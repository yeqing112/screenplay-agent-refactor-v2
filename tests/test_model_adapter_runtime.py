"""Model Adapter Runtime and Generation Orchestrator contract tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.generation_execution_service import GenerationExecutionService
from core.generation_orchestrator import GenerationOrchestrator, GenerationOrchestratorError
from core.model_adapter_runtime import (
    ModelAdapterRegistry,
    MockAdapter,
    UnavailableProviderAdapter,
    build_default_adapter_registry,
)
from models import PromptIRPointer, PromptIRVersion, StoryboardShot
from scripts.verify_migration_chain import _upgrade


def _session(tmp_path: Path):
    db = tmp_path / "model-adapter-runtime.sqlite"
    _upgrade(db)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    return engine, sessionmaker(bind=engine)()


def _fixture(session, *, profile_id: str = "mock-runtime-profile", shot_id: int = 8801):
    shot = StoryboardShot(
        book_id=980001,
        episode=1,
        scene_name="RUNTIME_SCENE",
        scene_id="RUNTIME_SCENE",
        plan_shot_id="RUNTIME_SHOT",
        shot_id=shot_id,
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
        schema_version="prompt_ir_runtime_test_v1",
        payload_json='{"prompt":"a quiet cinematic room","generation_policy":{"target_media":"IMAGE"}}',
        payload_hash="sha256:runtime-prompt",
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
    row = GenerationExecutionService(session).create_execution(
        shot_id=shot.id,
        prompt_pointer_id=pointer.id,
        prompt_version_id=version.id,
        model_profile_id=profile_id,
    )
    session.commit()
    return shot, version, pointer, row


def _mock_profile(profile_id: str = "mock-runtime-profile"):
    return {
        "id": profile_id,
        "name": "Runtime Mock",
        "capability": "image",
        "provider": "prototype-task-adapter",
        "model_name": "mock-image-v1",
        "default_params": {"size": "1024x1024"},
        "enabled": True,
        "key_configured": True,
    }


def test_adapter_registry_selects_mock_and_never_creates_media(tmp_path: Path):
    registry = build_default_adapter_registry()
    adapter = registry.resolve("prototype-task-adapter")
    assert isinstance(adapter, MockAdapter)
    result = adapter.generate(_mock_profile(), {"prompt": "hello"}, {"size": "1024x1024"})
    assert result.status == "SUCCESS"
    assert result.provider_request["media_generated"] is False
    assert result.provider_response["mock"] is True
    assert result.logical_provider_calls == 1

    unavailable = registry.resolve("openai-compatible")
    assert isinstance(unavailable, UnavailableProviderAdapter)


def test_orchestrator_runs_execution_through_registry_and_persists_success(tmp_path: Path):
    engine, session = _session(tmp_path)
    try:
        _, _, _, row = _fixture(session)
        orchestrator = GenerationOrchestrator(
            session,
            adapter_registry=ModelAdapterRegistry({"prototype-task-adapter": MockAdapter()}),
            profile_resolver=lambda profile_id: _mock_profile(profile_id),
        )
        completed = orchestrator.run(row.execution_id, params={"seed": 7})
        session.commit()

        assert completed.execution_status == "SUCCESS"
        assert completed.provider == "prototype-task-adapter"
        assert completed.model == "mock-image-v1"
        assert completed.provider_request_id.startswith("mockreq_")
        assert completed.logical_provider_calls == 1
        assert completed.response_payload["status"] == "SUCCESS"
        assert completed.response_payload["provider_response"]["mock"] is True
        assert completed.request_payload["runtime"]["params"]["seed"] == 7
    finally:
        session.close()
        engine.dispose()


def test_orchestrator_provider_failure_persists_failed_execution(tmp_path: Path):
    engine, session = _session(tmp_path)
    try:
        _, _, _, row = _fixture(session, profile_id="mock-failure-profile", shot_id=8802)
        orchestrator = GenerationOrchestrator(
            session,
            adapter_registry=ModelAdapterRegistry({"prototype-task-adapter": MockAdapter()}),
            profile_resolver=lambda profile_id: _mock_profile(profile_id),
        )
        with pytest.raises(GenerationOrchestratorError) as exc_info:
            orchestrator.run(row.execution_id, params={"simulate_failure": True})
        session.commit()

        assert exc_info.value.code == "MOCK_PROVIDER_FAILURE"
        assert row.execution_status == "FAILED"
        assert row.error_message == "Mock provider failure requested by the execution test."
        assert row.logical_provider_calls == 1
    finally:
        session.close()
        engine.dispose()


def test_non_mock_provider_is_fail_closed_before_running(tmp_path: Path):
    engine, session = _session(tmp_path)
    try:
        _, _, _, row = _fixture(session, profile_id="future-flux-profile", shot_id=8803)
        profile = _mock_profile("future-flux-profile")
        profile.update({"provider": "flux", "model_name": "flux-pro"})
        orchestrator = GenerationOrchestrator(session, profile_resolver=lambda profile_id: profile)
        with pytest.raises(GenerationOrchestratorError) as exc_info:
            orchestrator.run(row.execution_id)
        assert exc_info.value.code == "MODEL_ADAPTER_PROVIDER_NOT_ENABLED"
        assert row.execution_status == "CREATED"
        assert row.logical_provider_calls == 0
    finally:
        session.close()
        engine.dispose()


def test_run_api_contract_updates_the_same_execution_record(tmp_path: Path, monkeypatch):
    engine, session = _session(tmp_path)
    try:
        _, _, _, row = _fixture(session, profile_id="api-runtime-profile", shot_id=8804)
        api_module = __import__("api.generation_execution_api", fromlist=["*"])
        orchestrator_module = __import__("core.generation_orchestrator", fromlist=["*"])
        monkeypatch.setattr(api_module, "Session", sessionmaker(bind=engine))
        monkeypatch.setattr(orchestrator_module, "get_profile", lambda profile_id: _mock_profile(profile_id))
        response = api_module.run_execution(
            row.execution_id,
            api_module.RunGenerationExecutionRequest(params={"seed": 11}),
        )
        assert response["execution_id"] == row.execution_id
        assert response["status"] == "SUCCESS"
        assert response["metadata"]["provider_calls"] == 1
    finally:
        session.close()
        engine.dispose()
