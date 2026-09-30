from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import api.generation_attempt_canonical_api as facade
import api.generation_canary_api as canary
from core.generation_attempt_lineage import GenerationAttemptLineageService
from models import (
    Base,
    GenerationExecutionAttemptLineage,
    GenerationExecutionRecord,
    MediaCandidateRecord,
    OfficialMediaPointer,
    OfficialMediaVersion,
    StoryboardShot,
)


@pytest.fixture()
def db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    monkeypatch.setattr(facade, "Session", lambda: session)
    monkeypatch.setattr(canary, "Session", lambda: session)
    yield session
    session.close()


def _context(shot_id: int, *, target_media: str = "IMAGE", generation_mode: str = "TEXT_TO_IMAGE", provider_request_fingerprint: str = "base-request-fp"):
    is_video = target_media == "VIDEO"
    return {
        "row": SimpleNamespace(id=shot_id),
        "payload": {
            "generation_payload_fingerprint": "payload-current",
            "prompt_ir_ref": {"plan_shot_id": "plan-1"},
            "generation_policy": {"fingerprint": "policy", "mode": generation_mode, "target_media": target_media, **({"duration_seconds": 1} if is_video else {})},
            "request": {"prompt": "locked", "motion_prompt": "locked-motion" if is_video else "", "mode": generation_mode, "target_media": target_media, "reference_bindings": [], **({"duration_seconds": 1, "aspect_ratio": None, "resolution": None} if is_video else {})},
        },
        "policy": {"fingerprint": "policy", "mode": generation_mode, "target_media": target_media, **({"duration_seconds": 1} if is_video else {})},
        "resolved": {"version": SimpleNamespace(id=1, payload_hash="prompt-hash"), "authority": SimpleNamespace(id=2)},
        "profile": {"id": "builtin-mock-video" if is_video else "builtin-mock-image", "provider": "prototype-task-adapter", "model_name": "mock-video" if is_video else "mock-image", "phase_j3_canonical": True},
        "profile_fingerprint": "profile-fp",
        "adapter": {"adapter_id": "prototype-task-adapter.video.v1" if is_video else "prototype-task-adapter.image.v1", "adapter_version": "v1"},
        "request_snapshot": {"target_media": target_media, "generation_mode": generation_mode, "prompt": "locked", "motion_prompt": "locked-motion" if is_video else "", "reference_bindings": [], **({"duration_seconds": 1, "aspect_ratio": None, "resolution": None} if is_video else {})},
        "provider_request_fingerprint": provider_request_fingerprint,
        "target_media": target_media,
        "reference_bindings_fingerprint": "",
        "asset_bindings_fingerprint": "",
    }


