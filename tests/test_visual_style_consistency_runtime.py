"""Visual Style Consistency Runtime contract tests."""
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from core.visual_style_consistency import (
    VisualStyleConsistencyError,
    add_style_reference_asset,
    bind_episode_style,
    bind_shot_style,
    create_style_constrained_prompt_version,
    create_visual_style_profile,
    inject_style_constraints,
    validate_shot_style_consistency,
)
from models import ProductionPromptVersion, ShotStyleBinding, StoryboardShot, StyleReferenceAsset, VisualStyleProfile
from scripts.verify_migration_chain import _upgrade


def _session(tmp_path: Path):
    db = tmp_path / "visual-style.sqlite"
    _upgrade(db)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    return engine, sessionmaker(bind=engine)()


def _shot(session, *, shot_id: int = 31, episode: int = 1):
    row = StoryboardShot(
        book_id=990402,
        episode=episode,
        scene_name="摄影棚",
        scene_id="scene:studio",
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


def _style(session, name: str = "冷峻电影风格"):
    return create_visual_style_profile(
        session,
        book_id=990402,
        name=name,
        description="冷色、克制、几何化的电影视觉规则",
        camera_profile={"lens": "35mm", "movement": "slow dolly"},
        lighting_profile={"key": "soft side light", "contrast": "high"},
        color_profile={"palette": ["steel blue", "charcoal"], "saturation": "muted"},
        composition_profile={"rule": "symmetry", "negative_space": True},
    )


def _reference(session, style_id: int, asset_id: str = "style-board-v1"):
    return add_style_reference_asset(session, style_id=style_id, asset_id=asset_id, reference_type="composition", priority=0, constraint_snapshot={"keep": "symmetry"})


def test_migration_exposes_visual_style_profile_and_relations(tmp_path):
    engine, session = _session(tmp_path)
    try:
        tables = set(inspect(engine).get_table_names())
        assert {"visual_style_profiles", "style_reference_assets", "shot_style_bindings"}.issubset(tables)
        assert {"camera_profile", "lighting_profile", "color_profile", "composition_profile"}.issubset({item["name"] for item in inspect(engine).get_columns("visual_style_profiles")})
        assert {"book_id", "episode", "style_id", "scope", "style_rules", "binding_fingerprint", "status"}.issubset({item["name"] for item in inspect(engine).get_columns("shot_style_bindings")})
        assert VisualStyleProfile.__tablename__ == "visual_style_profiles"
    finally:
        session.close(); engine.dispose()


def test_episode_default_and_shot_override_inject_style_without_mutating_source(tmp_path):
    engine, session = _session(tmp_path)
    try:
        default_style = _style(session, "Episode 默认风格")
        _reference(session, default_style["id"], "episode-style-board")
        override_style = _style(session, "Shot 覆盖风格")
        _reference(session, override_style["id"], "shot-style-board")
        shot = _shot(session)
        bind_episode_style(session, book_id=shot.book_id, episode=shot.episode, style_id=default_style["id"], style_rules={"grain": "fine"})
        session.commit()

        default_validation = validate_shot_style_consistency(session, shot_id=shot.id)
        assert default_validation["status"] == "PASS"
        assert default_validation["checks"]["scope"] == "EPISODE_DEFAULT"
        source = "A locked medium shot in the studio."
        compiled = inject_style_constraints(session, shot_id=shot.id, original_prompt=source)
        assert compiled["original_prompt"] == source
        assert compiled["prompt_was_mutated"] is False
        assert source in compiled["injected_prompt"]
        assert "Camera Rules" in compiled["injected_prompt"]
        assert "Lighting Rules" in compiled["injected_prompt"]
        assert "Color Rules" in compiled["injected_prompt"]
        assert "Composition Rules" in compiled["injected_prompt"]
        assert "episode-style-board" in compiled["injected_prompt"]

        bind_shot_style(session, shot_id=shot.id, style_id=override_style["id"], style_rules={"camera": "hold center"})
        session.commit()
        override_validation = validate_shot_style_consistency(session, shot_id=shot.id)
        assert override_validation["status"] == "PASS"
        assert override_validation["binding"]["scope"] == "SHOT_OVERRIDE"
        assert override_validation["binding"]["style_id"] == override_style["id"]
        assert session.query(ShotStyleBinding).filter_by(storyboard_shot_id=shot.id, status="STALE").count() == 0
        assert session.query(StyleReferenceAsset).count() == 2

        prompt_version = create_style_constrained_prompt_version(session, prompt_id="shot-31-style", shot_id=shot.id, original_prompt=source)
        persisted = session.query(ProductionPromptVersion).filter_by(prompt_version_id=prompt_version["prompt_version"]["prompt_version_id"]).one()
        assert persisted.created_from == "VISUAL_STYLE_CONSISTENCY"
        assert source in persisted.prompt_structure
    finally:
        session.close(); engine.dispose()


def test_rebinding_same_shot_stales_previous_override(tmp_path):
    engine, session = _session(tmp_path)
    try:
        first = _style(session, "第一套风格")
        _reference(session, first["id"], "first-style")
        second = _style(session, "第二套风格")
        _reference(session, second["id"], "second-style")
        shot = _shot(session, shot_id=32)
        bind_shot_style(session, shot_id=shot.id, style_id=first["id"])
        bind_shot_style(session, shot_id=shot.id, style_id=second["id"])
        session.commit()
        assert session.query(ShotStyleBinding).filter_by(storyboard_shot_id=shot.id, status="ACTIVE").count() == 1
        assert session.query(ShotStyleBinding).filter_by(storyboard_shot_id=shot.id, status="STALE").count() == 1
        assert validate_shot_style_consistency(session, shot_id=shot.id)["binding"]["style_id"] == second["id"]
    finally:
        session.close(); engine.dispose()


def test_missing_style_reference_blocks_validation_and_prompt(tmp_path):
    engine, session = _session(tmp_path)
    try:
        style = _style(session, "没有参考的风格")
        shot = _shot(session, shot_id=33)
        bind_shot_style(session, shot_id=shot.id, style_id=style["id"])
        session.commit()
        validation = validate_shot_style_consistency(session, shot_id=shot.id)
        assert validation["status"] == "BLOCKED"
        assert any(item["code"] == "STYLE_REFERENCE_ASSET_MISSING" for item in validation["errors"])
        with pytest.raises(VisualStyleConsistencyError) as exc:
            inject_style_constraints(session, shot_id=shot.id, original_prompt="original")
        assert exc.value.code == "VISUAL_STYLE_CONSISTENCY_BLOCKED"
    finally:
        session.close(); engine.dispose()
