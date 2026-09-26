"""Real image Provider Adapter and execution-to-candidate contract tests."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import config
from core.generation_execution_service import GenerationExecutionService
from core.generation_orchestrator import GenerationOrchestrator, GenerationOrchestratorError
from core.model_adapter_runtime import ImageGenerationProviderAdapter, ModelAdapterRegistry
from models import PromptIRPointer, PromptIRVersion, StoryboardShot
from scripts.verify_migration_chain import _upgrade


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
 )


def _session(tmp_path: Path):
    db = tmp_path / "real-image-provider.sqlite"
    _upgrade(db)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    return engine, sessionmaker(bind=engine)()


def _fixture(session, profile_id: str = "real-image-profile"):
    shot = StoryboardShot(
        book_id=981001,
        episode=1,
        scene_name="CANARY_SCENE",
        scene_id="CANARY_SCENE",
        plan_shot_id="CANARY_SHOT_001",
        shot_id=1,
    )
    session.add(shot)
    session.flush()
    version = PromptIRVersion(
        book_id=shot.book_id,
        episode=shot.episode,
        scene_id=shot.scene_id,
        storyboard_shot_id=shot.id,
        materialization_set_id=1,
        plan_shot_id=shot.plan_shot_id,
        schema_version="prompt_ir_real_image_canary_v1",
        payload_json='{"prompt":"a quiet cinematic room","generation_policy":{"target_media":"IMAGE"}}',
        payload_hash="sha256:real-image-canary-prompt",
        compiler_version="test",
        compiler_policy_version="test",
        retention_policy_version="test",
    )
    session.add(version)
    session.flush()
    pointer = PromptIRPointer(
        book_id=shot.book_id,
        episode=shot.episode,
        storyboard_shot_id=shot.id,
        target_media="IMAGE",
        prompt_ir_version_id=version.id,
        payload_hash=version.payload_hash,
    )
    session.add(pointer)
    session.commit()
    return GenerationExecutionService(session).create_execution(
        shot_id=shot.id,
        prompt_pointer_id=pointer.id,
        prompt_version_id=version.id,
        model_profile_id=profile_id,
    )


def _profile(profile_id: str = "real-image-profile"):
    return {
        "id": profile_id,
        "name": "Canary real image",
        "capability": "image",
        "provider": "poyo-async",
        "base_url": "https://provider.invalid",
        "model_name": "gpt-image-2",
        "default_params": {"size": "1024x1024", "poll_interval_seconds": 1},
        "enabled": True,
        "uses_mock": False,
        "key_configured": True,
        "credential_configured": True,
        "api_key": "test-secret-never-persisted",
        "transport_binding_id": "poyo-async.image.v1",
    }


def test_image_provider_adapter_records_request_and_response_without_secret(monkeypatch: pytest.MonkeyPatch):
    async def fake_dispatch(context):
        assert context["profile"]["api_key"] == "test-secret-never-persisted"
        return {
            "uri": "data:image/png;base64," + base64.b64encode(PNG).decode("ascii"),
            "previewUrl": "data:image/png;base64," + base64.b64encode(PNG).decode("ascii"),
            "providerResponse": {"id": "provider-response-1", "status": "succeeded"},
            "providerRequestPayload": {"model": "gpt-image-2", "prompt": "a quiet cinematic room"},
            "providerRequestId": "provider-request-1",
            "providerTaskId": "provider-task-1",
        }

    monkeypatch.setattr("core.provider_transport_registry.dispatch_provider_transport", fake_dispatch)
    result = ImageGenerationProviderAdapter().generate(
        _profile(),
        {"prompt_ir_version_id": 7, "payload_hash": "sha256:p", "payload": {"prompt": "a quiet cinematic room"}},
        {"seed": 3},
    )
    assert result.status == "SUCCESS"
    assert result.provider_request_id == "provider-request-1"
    assert result.provider_task_id == "provider-task-1"
    assert result.asset_uri.startswith("data:image/png")
    assert result.provider_request["provider"] == "poyo-async"
    assert "test-secret" not in str(result.as_dict())


def test_real_image_execution_persists_media_candidate_and_provider_called(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("PHASE_F_PROVIDER_CANARY_REAL", "1")
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path / "uploads")

    async def fake_dispatch(_context):
        uri = "data:image/png;base64," + base64.b64encode(PNG).decode("ascii")
        return {
            "uri": uri,
            "previewUrl": uri,
            "providerResponse": {"id": "provider-response-2", "status": "succeeded"},
            "providerRequestPayload": {"model": "gpt-image-2", "prompt": "a quiet cinematic room"},
            "providerRequestId": "provider-request-2",
            "providerTaskId": "provider-task-2",
        }

    monkeypatch.setattr("core.provider_transport_registry.dispatch_provider_transport", fake_dispatch)
    engine, session = _session(tmp_path)
    try:
        row = _fixture(session)
        completed = GenerationOrchestrator(
            session,
            adapter_registry=ModelAdapterRegistry({"poyo-async": ImageGenerationProviderAdapter()}),
            profile_resolver=lambda _profile_id: _profile(),
        ).run(row.execution_id)
        session.commit()
        from models import MediaCandidateRecord

        candidate = session.query(MediaCandidateRecord).filter_by(execution_id=row.execution_id).one()
        assert completed.execution_status == "SUCCESS"
        assert completed.provider == "poyo-async"
        assert completed.provider_request_id == "provider-request-2"
        assert completed.candidate_id == candidate.candidate_id
        assert candidate.status == "MEDIA_CANDIDATE"
        assert candidate.media_type == "IMAGE"
        assert candidate.width == 1 and candidate.height == 1
        assert "test-secret" not in str(completed.request_payload)
        assert "test-secret" not in str(completed.response_payload)
    finally:
        session.close()
        engine.dispose()


def test_real_image_provider_failure_is_durable_and_fail_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("PHASE_F_PROVIDER_CANARY_REAL", "1")

    async def failed_dispatch(_context):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr("core.provider_transport_registry.dispatch_provider_transport", failed_dispatch)
    engine, session = _session(tmp_path)
    try:
        row = _fixture(session, profile_id="real-image-failure")
        with pytest.raises(GenerationOrchestratorError) as exc_info:
            GenerationOrchestrator(
                session,
                adapter_registry=ModelAdapterRegistry({"poyo-async": ImageGenerationProviderAdapter()}),
                profile_resolver=lambda _profile_id: _profile("real-image-failure"),
            ).run(row.execution_id)
        session.commit()
        assert exc_info.value.code == "REAL_PROVIDER_CALL_FAILED"
        assert row.execution_status == "FAILED"
        assert row.logical_provider_calls == 1
        assert "provider unavailable" in row.error_message
        assert not row.candidate_id
    finally:
        session.close()
        engine.dispose()

