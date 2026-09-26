"""Provider-free Generation Execution Foundation contract tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.generation_execution_service import (
    GenerationExecutionError,
    GenerationExecutionService,
)
from models import PromptIRPointer, PromptIRVersion, Session, StoryboardShot
from scripts.verify_migration_chain import _upgrade


def _session(tmp_path: Path):
    db = tmp_path / "generation-execution-foundation.sqlite"
    _upgrade(db)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    return engine, sessionmaker(bind=engine)()


def _fixture(session, *, business_shot_id: int = 7001):
    shot = StoryboardShot(
        book_id=970001,
        episode=1,
        scene_name="FOUNDATION_SCENE",
        scene_id="FOUNDATION_SCENE",
        plan_shot_id="FOUNDATION_SHOT",
        shot_id=business_shot_id,
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
        schema_version="prompt_ir_test_v1",
        payload_json='{"generation_policy":{"target_media":"IMAGE"}}',
        payload_hash="sha256:foundation-prompt",
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
    return shot, version, pointer


def test_entity_creation_and_required_foundation_fields(tmp_path: Path):
    engine, session = _session(tmp_path)
    try:
        shot, version, pointer = _fixture(session)
        service = GenerationExecutionService(session)
        row = service.create_execution(
            shot_id=shot.id,
            prompt_pointer_id=pointer.id,
            prompt_version_id=version.id,
            model_profile_id="foundation-test-profile",
        )
        session.commit()

        assert row.execution_id.startswith("gex_")
        assert row.status == "CREATED"
        assert row.execution_status == "CREATED"
        assert row.shot_id == shot.id
        assert row.prompt_pointer_id == pointer.id
        assert row.prompt_version_id == version.id
        assert row.model_profile_id == "foundation-test-profile"
        assert row.request_payload["provider_calls"] == 0
        assert row.response_payload == {}
        assert row.error_message == ""
        assert row.retry_count == 0
        assert row.created_at is not None
        assert row.started_at is None
        assert row.completed_at is None
        assert row.logical_provider_calls == 0
    finally:
        session.close()
        engine.dispose()


def test_state_machine_accepts_required_transitions_and_rejects_terminal_reentry(tmp_path: Path):
    engine, session = _session(tmp_path)
    try:
        shot, version, pointer = _fixture(session, business_shot_id=7002)
        service = GenerationExecutionService(session)
        row = service.create_execution(
            shot_id=shot.shot_id,
            prompt_pointer_id=pointer.id,
            prompt_version_id=version.id,
            model_profile_id="foundation-test-profile",
        )
        service.transition(row.execution_id, "QUEUED")
        service.transition(row.execution_id, "RUNNING")
        service.transition(row.execution_id, "SUCCESS", response_payload={"provider_calls": 0})
        session.commit()
        assert row.execution_status == "SUCCESS"
        assert row.started_at is not None
        assert row.completed_at is not None
        assert row.response_payload["provider_calls"] == 0

        with pytest.raises(GenerationExecutionError) as exc_info:
            service.transition(row.execution_id, "RUNNING")
        assert exc_info.value.code == "GENERATION_EXECUTION_TRANSITION_INVALID"
    finally:
        session.close()
        engine.dispose()


def test_failed_retry_cycle_returns_to_queue_and_counts_retry(tmp_path: Path):
    engine, session = _session(tmp_path)
    try:
        shot, version, pointer = _fixture(session, business_shot_id=7003)
        service = GenerationExecutionService(session)
        row = service.create_execution(
            shot_id=shot.id,
            prompt_pointer_id=pointer.id,
            prompt_version_id=version.id,
            model_profile_id="foundation-test-profile",
        )
        service.transition(row.execution_id, "QUEUED")
        service.transition(row.execution_id, "RUNNING")
        service.transition(row.execution_id, "FAILED", error_message="foundation failure")
        service.transition(row.execution_id, "RETRYING")
        service.transition(row.execution_id, "QUEUED")
        session.commit()
        assert row.execution_status == "QUEUED"
        assert row.error_message == "foundation failure"
        assert row.retry_count == 1
    finally:
        session.close()
        engine.dispose()


def test_api_contract_functions_create_and_query_execution(tmp_path: Path, monkeypatch):
    engine, session = _session(tmp_path)
    try:
        shot, version, pointer = _fixture(session, business_shot_id=7004)
        api_module = __import__("api.generation_execution_api", fromlist=["*"])
        monkeypatch.setattr(api_module, "Session", sessionmaker(bind=engine))
        request = api_module.CreateGenerationExecutionRequest(
            shot_id=shot.id,
            prompt_pointer_id=pointer.id,
            prompt_version_id=version.id,
            model_profile_id="foundation-api-profile",
        )
        created = api_module.create_execution(request)
        assert set(created) == {"execution_id", "status"}
        assert created["status"] == "CREATED"
        fetched = api_module.get_execution(created["execution_id"])
        assert fetched["execution_id"] == created["execution_id"]
        assert fetched["status"] == "CREATED"
        assert fetched["metadata"]["shot_id"] == shot.id
        assert fetched["metadata"]["prompt_pointer_id"] == pointer.id
    finally:
        session.close()
        engine.dispose()