def _source(session, shot_id: int, *, execution_id: str = "failed-source", status: str = "FAILED", target_media: str = "IMAGE", provider_request_fingerprint: str = "base-request-fp", generation_mode: str = "TEXT_TO_IMAGE"):
    row = GenerationExecutionRecord(
        execution_id=execution_id, schema_version="test", book_id=1, episode=1, storyboard_shot_id=shot_id,
        plan_shot_id="", execution_mode="CANARY", status=status, target_media=target_media,
        prompt_ir_version_id=1, prompt_ir_authority_id=2, prompt_ir_payload_hash="prompt-hash",
        generation_payload_fingerprint="old", generation_policy_fingerprint="policy", model_profile_id="builtin-mock-video" if target_media == "VIDEO" else "builtin-mock-image",
        model_profile_fingerprint="profile-fp", provider_adapter_id="prototype-task-adapter.image.v1", provider_adapter_version="v1",
        reference_bindings_fingerprint="", provider_request_fingerprint=provider_request_fingerprint,
        request_snapshot_json=json.dumps({"generation_mode": generation_mode, "target_media": target_media}),
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
    assert exc.value.detail["code"] == "GENERATION_ATTEMPT_EXECUTE_CONFIRMATION_REQUIRED"


def _bind_official_source(session, *, shot_id: int, execution_id: str = "official-source", media: str = "IMAGE"):
    candidate_id = f"candidate-{media.lower()}-source"
    role = "SHOT_PRIMARY_IMAGE" if media == "IMAGE" else "SHOT_PRIMARY_VIDEO"
    candidate = MediaCandidateRecord(
        candidate_id=candidate_id, execution_id=execution_id, status="MEDIA_CANDIDATE", media_type=media,
        storage_identity=f"fixture://{media.lower()}-source", storage_reference_json="{}", metadata_json="{}",
        checksum_sha256="checksum", mime_type="image/png" if media == "IMAGE" else "video/mp4", byte_size=1,
        width=1, height=1, duration_ms=None if media == "IMAGE" else 1000, prompt_ir_version_id=1,
        prompt_ir_payload_hash="prompt-hash", generation_payload_fingerprint="old", model_profile_id="builtin-mock-image" if media == "IMAGE" else "builtin-mock-video",
        model_profile_fingerprint="profile-fp", provider_request_fingerprint="base-request-fp", provider_response_hash="response",
    )
    official = OfficialMediaVersion(
        official_media_version_id=f"official-{media.lower()}", book_id=1, episode=1, storyboard_shot_id=shot_id,
        plan_shot_id="plan-1", media_role=role, media_type=media, candidate_id=candidate_id, candidate_fingerprint="candidate-fp",
        storage_identity=candidate.storage_identity, checksum_sha256="checksum", mime_type=candidate.mime_type, byte_size=1,
        width=1, height=1, duration_ms=candidate.duration_ms, prompt_ir_version_id=1, prompt_ir_payload_hash="prompt-hash",
        generation_payload_fingerprint="old", provider_request_fingerprint="base-request-fp", provider_response_hash="response",
        validation_id="validation", validation_fingerprint="validation-fp", revision=1, status="CURRENT", payload_hash="official-payload",
    )
    pointer = OfficialMediaPointer(
        book_id=1, episode=1, storyboard_shot_id=shot_id, media_role=role,
        official_media_version_id=official.official_media_version_id, authority_id=f"authority-{media.lower()}", fingerprint="pointer-fp",
    )
    session.add_all([candidate, official, pointer])
    session.commit()


def _patch_execution_runtime(monkeypatch, context, *, media: str):
    monkeypatch.setattr(facade, "_resolve_canonical_execution_inputs", lambda *args, **kwargs: context)
    monkeypatch.setattr(canary, "_resolve_canonical_execution_inputs", lambda *args, **kwargs: context)
    if media == "IMAGE":
        monkeypatch.setattr(canary, "_persist_candidate_media", lambda **kwargs: {
            "storage_identity": "local://attempt-image", "storage_reference": {"image_url": "local://attempt-image"},
            "checksum_sha256": "checksum-new", "mime_type": "image/png", "byte_size": 1,
            "width": 1, "height": 1, "duration_ms": None,
        })
    else:
        monkeypatch.setattr(canary, "_persist_candidate_media", lambda **kwargs: {
            "storage_identity": "local://attempt-video", "storage_reference": {"video_url": "local://attempt-video"},
            "checksum_sha256": "checksum-new-video", "mime_type": "video/mp4", "byte_size": 1,
            "width": 1, "height": 1, "duration_ms": 1000,
        })


@pytest.mark.parametrize(
    ("media", "mode"),
    [("IMAGE", "TEXT_TO_IMAGE"), ("VIDEO", "TEXT_TO_VIDEO")],
)
def test_retry_preview_and_execute_supports_image_and_video_without_official_write(db, monkeypatch, media, mode):
    shot = StoryboardShot(book_id=1, episode=1, shot_id=101, scene_name="scene")
    db.add(shot)
    db.flush()
    _source(db, shot.id, target_media=media, provider_request_fingerprint="base-request-fp", generation_mode=mode)
    service = GenerationAttemptLineageService(db)
    attempt = service.create_retry_intent(source_execution_id="failed-source", operation_idempotency_key=f"retry-{media.lower()}")
    db.commit()
    context = _context(shot.id, target_media=media, generation_mode=mode)
    _patch_execution_runtime(monkeypatch, context, media=media)
    confirmation = service.build_confirmation(attempt.attempt_lineage_id)
    preview = facade.preview_generation_attempt(1, 1, 101, attempt.attempt_lineage_id, facade.AttemptPreviewRequest(attempt_confirmation_token=confirmation))
    assert preview["execution"]["status"] == "PREVIEWED"
    request = facade.AttemptExecuteRequest(
        execute=True, confirmed=True, allowExternalCall=True,
        attemptConfirmationToken=confirmation, previewExecutionId=preview["execution"]["execution_id"],
        executionConfirmationToken=preview["execution_confirmation_token"],
    )
    result = asyncio.run(facade.execute_generation_attempt(1, 1, 101, attempt.attempt_lineage_id, request))
    assert result["execution"]["status"] == "SUCCEEDED"
    assert result["candidate"]["media_type"] == media
    assert result["execution"]["official_promotion_count"] == 0


@pytest.mark.parametrize("media", ["IMAGE", "VIDEO"])
def test_regenerate_preview_execute_keeps_current_official_and_creates_new_candidate(db, monkeypatch, media):
    shot = StoryboardShot(book_id=1, episode=1, shot_id=101, scene_name="scene")
    db.add(shot)
    db.flush()
    durable_shot_id = shot.id
    mode = "TEXT_TO_IMAGE" if media == "IMAGE" else "TEXT_TO_VIDEO"
    _source(db, durable_shot_id, execution_id="official-source", status="SUCCEEDED", target_media=media, provider_request_fingerprint="base-request-fp", generation_mode=mode)
    _bind_official_source(db, shot_id=durable_shot_id, execution_id="official-source", media=media)
    service = GenerationAttemptLineageService(db)
    official_id = f"official-{media.lower()}"
    attempt = service.create_regenerate_intent(source_official_media_version_id=official_id, operation_idempotency_key=f"reg-{media.lower()}")
    attempt_id = attempt.attempt_lineage_id
    db.commit()
    context = _context(durable_shot_id, target_media=media, generation_mode=mode)
    _patch_execution_runtime(monkeypatch, context, media=media)
    confirmation = service.build_confirmation(attempt_id)
    preview = facade.preview_generation_attempt(1, 1, 101, attempt_id, facade.AttemptPreviewRequest(attempt_confirmation_token=confirmation))
    request = facade.AttemptExecuteRequest(
        execute=True, confirmed=True, allowExternalCall=True,
        attemptConfirmationToken=confirmation, previewExecutionId=preview["execution"]["execution_id"],
        executionConfirmationToken=preview["execution_confirmation_token"],
    )
    result = asyncio.run(facade.execute_generation_attempt(1, 1, 101, attempt_id, request))
    assert result["candidate"]["media_type"] == media
    pointer = db.query(OfficialMediaPointer).filter_by(storyboard_shot_id=durable_shot_id, media_role=("SHOT_PRIMARY_IMAGE" if media == "IMAGE" else "SHOT_PRIMARY_VIDEO")).one()
    assert pointer.official_media_version_id == official_id
    assert db.query(OfficialMediaVersion).filter_by(official_media_version_id=official_id).one().status == "CURRENT"


def test_retry_preview_is_idempotent_and_bound_replay_does_not_require_source_freshness(db, monkeypatch):
    shot = StoryboardShot(book_id=1, episode=1, shot_id=101, scene_name="scene")
    db.add(shot)
    db.flush()
    _source(db, shot.id)
    service = GenerationAttemptLineageService(db)
    attempt = service.create_retry_intent(source_execution_id="failed-source", operation_idempotency_key="retry-idempotent")
    db.commit()
    context = _context(shot.id)
    monkeypatch.setattr(facade, "_resolve_canonical_execution_inputs", lambda *args, **kwargs: context)
    confirmation = service.build_confirmation(attempt.attempt_lineage_id)
    first = facade.preview_generation_attempt(1, 1, 101, attempt.attempt_lineage_id, facade.AttemptPreviewRequest(attempt_confirmation_token=confirmation))
    source = db.query(GenerationExecutionRecord).filter_by(execution_id="failed-source").one()
    source.status = "SUCCEEDED"
    db.commit()
    second = facade.preview_generation_attempt(1, 1, 101, attempt.attempt_lineage_id, facade.AttemptPreviewRequest(attempt_confirmation_token=confirmation))
    assert second["execution"]["execution_id"] == first["execution"]["execution_id"]
    assert second["execution_created"] is False
    assert db.query(GenerationExecutionRecord).count() == 2


def test_source_stale_and_cancelled_attempt_create_no_execution(db, monkeypatch):
    shot = StoryboardShot(book_id=1, episode=1, shot_id=101, scene_name="scene")
    db.add(shot)
    db.flush()
    _source(db, shot.id)
    service = GenerationAttemptLineageService(db)
    stale = service.create_retry_intent(source_execution_id="failed-source", operation_idempotency_key="retry-stale")
    cancelled = service.create_retry_intent(source_execution_id="failed-source", operation_idempotency_key="retry-cancelled")
    stale_id = stale.attempt_lineage_id
    cancelled_id = cancelled.attempt_lineage_id
    cancelled.status = "CANCELLED"
    db.commit()
    context = _context(shot.id, provider_request_fingerprint="changed-current")
    monkeypatch.setattr(facade, "_resolve_canonical_execution_inputs", lambda *args, **kwargs: context)
    stale_token = service.build_confirmation(stale_id)
    with pytest.raises(HTTPException) as stale_error:
        facade.preview_generation_attempt(1, 1, 101, stale_id, facade.AttemptPreviewRequest(attempt_confirmation_token=stale_token))
    assert stale_error.value.detail["code"] == "GENERATION_ATTEMPT_SOURCE_STALE"
    cancelled_token = service.build_confirmation(cancelled_id)
    with pytest.raises(HTTPException) as cancelled_error:
        facade.preview_generation_attempt(1, 1, 101, cancelled_id, facade.AttemptPreviewRequest(attempt_confirmation_token=cancelled_token))
    assert cancelled_error.value.detail["code"] == "GENERATION_ATTEMPT_CANCELLED"
    assert db.query(GenerationExecutionRecord).count() == 1


def test_retry_of_retry_restores_base_fingerprint_and_root(db, monkeypatch):
    shot = StoryboardShot(book_id=1, episode=1, shot_id=101, scene_name="scene")
    db.add(shot)
    db.flush()
    _source(db, shot.id)
    service = GenerationAttemptLineageService(db)
    first = service.create_retry_intent(source_execution_id="failed-source", operation_idempotency_key="retry-root-1")
    db.commit()
    context = _context(shot.id)
    monkeypatch.setattr(facade, "_resolve_canonical_execution_inputs", lambda *args, **kwargs: context)
    token = service.build_confirmation(first.attempt_lineage_id)
    preview = facade.preview_generation_attempt(1, 1, 101, first.attempt_lineage_id, facade.AttemptPreviewRequest(attempt_confirmation_token=token))
    produced = db.query(GenerationExecutionRecord).filter_by(execution_id=preview["execution"]["execution_id"]).one()
    produced.status = "FAILED"
    db.commit()
    second = service.create_retry_intent(source_execution_id=produced.execution_id, operation_idempotency_key="retry-root-2")
    db.commit()
    assert second.root_execution_id == first.root_execution_id
    assert second.attempt_number == first.attempt_number + 1
    second_token = service.build_confirmation(second.attempt_lineage_id)
    second_preview = facade.preview_generation_attempt(1, 1, 101, second.attempt_lineage_id, facade.AttemptPreviewRequest(attempt_confirmation_token=second_token))
    assert second_preview["execution"]["provider_request_fingerprint"] != preview["execution"]["provider_request_fingerprint"]


def test_execute_failure_is_bound_and_requires_new_business_retry(db, monkeypatch):
    shot = StoryboardShot(book_id=1, episode=1, shot_id=101, scene_name="scene")
    db.add(shot)
    db.flush()
    _source(db, shot.id)
    service = GenerationAttemptLineageService(db)
    attempt = service.create_retry_intent(source_execution_id="failed-source", operation_idempotency_key="retry-failure")
    attempt_id = attempt.attempt_lineage_id
    db.commit()
    context = _context(shot.id)
    _patch_execution_runtime(monkeypatch, context, media="IMAGE")
    async def provider_failure(**_kwargs):
        raise HTTPException(status_code=502, detail={"code": "MOCK_PROVIDER_FAILURE", "message": "fixture failure"})
    monkeypatch.setattr(canary, "_call_provider", provider_failure)
    confirmation = service.build_confirmation(attempt_id)
    preview = facade.preview_generation_attempt(1, 1, 101, attempt_id, facade.AttemptPreviewRequest(attempt_confirmation_token=confirmation))
    request = facade.AttemptExecuteRequest(
        execute=True, confirmed=True, allowExternalCall=True,
        attemptConfirmationToken=confirmation, previewExecutionId=preview["execution"]["execution_id"],
        executionConfirmationToken=preview["execution_confirmation_token"],
    )
    with pytest.raises(HTTPException) as first_error:
        asyncio.run(facade.execute_generation_attempt(1, 1, 101, attempt_id, request))
    assert first_error.value.detail["code"] == "MOCK_PROVIDER_FAILURE"
    produced = db.query(GenerationExecutionRecord).filter_by(execution_id=preview["execution"]["execution_id"]).one()
    assert produced.status == "FAILED"
    assert db.query(GenerationExecutionAttemptLineage).filter_by(attempt_lineage_id=attempt_id).one().status == "BOUND"
    with pytest.raises(HTTPException) as replay_error:
        asyncio.run(facade.execute_generation_attempt(1, 1, 101, attempt_id, request))
    assert replay_error.value.detail["code"] == "GENERATION_CANARY_FAILED_REQUIRES_NEW_CONFIRMATION"


def test_execute_success_replay_is_idempotent_without_second_provider_call(db, monkeypatch):
    shot = StoryboardShot(book_id=1, episode=1, shot_id=101, scene_name="scene")
    db.add(shot)
    db.flush()
    _source(db, shot.id)
    service = GenerationAttemptLineageService(db)
    attempt = service.create_retry_intent(source_execution_id="failed-source", operation_idempotency_key="retry-replay")
    attempt_id = attempt.attempt_lineage_id
    db.commit()
    context = _context(shot.id)
    _patch_execution_runtime(monkeypatch, context, media="IMAGE")
    calls = []
    original_provider = canary._call_provider
    async def counting_provider(**kwargs):
        calls.append(1)
        return await original_provider(**kwargs)
    monkeypatch.setattr(canary, "_call_provider", counting_provider)
    confirmation = service.build_confirmation(attempt_id)
    preview = facade.preview_generation_attempt(1, 1, 101, attempt_id, facade.AttemptPreviewRequest(attempt_confirmation_token=confirmation))
    request = facade.AttemptExecuteRequest(
        execute=True, confirmed=True, allowExternalCall=True,
        attemptConfirmationToken=confirmation, previewExecutionId=preview["execution"]["execution_id"],
        executionConfirmationToken=preview["execution_confirmation_token"],
    )
    first = asyncio.run(facade.execute_generation_attempt(1, 1, 101, attempt_id, request))
    second = asyncio.run(facade.execute_generation_attempt(1, 1, 101, attempt_id, request))
    assert first["execution"]["execution_id"] == second["execution"]["execution_id"]
    assert first["candidate"]["candidate_id"] == second["candidate"]["candidate_id"]
    assert len(calls) == 1


def test_v2_projection_exposes_attempt_candidate_and_review_action(db, monkeypatch):
    shot = StoryboardShot(book_id=1, episode=1, shot_id=101, scene_name="scene")
    db.add(shot)
    db.flush()
    durable_shot_id = shot.id
    _source(db, durable_shot_id)
    service = GenerationAttemptLineageService(db)
    attempt = service.create_retry_intent(source_execution_id="failed-source", operation_idempotency_key="retry-v2")
    attempt_id = attempt.attempt_lineage_id
    db.commit()
    context = _context(durable_shot_id)
    _patch_execution_runtime(monkeypatch, context, media="IMAGE")
    confirmation = service.build_confirmation(attempt_id)
    preview = facade.preview_generation_attempt(1, 1, 101, attempt_id, facade.AttemptPreviewRequest(attempt_confirmation_token=confirmation))
    request = facade.AttemptExecuteRequest(
        execute=True, confirmed=True, allowExternalCall=True,
        attemptConfirmationToken=confirmation, previewExecutionId=preview["execution"]["execution_id"],
        executionConfirmationToken=preview["execution_confirmation_token"],
    )
    result = asyncio.run(facade.execute_generation_attempt(1, 1, 101, attempt_id, request))
    import core.production_workspace_projection_v2 as projection
    monkeypatch.setattr(projection, "build_production_workspace_projection", lambda *args, **kwargs: {
        "project": {}, "stages": {}, "episodes": [], "assets": [],
        "shots": [{"book_id": 1, "episode": 1, "shot_id": 101, "storyboard_shot_id": durable_shot_id, "plan_shot_id": "plan-1", "scene_id": "scene-1", "duration": 1, "camera": {}, "action": ""}],
    })
    monkeypatch.setattr(projection, "_asset_readiness", lambda *args, **kwargs: {"state": "ready", "required": {}, "required_entities": [], "missing": [], "stale": [], "current": True, "required_entity_count": 0, "requirement_source": "test"})
    monkeypatch.setattr(projection, "_prompt_lane", lambda *args, **kwargs: {"current": True, "version": 1, "stale": False, "state": "complete", "payload_hash": "prompt-hash", "generation_policy": {"mode": "TEXT_TO_IMAGE", "target_media": "IMAGE"}, "reason_codes": []})
    monkeypatch.setattr(projection, "_official_projection", lambda *args, **kwargs: {"current": True, "currentness": "current", "version": {"id": "official-old", "candidate_id": "candidate-old"}, "authority": {"id": "authority-old"}, "pointer": {"official_media_version_id": "official-old"}, "preview": None, "preview_url": None})
    projected = projection.build_production_workspace_projection_v2(db, book_id=1, generation_profile_selection={"IMAGE": "builtin-mock-image"})
    lane = projected["shots"][0]["IMAGE"]
    assert lane["latest_execution"]["id"] == result["execution"]["execution_id"]
    assert lane["candidates"]["count"] == 1
    assert lane["official"]["current"] is True
    assert projected["shots"][0]["next_action"]["key"] == "REVIEW_IMAGE_CANDIDATE"


def test_regenerate_from_regenerate_restores_base_fingerprint_metadata(db, monkeypatch):
    shot = StoryboardShot(book_id=1, episode=1, shot_id=101, scene_name="scene")
    db.add(shot)
    db.flush()
    durable_shot_id = shot.id
    _source(db, durable_shot_id, execution_id="official-source", status="SUCCEEDED", target_media="IMAGE", provider_request_fingerprint="base-request-fp", generation_mode="TEXT_TO_IMAGE")
    _bind_official_source(db, shot_id=durable_shot_id, execution_id="official-source", media="IMAGE")
    service = GenerationAttemptLineageService(db)
    first = service.create_regenerate_intent(source_official_media_version_id="official-image", operation_idempotency_key="regenerate-chain-1")
    first_id = first.attempt_lineage_id
    db.commit()
    context = _context(durable_shot_id)
    _patch_execution_runtime(monkeypatch, context, media="IMAGE")
    confirmation = service.build_confirmation(first_id)
    preview = facade.preview_generation_attempt(1, 1, 101, first_id, facade.AttemptPreviewRequest(attempt_confirmation_token=confirmation))
    request = facade.AttemptExecuteRequest(
        execute=True, confirmed=True, allowExternalCall=True,
        attemptConfirmationToken=confirmation, previewExecutionId=preview["execution"]["execution_id"],
        executionConfirmationToken=preview["execution_confirmation_token"],
    )
    result = asyncio.run(facade.execute_generation_attempt(1, 1, 101, first_id, request))
    produced_id = result["execution"]["execution_id"]
    produced = db.query(GenerationExecutionRecord).filter_by(execution_id=produced_id).one()
    produced_candidate = db.query(MediaCandidateRecord).filter_by(execution_id=produced_id).one()
    produced_provider_request_fingerprint = produced.provider_request_fingerprint
    official_v2 = OfficialMediaVersion(
        official_media_version_id="official-image-v2", book_id=1, episode=1, storyboard_shot_id=durable_shot_id,
        plan_shot_id="plan-1", media_role="SHOT_PRIMARY_IMAGE", media_type="IMAGE", candidate_id=produced_candidate.candidate_id,
        candidate_fingerprint="candidate-v2", storage_identity=produced_candidate.storage_identity, checksum_sha256="checksum-new",
        mime_type="image/png", byte_size=1, width=1, height=1, prompt_ir_version_id=1, prompt_ir_payload_hash="prompt-hash",
        generation_payload_fingerprint=produced.generation_payload_fingerprint, provider_request_fingerprint=produced.provider_request_fingerprint,
        provider_response_hash=produced.provider_response_hash, validation_id="validation-v2", validation_fingerprint="validation-fp-v2",
        revision=2, status="CURRENT", payload_hash="official-payload-v2",
    )
    pointer = db.query(OfficialMediaPointer).filter_by(storyboard_shot_id=durable_shot_id, media_role="SHOT_PRIMARY_IMAGE").one()
    pointer.official_media_version_id = "official-image-v2"
    db.add(official_v2)
    db.commit()
    second = service.create_regenerate_intent(source_official_media_version_id="official-image-v2", operation_idempotency_key="regenerate-chain-2")
    second_id = second.attempt_lineage_id
    db.commit()
    second_token = service.build_confirmation(second_id)
    second_preview = facade.preview_generation_attempt(1, 1, 101, second_id, facade.AttemptPreviewRequest(attempt_confirmation_token=second_token))
    assert second_preview["execution"]["provider_request_fingerprint"] != produced_provider_request_fingerprint
    lineage = json.loads(db.query(GenerationExecutionRecord).filter_by(execution_id=second_preview["execution"]["execution_id"]).one().request_snapshot_json)["_generation_attempt"]
    assert lineage["base_provider_request_fingerprint"] == "base-request-fp"
