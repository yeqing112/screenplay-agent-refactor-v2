"""Video Generation Runtime contract tests."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

import core.video_generation_runtime as runtime
from core.keyframe_authoring import bind_keyframe_asset, create_keyframe_sequence
from core.production_asset_authority import ingest_production_asset
from core.video_provider_adapter import MockVideoProvider
from models import GenerationExecutionRecord, MediaCandidateRecord, ProductionPromptVersion, PromptIRPointer, PromptIRVersion, StoryboardShot, TaskRun, VideoGenerationIntent
from scripts.verify_migration_chain import _upgrade


def _session(tmp_path: Path):
    db = tmp_path / "video-generation.sqlite"
    _upgrade(db)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    return engine, sessionmaker(bind=engine)()


def _fixture(session, *, shot_id: int = 61):
    shot = StoryboardShot(book_id=990401, episode=3, scene_name="旧车站", scene_id="scene:station", shot_id=shot_id, plan_shot_id=f"PLAN-{shot_id}", materialization_status="MATERIALIZED", execution_status="queued", quality_status="draft", production_status="blocked", workflow_profile="production")
    session.add(shot)
    session.flush()
    frames = [
        {"type": "start", "time": 0, "description": "traveler waits", "camera_state": {}, "character_state": {}, "scene_state": {}, "emotion_state": {}, "camera_motion": "slow_push_in", "character_motion": "still", "environment_motion": "wind_motion", "emotion_transition": "calm_to_fear"},
        {"type": "end", "time": 2, "description": "traveler faces the tunnel", "camera_state": {}, "character_state": {}, "scene_state": {}, "emotion_state": {}, "camera_motion": "hold", "character_motion": "head_turn", "environment_motion": "wind_motion", "emotion_transition": "fear_transition"},
    ]
    sequence = create_keyframe_sequence(session, shot_id=shot.id, duration=2, frame_plan={"fps": 24}, frames=frames)
    asset = ingest_production_asset(session, entity_type="SCENE", entity_id="scene:station", source={"storage_identity": "https://cdn.example.test/station.png", "checksum": "sha256:station", "metadata": {"source_kind": "real_media", "mime_type": "image/png"}})
    bind_keyframe_asset(session, keyframe_id=sequence["frames"][0]["id"], asset_type="SCENE", authority_id=asset["authority_id"], version_id=asset["version_id"], is_primary=True)
    bind_keyframe_asset(session, keyframe_id=sequence["frames"][1]["id"], asset_type="SCENE", authority_id=asset["authority_id"], version_id=asset["version_id"], is_primary=True)
    prompt = ProductionPromptVersion(prompt_version_id=f"ppv-video-{shot.id}", prompt_id=f"video-prompt-{shot.id}", version_number=1, prompt_text="A traveler faces the silent tunnel.", prompt_structure=json.dumps({"source_prompt": "A traveler faces the silent tunnel."}), prompt_fingerprint="sha256:video-prompt", created_from="KEYFRAME_AUTHORING")
    session.add(prompt)
    session.flush()
    return shot, sequence, prompt


def _motion():
    return {"camera_motion": "slow_push_in", "subject_motion": "head_turn", "environment_motion": "wind_motion", "emotion_transition": "calm_to_fear"}


def test_execution_projection_redacts_nested_provider_credentials():
    assert runtime._secret_free({
        "Authorization": "Bearer secret",
        "api_key": "secret",
        "nested": {"x-api-key": "secret", "status": "succeeded"},
    }) == {"nested": {"status": "succeeded"}}


def test_migration_exposes_video_generation_intent(tmp_path):
    engine, session = _session(tmp_path)
    try:
        assert "video_generation_intents" in set(inspect(engine).get_table_names())
        assert VideoGenerationIntent.__tablename__ == "video_generation_intents"
    finally:
        session.close(); engine.dispose()


def test_video_intent_reuses_keyframe_and_prompt_lineage(tmp_path):
    engine, session = _session(tmp_path)
    try:
        shot, sequence, prompt = _fixture(session)
        intent = runtime.create_video_generation_intent(session, shot_id=shot.id, duration=2, aspect_ratio="16:9", motion_profile=_motion(), first_frame_asset={"keyframe_id": sequence["frames"][0]["id"]}, last_frame_asset={"keyframe_id": sequence["frames"][1]["id"]}, prompt_version=prompt.prompt_version_id)
        session.commit()
        assert intent["generation_type"] == "VIDEO"
        assert intent["first_frame_asset"]["binding_fingerprint"]
        assert intent["last_frame_asset"]["keyframe_id"] == sequence["frames"][1]["id"]
        assert runtime.get_video_generation_intent(session, shot_id=shot.id)["id"] == intent["id"]
    finally:
        session.close(); engine.dispose()


def test_video_intent_requires_current_first_frame_asset(tmp_path):
    engine, session = _session(tmp_path)
    try:
        shot, sequence, prompt = _fixture(session, shot_id=62)
        with pytest.raises(runtime.VideoGenerationError) as exc:
            runtime.create_video_generation_intent(session, shot_id=shot.id, duration=2, aspect_ratio="16:9", motion_profile=_motion(), first_frame_asset={"keyframe_id": 999999}, last_frame_asset={}, prompt_version=prompt.prompt_version_id)
        assert exc.value.code == "VIDEO_FRAME_ASSET_INVALID"
    finally:
        session.close(); engine.dispose()


def test_mock_video_provider_exposes_generate_video_without_network():
    result = MockVideoProvider().generate_video(prompt="A locked prompt", motion_profile=_motion(), duration=2, aspect_ratio="16:9", first_frame_asset={"keyframe_id": 1}, last_frame_asset={}, request_context={"intent_id": 1})
    assert result.status == "SUCCESS"
    assert result.provider == "mock-video"
    assert result.media_uri.startswith("data:video/mp4;base64,")
    assert result.logical_provider_calls == 1


def test_video_execution_reuses_generation_execution_task_and_candidate_chain(tmp_path, monkeypatch):
    engine, session = _session(tmp_path)
    try:
        shot, sequence, prompt = _fixture(session, shot_id=63)
        intent = runtime.create_video_generation_intent(session, shot_id=shot.id, duration=2, aspect_ratio="16:9", motion_profile=_motion(), first_frame_asset={"keyframe_id": sequence["frames"][0]["id"]}, last_frame_asset={}, prompt_version=prompt.prompt_version_id)
        session.commit()
        ir = SimpleNamespace(id=901, payload_hash="sha256:video-ir", payload_json=json.dumps({"generation_policy": {"target_media": "VIDEO", "mode": "TEXT_TO_VIDEO", "duration_seconds": 2, "fingerprint": "sha256:video-policy"}}))
        pointer = SimpleNamespace(id=902)
        authority = SimpleNamespace(id=903)
        monkeypatch.setattr(runtime, "_current_video_prompt_ir", lambda _session, shot: (pointer, ir, authority))

        def fake_candidate(_session, execution, result):
            row = MediaCandidateRecord(candidate_id="video-candidate-test", execution_id=execution.execution_id, status="MEDIA_CANDIDATE", media_type="VIDEO", storage_identity="mock://video", storage_reference_json="{}", metadata_json=json.dumps({"media_type": "VIDEO", "mime_type": "video/mp4", "byte_size": 1, "width": 2, "height": 2, "duration_ms": 2000}), checksum_sha256="sha256:video", mime_type="video/mp4", byte_size=1, width=2, height=2, duration_ms=2000, prompt_ir_version_id=901, prompt_ir_payload_hash="sha256:video-ir", generation_payload_fingerprint=execution.generation_payload_fingerprint, model_profile_id=execution.model_profile_id, model_profile_fingerprint=execution.model_profile_fingerprint, provider_request_fingerprint=execution.provider_request_fingerprint, provider_response_hash=result.provider_response_hash, provider_task_id=result.provider_task_id)
            _session.add(row)
            _session.flush()
            return row

        monkeypatch.setattr(runtime, "_persist_video_candidate", fake_candidate)
        monkeypatch.setattr(runtime, "validate_media_candidate", lambda _session, candidate_id: {"validation_id": "mvr-video-test", "validation": SimpleNamespace(status="TECHNICALLY_VALID"), "promotion": SimpleNamespace(promotion_id="mpr-video-test")})
        result = runtime.execute_video_generation(session, intent_id=intent["id"])
        assert result["execution"]["generation_type"] == "VIDEO"
        assert result["execution"]["status"] == "SUCCESS"
        assert result["candidate"]["media_type"] == "VIDEO"
        assert session.query(GenerationExecutionRecord).filter_by(target_media="VIDEO").count() == 1
        assert session.query(TaskRun).filter_by(task_kind="VIDEO_GENERATION", status="completed").count() == 1
        assert result["validation"]["promotion_id"] == "mpr-video-test"
    finally:
        session.close(); engine.dispose()
