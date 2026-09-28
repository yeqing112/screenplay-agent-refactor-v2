"""Shot scoped video production orchestration contracts."""

import json
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import core.shot_video_production as orchestration
from models import Keyframe, MediaCandidateRecord, ProductionPromptVersion, StoryboardShot, VideoGenerationIntent
import core.video_generation_runtime as runtime
from scripts.verify_migration_chain import _upgrade


def _session(tmp_path: Path):
    db = tmp_path / "shot-video-orchestration.sqlite"
    _upgrade(db)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    return engine, sessionmaker(bind=engine)()


def _context(shot: StoryboardShot) -> dict:
    # The execution context may contain ORM rows internally.  The API
    # projection must remain primitive and JSON serializable.
    frame = Keyframe(id=991, frame_type="START", time_seconds=0)
    return {
        "shot": shot,
        "sequence": SimpleNamespace(id=21, revision=1, duration=2),
        "profile": {"id": "builtin-mock-video", "provider": "mock-video", "capability": "video"},
        "capabilities": {"last_frame": True, "aspect_ratio": True},
        "start": frame,
        "end": None,
        "start_asset": {"keyframe_id": 991, "binding_id": 1},
        "end_asset": {},
        "prompt": SimpleNamespace(prompt_version_id="prompt-v1"),
        "prompt_text": "A traveler faces the silent tunnel.",
        "duration": 2,
        "aspect_ratio": "16:9",
        "motion_profile": {"camera_motion": "hold"},
        "source_fingerprint": "sha256:source",
        "basis": {
            "shot_id": shot.id,
            "shot_direction": {"fingerprint": "sha256:direction"},
            "prompt_authority": {"pointer_id": 1, "version_id": 2, "payload_hash": "sha256:prompt"},
            "model_profile": {"id": "builtin-mock-video"},
        },
    }


def test_reconcile_response_does_not_leak_orm_rows(tmp_path, monkeypatch):
    engine, session = _session(tmp_path)
    try:
        shot = StoryboardShot(book_id=1, episode=1, scene_name="Station", scene_id="s1", shot_id=1, materialization_status="MATERIALIZED")
        session.add(shot)
        session.flush()
        monkeypatch.setattr(orchestration, "_source_context", lambda *_args, **_kwargs: _context(shot))
        result = orchestration.reconcile_video_intent(session, shot_id=shot.id)
        json.dumps(result)
        assert result["source"]["shot_id"] == shot.id
        assert result["source"]["basis"]["shot_id"] == shot.id
        assert session.query(VideoGenerationIntent).count() == 1
    finally:
        session.close()
        engine.dispose()


def test_reconcile_is_idempotent_for_same_source(tmp_path, monkeypatch):
    engine, session = _session(tmp_path)
    try:
        shot = StoryboardShot(book_id=1, episode=1, scene_name="Station", scene_id="s1", shot_id=2, materialization_status="MATERIALIZED")
        session.add(shot)
        session.flush()
        monkeypatch.setattr(orchestration, "_source_context", lambda *_args, **_kwargs: _context(shot))
        first = orchestration.reconcile_video_intent(session, shot_id=shot.id)
        second = orchestration.reconcile_video_intent(session, shot_id=shot.id)
        assert first["intent"]["id"] == second["intent"]["id"]
        assert second["idempotent"] is True
        assert session.query(VideoGenerationIntent).count() == 1
    finally:
        session.close()
        engine.dispose()


def test_mock_execution_reuses_existing_execution_and_keeps_lineage(tmp_path, monkeypatch):
    engine, session = _session(tmp_path)
    try:
        shot = StoryboardShot(book_id=1, episode=1, scene_name="Station", scene_id="s1", shot_id=3, materialization_status="MATERIALIZED")
        session.add(shot)
        session.add(ProductionPromptVersion(prompt_version_id="prompt-v1", prompt_id="p1", version_number=1, prompt_text="A traveler faces the silent tunnel.", prompt_structure="{}", prompt_fingerprint="sha256:p", created_from="TEST"))
        session.flush()
        context = _context(shot)
        monkeypatch.setattr(orchestration, "_source_context", lambda *_args, **_kwargs: context)
        monkeypatch.setattr(runtime, "_validate_frame_asset", lambda *_args, **kwargs: {"keyframe_id": 991 if kwargs.get("first") else 992, "storage_identity": "fixture://frame", "asset_authority_current": True})
        monkeypatch.setattr(runtime, "_current_video_prompt_ir", lambda *_args, **_kwargs: (SimpleNamespace(id=1), SimpleNamespace(id=2, payload_hash="sha256:ir", payload_json=json.dumps({"prompt": "A traveler faces the silent tunnel."})), SimpleNamespace(id=3)))
        monkeypatch.setattr(runtime, "validate_media_candidate", lambda _session, _candidate_id: {"validation_id": "validation-1", "validation": SimpleNamespace(status="TECHNICALLY_VALID"), "promotion": SimpleNamespace(promotion_id="promotion-1")})

        def fake_candidate(db, execution, result):
            row = MediaCandidateRecord(candidate_id="video-candidate-orchestration", execution_id=execution.execution_id, status="MEDIA_CANDIDATE", media_type="VIDEO", storage_identity="fixture://video", storage_reference_json="{}", metadata_json=json.dumps({"media_type": "VIDEO"}), checksum_sha256="sha256:video", mime_type="video/mp4", byte_size=4, width=2, height=2, duration_ms=2000, prompt_ir_version_id=execution.prompt_ir_version_id, prompt_ir_payload_hash=execution.prompt_ir_payload_hash, generation_payload_fingerprint=execution.generation_payload_fingerprint, model_profile_id=execution.model_profile_id, model_profile_fingerprint=execution.model_profile_fingerprint, provider_request_fingerprint=execution.provider_request_fingerprint, provider_response_hash=result.provider_response_hash, provider_task_id=result.provider_task_id)
            db.add(row)
            db.flush()
            return row

        monkeypatch.setattr(runtime, "_persist_video_candidate", fake_candidate)
        first = orchestration.execute_shot_video_production(session, shot_id=shot.id)
        second = orchestration.execute_shot_video_production(session, shot_id=shot.id)
        assert first["candidate"]["media_type"] == "VIDEO"
        assert second["reused"] is True
        assert second["provider_calls"] == 0
        assert json.loads(session.query(VideoGenerationIntent).one().motion_profile)["orchestration_lineage"]["human_review_required"] is True
    finally:
        session.close()
        engine.dispose()
