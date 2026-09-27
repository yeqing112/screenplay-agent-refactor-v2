"""Shot Direction Runtime contract tests."""
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from core.shot_direction import (
    ShotDirectionError,
    create_shot_direction,
    create_shot_direction_prompt_version,
    get_shot_direction,
    inject_shot_direction,
    update_shot_direction,
    validate_shot_direction,
)
from models import ProductionPromptVersion, ShotDirection, StoryboardShot
from scripts.verify_migration_chain import _upgrade


def _session(tmp_path: Path):
    db = tmp_path / "shot-direction.sqlite"
    _upgrade(db)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    return engine, sessionmaker(bind=engine)()


def _shot(session, *, shot_id: int = 41):
    row = StoryboardShot(
        book_id=990403,
        episode=2,
        scene_name="旧车站",
        scene_id="scene:station",
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


def _payload():
    return {
        "shot_type": "medium shot",
        "camera_profile": {"lens": "35mm", "angle": "eye_level", "distance": "medium shot", "movement": "slow push in", "speed": "slow"},
        "movement_profile": {"trajectory": "toward subject", "stabilization": "dolly"},
        "composition_profile": {"framing": "centered", "subject_position": "left third", "foreground": "door frame", "background": "empty platform", "depth": "layered"},
        "performance_profile": {"expression": "restrained fear", "gesture": "hands tighten", "body_motion": "turns slowly", "eye_direction": "toward the tunnel"},
        "emotion_profile": {"arc": "suspicion to resolve", "intensity": 7},
    }


def test_migration_exposes_shot_direction_relation(tmp_path):
    engine, session = _session(tmp_path)
    try:
        tables = set(inspect(engine).get_table_names())
        assert "shot_directions" in tables
        columns = {item["name"] for item in inspect(engine).get_columns("shot_directions")}
        assert {"storyboard_shot_id", "shot_type", "camera_profile", "movement_profile", "composition_profile", "performance_profile", "emotion_profile", "revision", "direction_fingerprint", "status"}.issubset(columns)
        assert ShotDirection.__tablename__ == "shot_directions"
    finally:
        session.close(); engine.dispose()


def test_direction_entity_validation_update_and_prompt_lineage(tmp_path):
    engine, session = _session(tmp_path)
    try:
        shot = _shot(session)
        direction = create_shot_direction(session, shot_id=shot.id, **_payload())
        session.commit()
        assert direction["shot_id"] == shot.id
        assert direction["revision"] == 1
        validation = validate_shot_direction(session, shot_id=shot.id)
        assert validation["status"] == "PASS"
        assert validation["checks"] == {"shot_exists": True, "direction_present": True, "camera_valid": True, "complete": True}

        source = "The traveler waits beside the silent platform."
        compiled = inject_shot_direction(session, shot_id=shot.id, original_prompt=source)
        assert compiled["original_prompt"] == source
        assert compiled["prompt_was_mutated"] is False
        assert source in compiled["injected_prompt"]
        assert "Camera Direction" in compiled["injected_prompt"]
        assert "Composition" in compiled["injected_prompt"]
        assert "Performance" in compiled["injected_prompt"]
        assert "35mm" in compiled["injected_prompt"]

        updated = update_shot_direction(session, shot_id=shot.id, camera_profile={**_payload()["camera_profile"], "speed": "medium"})
        session.commit()
        assert updated["revision"] == 2
        assert get_shot_direction(session, shot_id=shot.id)["camera_profile"]["speed"] == "medium"

        prompt_version = create_shot_direction_prompt_version(session, prompt_id="shot-41-direction", shot_id=shot.id, original_prompt=source)
        persisted = session.query(ProductionPromptVersion).filter_by(prompt_version_id=prompt_version["prompt_version"]["prompt_version_id"]).one()
        assert persisted.created_from == "SHOT_DIRECTION"
        assert source in persisted.prompt_structure
    finally:
        session.close(); engine.dispose()


def test_camera_validation_rejects_invalid_parameters(tmp_path):
    engine, session = _session(tmp_path)
    try:
        shot = _shot(session, shot_id=42)
        payload = _payload()
        payload["camera_profile"] = {**payload["camera_profile"], "lens": "cinema", "angle": "unknown_angle", "speed": "instant"}
        with pytest.raises(ShotDirectionError) as exc:
            create_shot_direction(session, shot_id=shot.id, **payload)
        assert exc.value.code == "SHOT_DIRECTION_INVALID"
        codes = {item["code"] for item in exc.value.diagnostics}
        assert {"CAMERA_LENS_INVALID", "CAMERA_ANGLE_INVALID", "CAMERA_SPEED_INVALID"}.issubset(codes)
    finally:
        session.close(); engine.dispose()


def test_missing_direction_blocks_validation_and_prompt(tmp_path):
    engine, session = _session(tmp_path)
    try:
        shot = _shot(session, shot_id=43)
        validation = validate_shot_direction(session, shot_id=shot.id)
        assert validation["status"] == "BLOCKED"
        assert validation["errors"][0]["code"] == "SHOT_DIRECTION_MISSING"
        with pytest.raises(ShotDirectionError) as exc:
            inject_shot_direction(session, shot_id=shot.id, original_prompt="original")
        assert exc.value.code == "SHOT_DIRECTION_BLOCKED"
    finally:
        session.close(); engine.dispose()
