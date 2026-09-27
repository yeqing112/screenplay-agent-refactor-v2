"""Scene Continuity Runtime contract tests."""
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from core.scene_continuity import (
    SceneContinuityError,
    add_scene_reference_asset,
    bind_shot_scene,
    create_scene_constrained_prompt_version,
    create_scene_identity,
    inject_scene_constraints,
    validate_scene_continuity,
)
from models import ProductionPromptVersion, SceneIdentity, SceneReferenceAsset, ShotSceneBinding, StoryboardShot
from scripts.verify_migration_chain import _upgrade


def _session(tmp_path: Path):
    db = tmp_path / "scene-continuity.sqlite"
    _upgrade(db)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    return engine, sessionmaker(bind=engine)()


def _shot(session, *, shot_id: int = 21):
    row = StoryboardShot(
        book_id=990401,
        episode=1,
        scene_name="雨夜码头",
        scene_id="scene:harbor",
        shot_id=shot_id,
        materialization_status="MATERIALIZED",
        execution_status="queued",
        quality_status="draft",
        production_status="blocked",
        workflow_profile="production",
    )
    session.add(row)
    session.flush()
    return row


def test_migration_exposes_scene_identity_extensions_and_relations(tmp_path):
    engine, session = _session(tmp_path)
    try:
        columns = {item["name"] for item in inspect(engine).get_columns("visual_locations")}
        assert {"attributes", "environment_profile"}.issubset(columns)
        assert {"scene_reference_assets", "shot_scene_bindings"}.issubset(set(inspect(engine).get_table_names()))
        assert SceneIdentity.__tablename__ == "visual_locations"
    finally:
        session.close(); engine.dispose()


def test_scene_binding_and_prompt_injection_preserve_source_prompt(tmp_path):
    engine, session = _session(tmp_path)
    try:
        scene = create_scene_identity(
            session,
            book_id=990401,
            scene_id="SCENE_HARBOR",
            name="雨夜码头",
            description="潮湿的旧码头，远处有锈蚀吊机",
            attributes={"geometry": "linear pier", "surface": "wet timber"},
            environment_profile={"weather": "rain", "time": "night", "lighting": "blue sodium haze"},
        )
        overview = add_scene_reference_asset(session, scene_id=scene["id"], asset_id="harbor-overview-v1", reference_type="overview", priority=0, constraint_snapshot={"horizon": "open water"})
        lighting = add_scene_reference_asset(session, scene_id=scene["id"], asset_id="harbor-lighting-v1", reference_type="lighting", priority=1)
        shot = _shot(session)
        binding = bind_shot_scene(session, shot_id=shot.id, scene_id=scene["id"], reference_asset_ids=[overview["asset_id"], lighting["id"]], environment_rules={"rain": "continuous", "screen_direction": "preserve"})
        session.commit()

        validation = validate_scene_continuity(session, shot_id=shot.id)
        assert validation["status"] == "PASS"
        assert validation["checks"] == {"scene_bound": True, "reference_asset_present": True, "constraints_present": True}
        assert binding["scene_id"] == scene["id"]
        assert session.query(SceneReferenceAsset).count() == 2
        assert session.query(ShotSceneBinding).count() == 1

        source = "A wide shot starts at the edge of the dock."
        compiled = inject_scene_constraints(session, shot_id=shot.id, original_prompt=source)
        assert compiled["original_prompt"] == source
        assert compiled["prompt_was_mutated"] is False
        assert source in compiled["injected_prompt"]
        assert "雨夜码头" in compiled["injected_prompt"]
        assert "blue sodium haze" in compiled["injected_prompt"]
        assert "harbor-overview-v1" in compiled["injected_prompt"]
        assert "continuous" in compiled["injected_prompt"]

        prompt_version = create_scene_constrained_prompt_version(session, prompt_id="shot-21-scene", shot_id=shot.id, original_prompt=source)
        persisted = session.query(ProductionPromptVersion).filter_by(prompt_version_id=prompt_version["prompt_version"]["prompt_version_id"]).one()
        assert persisted.created_from == "SCENE_CONTINUITY"
        assert source in persisted.prompt_structure
    finally:
        session.close(); engine.dispose()


def test_missing_scene_reference_blocks_continuity_and_prompt_injection(tmp_path):
    engine, session = _session(tmp_path)
    try:
        scene = create_scene_identity(session, book_id=990401, name="无参考场景", description="a scene without a reference")
        shot = _shot(session, shot_id=22)
        bind_shot_scene(session, shot_id=shot.id, scene_id=scene["id"])
        session.commit()
        validation = validate_scene_continuity(session, shot_id=shot.id)
        assert validation["status"] == "BLOCKED"
        assert any(item["code"] == "SCENE_REFERENCE_ASSET_MISSING" for item in validation["errors"])
        with pytest.raises(SceneContinuityError) as exc:
            inject_scene_constraints(session, shot_id=shot.id, original_prompt="original")
        assert exc.value.code == "SCENE_CONTINUITY_BLOCKED"
    finally:
        session.close(); engine.dispose()
