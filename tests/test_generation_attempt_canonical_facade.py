from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import api.generation_attempt_canonical_api as facade
import api.generation_canary_api as canary
from core.generation_attempt_lineage import GenerationAttemptLineageService
from models import Base, GenerationExecutionRecord, StoryboardShot


@pytest.fixture()
def db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    monkeypatch.setattr(facade, "Session", lambda: session)
    monkeypatch.setattr(canary, "Session", lambda: session)
    yield session
    session.close()


def _context(shot_id: int):
    return {
        "row": SimpleNamespace(id=shot_id),
        "payload": {
            "generation_payload_fingerprint": "payload-current",
            "prompt_ir_ref": {"plan_shot_id": "plan-1"},
            "generation_policy": {"fingerprint": "policy", "mode": "TEXT_TO_IMAGE", "target_media": "IMAGE"},
            "request": {"prompt": "locked", "mode": "TEXT_TO_IMAGE", "target_media": "IMAGE", "reference_bindings": []},
        },
        "policy": {"fingerprint": "policy", "mode": "TEXT_TO_IMAGE"},
        "resolved": {"version": SimpleNamespace(id=1, payload_hash="prompt-hash"), "authority": SimpleNamespace(id=2)},
        "profile": {"id": "builtin-mock-image", "provider": "prototype-task-adapter", "model_name": "mock-image", "phase_j3_canonical": True},
        "profile_fingerprint": "profile-fp",
        "adapter": {"adapter_id": "prototype-task-adapter.image.v1", "adapter_version": "v1"},
        "request_snapshot": {"target_media": "IMAGE", "generation_mode": "TEXT_TO_IMAGE", "prompt": "locked", "reference_bindings": []},
        "provider_request_fingerprint": "base-request-fp",
        "target_media": "IMAGE",
        "reference_bindings_fingerprint": "",
        "asset_bindings_fingerprint": "",
    }


def _source(session, shot_id: int):
    row = GenerationExecutionRecord(
        execution_id="failed-source", schema_version="test", book_id=1, episode=1, storyboard_shot_id=shot_id,
        plan_shot_id="", execution_mode="CANARY", status="FAILED", target_media="IMAGE",
        prompt_ir_version_id=1, prompt_ir_authority_id=2, prompt_ir_payload_hash="prompt-hash",
        generation_payload_fingerprint="old", generation_policy_fingerprint="policy", model_profile_id="builtin-mock-image",
        model_profile_fingerprint="profile-fp", provider_adapter_id="prototype-task-adapter.image.v1", provider_adapter_version="v1",
        reference_bindings_fingerprint="", provider_request_fingerprint="base-request-fp", request_snapshot_json="{}",
        provider="", model="",
    )
    session.add(row)
    session.commit()
    return row


def test_retry_preview_binds_attempt_without_provider_or_candidate(db, monkeypatch):
    shot = StoryboardShot(book_id=1, episode=1, shot_id=101, scene_name="scene")
    db.add(shot)
    db.flush()
    _source(db, shot.id)
    service = GenerationAttemptLineageService(db)
    attempt = service.create_retry_intent(source_execution_id="failed-source", operation_idempotency_key="retry-1")
    db.commit()
    context = _context(shot.id)
    monkeypatch.setattr(facade, "_resolve_canonical_execution_inputs", lambda *args, **kwargs: context)
    result = facade.preview_generation_attempt(
        1, 1, 101, attempt.attempt_lineage_id,
        facade.AttemptPreviewRequest(attempt_confirmation_token=service.build_confirmation(attempt.attempt_lineage_id)),
    )
    assert result["provider_calls"] == 0
    assert result["execution"]["status"] == "PREVIEWED"
    assert result["attempt"]["status"] == "BOUND"
    assert result["candidate"] is None
    assert result["execution"]["provider_request_fingerprint"] != context["provider_request_fingerprint"]


def test_retry_execute_uses_canonical_executor_and_writes_candidate_only(db, monkeypatch):
    shot = StoryboardShot(book_id=1, episode=1, shot_id=101, scene_name="scene")
    db.add(shot)
    db.flush()
    _source(db, shot.id)
    service = GenerationAttemptLineageService(db)
    attempt = service.create_retry_intent(source_execution_id="failed-source", operation_idempotency_key="retry-2")
    db.commit()
    context = _context(shot.id)
    monkeypatch.setattr(facade, "_resolve_canonical_execution_inputs", lambda *args, **kwargs: context)
    monkeypatch.setattr(canary, "_resolve_canonical_execution_inputs", lambda *args, **kwargs: context)
    monkeypatch.setattr(canary, "_persist_candidate_media", lambda **kwargs: {
        "storage_identity": "local://image", "storage_reference": {"image_url": "local://image"},
        "checksum_sha256": "checksum", "mime_type": "image/png", "byte_size": 1,
        "width": 1, "height": 1, "duration_ms": None,
    })
    confirmation = service.build_confirmation(attempt.attempt_lineage_id)
    preview = facade.preview_generation_attempt(1, 1, 101, attempt.attempt_lineage_id, facade.AttemptPreviewRequest(attempt_confirmation_token=confirmation))
    request = facade.AttemptExecuteRequest(
        execute=True, confirmed=True, allowExternalCall=True,
        attemptConfirmationToken=confirmation,
        previewExecutionId=preview["execution"]["execution_id"],
        executionConfirmationToken=preview["execution_confirmation_token"],
    )
    result = asyncio.run(facade.execute_generation_attempt(1, 1, 101, attempt.attempt_lineage_id, request))
    assert result["execution"]["status"] == "SUCCEEDED"
    assert result["candidate"]["status"] == "MEDIA_CANDIDATE"
    assert result["execution"]["official_promotion_count"] == 0


def test_attempt_execute_requires_all_confirmation_flags(db):
    with pytest.raises(HTTPException) as exc:
        asyncio.run(facade.execute_generation_attempt(1, 1, 101, "gat-missing", facade.AttemptExecuteRequest(execute=True, confirmed=False, allowExternalCall=True, attemptConfirmationToken="x", previewExecutionId="x", executionConfirmationToken="x")))
    assert exc.value.detail["code"] == "GENERATION_ATTEMPT_EXECUTE_CONFIRMATION_REQUIRED"\n