"""Keyframe Authoring Runtime contract tests."""
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from core.keyframe_authoring import (
    KeyframeAuthoringError,
    bind_keyframe_asset,
    create_keyframe_prompt_version,
    create_keyframe_sequence,
    get_keyframe_sequence,
    inject_keyframe_constraints,
    update_keyframe,
    validate_keyframe_sequence,
)
from core.production_asset_authority import ingest_production_asset
from core.shot_direction import create_shot_direction
from models import Keyframe, KeyframeAssetBinding, KeyframeSequence, ProductionPromptVersion, StoryboardShot
from scripts.verify_migration_chain import _upgrade


def _session(tmp_path: Path):
    db = tmp_path / "keyframe-authoring.sqlite"
    _upgrade(db)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    return engine, sessionmaker(bind=engine)()


def _shot(session, *, shot_id: int = 51):
    row = StoryboardShot(book_id=990401, episode=2, scene_name="旧车站", scene_id="scene:station", shot_id=shot_id, materialization_status="MATERIALIZED", execution_status="queued", quality_status="draft", production_status="blocked", workflow_profile="production")
    session.add(row)
    session.flush()
    create_shot_direction(
        session,
        shot_id=row.id,
        shot_type="medium shot",
        camera_profile={"lens": "35mm", "angle": "eye_level", "distance": "medium shot", "movement": "slow push in", "speed": "slow"},
        movement_profile={"trajectory": "toward subject", "stabilization": "dolly"},
        composition_profile={"framing": "centered", "subject_position": "left third", "foreground": "door frame", "background": "empty platform", "depth": "layered"},
        performance_profile={"expression": "restrained fear", "gesture": "hands tighten", "body_motion": "turns slowly", "eye_direction": "toward tunnel"},
        emotion_profile={"arc": "suspicion to resolve", "intensity": 7},
    )
    session.flush()
    return row


def _frames():
    return [
        {"type": "start", "time": 0, "description": "traveler waits beside the platform", "camera_state": {"distance": "medium"}, "character_state": {"pose": "still"}, "scene_state": {"wind": "quiet"}, "emotion_state": {"value": "calm"}, "camera_motion": "slow_push_in", "character_motion": "still", "environment_motion": "wind_effect", "emotion_transition": "calm_to_suspicion"},
        {"type": "middle", "time": 2, "description": "traveler turns toward the tunnel", "camera_state": {"distance": "medium_close_up"}, "character_state": {"pose": "turning"}, "scene_state": {"wind": "rising"}, "emotion_state": {"value": "suspicious"}, "camera_motion": "continue_push_in", "character_motion": "head_turn", "environment_motion": "wind_effect", "emotion_transition": "suspicion_to_fear"},
        {"type": "end", "time": 4, "description": "traveler faces the unseen threat", "camera_state": {"distance": "close_up"}, "character_state": {"pose": "rigid"}, "scene_state": {"wind": "strong"}, "emotion_state": {"value": "fear"}, "camera_motion": "hold", "character_motion": "freeze", "environment_motion": "dust_swirl", "emotion_transition": "fear_to_resolve"},
    ]


def test_migration_exposes_keyframe_authoring_relations(tmp_path):
    engine, session = _session(tmp_path)
    try:
        tables = set(inspect(engine).get_table_names())
        assert {"keyframe_sequences", "keyframes", "keyframe_asset_bindings"}.issubset(tables)
        assert KeyframeSequence.__tablename__ == "keyframe_sequences"
        assert Keyframe.__tablename__ == "keyframes"
    finally:
        session.close(); engine.dispose()


def test_sequence_validation_order_prompt_and_lineage(tmp_path):
    engine, session = _session(tmp_path)
    try:
        shot = _shot(session)
        sequence = create_keyframe_sequence(session, shot_id=shot.id, duration=4, frame_plan={"fps": 24}, frames=_frames())
        session.commit()
        assert len(sequence["frames"]) == 3
        assert sequence["frames"][0]["type"] == "start"
        updated = update_keyframe(session, keyframe_id=sequence["frames"][1]["id"], values={"description": "traveler slowly turns toward the tunnel", "camera_motion": "medium_push_in"})
        assert updated["description"].startswith("traveler slowly")
        source = "The traveler waits beside the silent platform."
        compiled = inject_keyframe_constraints(session, keyframe_id=sequence["frames"][0]["id"], original_prompt=source)
        assert compiled["original_prompt"] == source
        assert compiled["prompt_was_mutated"] is False
        assert "Frame State" in compiled["injected_prompt"]
        assert "Motion Preparation" in compiled["injected_prompt"]
        assert "Camera Direction" in compiled["injected_prompt"]
        prompt = create_keyframe_prompt_version(session, keyframe_id=sequence["frames"][0]["id"], prompt_id="keyframe-prompt-51", original_prompt=source)
        row = session.query(ProductionPromptVersion).filter_by(prompt_version_id=prompt["prompt_version"]["prompt_version_id"]).one()
        assert "KEYFRAME_AUTHORING" in row.created_from
        assert "SHOT_DIRECTION" in row.created_from
        assert source in json.loads(row.prompt_structure)["source_prompt"]
    finally:
        session.close(); engine.dispose()


def test_invalid_sequence_order_fails_closed(tmp_path):
    engine, session = _session(tmp_path)
    try:
        shot = _shot(session, shot_id=52)
        invalid = _frames()
        invalid[0]["time"] = 1
        with pytest.raises(KeyframeAuthoringError) as exc:
            create_keyframe_sequence(session, shot_id=shot.id, duration=4, frame_plan={}, frames=invalid)
        assert exc.value.code == "KEYFRAME_SEQUENCE_INVALID"
        codes = {item["code"] for item in exc.value.diagnostics}
        assert "KEYFRAME_START_TIME_INVALID" in codes
    finally:
        session.close(); engine.dispose()


def test_first_frame_asset_binding_is_traceable_and_validation_passes(tmp_path):
    engine, session = _session(tmp_path)
    try:
        shot = _shot(session, shot_id=53)
        sequence = create_keyframe_sequence(session, shot_id=shot.id, duration=4, frame_plan={}, frames=_frames())
        asset = ingest_production_asset(session, entity_type="SCENE", entity_id="scene:station", source={"storage_identity": "https://cdn.example.test/station.png", "checksum": "sha256:station", "metadata": {"source_kind": "real_media", "mime_type": "image/png"}})
        bind_keyframe_asset(session, keyframe_id=sequence["frames"][0]["id"], asset_type=asset["asset_type"], authority_id=asset["authority_id"], version_id=asset["version_id"], is_primary=True)
        create_keyframe_prompt_version(session, keyframe_id=sequence["frames"][0]["id"], prompt_id="keyframe-prompt-53", original_prompt="A traveler waits.")
        session.commit()
        binding = session.query(KeyframeAssetBinding).filter_by(keyframe_id=sequence["frames"][0]["id"], status="ACTIVE").one()
        assert binding.is_primary is True
        validation = validate_keyframe_sequence(session, shot_id=shot.id)
        assert validation["status"] == "PASS", validation
        assert validation["checks"]["asset_binding_correct"] is True
    finally:
        session.close(); engine.dispose()
