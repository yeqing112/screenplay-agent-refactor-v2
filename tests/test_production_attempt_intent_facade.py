from __future__ import annotations

import json

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import api.generation_attempt_canonical_api as facade
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
    yield session
    session.close()


def _execution(session, shot_id: int, execution_id: str, *, status: str = "FAILED", media: str = "IMAGE"):
    mode = "TEXT_TO_IMAGE" if media == "IMAGE" else "TEXT_TO_VIDEO"
    row = GenerationExecutionRecord(
        execution_id=execution_id,
        schema_version="test",
        book_id=1,
        episode=1,
        storyboard_shot_id=shot_id,
        plan_shot_id="plan-1",
        execution_mode="CANARY",
        status=status,
        target_media=media,
        prompt_ir_version_id=1,
        prompt_ir_authority_id=2,
        prompt_ir_payload_hash="prompt-hash",
        generation_payload_fingerprint="payload-fp",
        generation_policy_fingerprint="policy-fp",
        model_profile_id="builtin-mock-image" if media == "IMAGE" else "builtin-mock-video",
        model_profile_fingerprint="profile-fp",
        provider_adapter_id="prototype-task-adapter.v1",
        provider_adapter_version="v1",
        reference_bindings_fingerprint="",
        provider_request_fingerprint=f"request-{execution_id}",
        request_snapshot_json=json.dumps({"generation_mode": mode, "target_media": media}),
        provider="",
        model="",
    )
    session.add(row)
    session.flush()
    return row


def _lane(*, latest=None, official=None, candidates=None):
    return {
        "latest_execution": latest,
        "official": official or {"current": False, "currentness": "missing", "version": None},
        "candidates": {"count": len(candidates or []), "items": candidates or [], "latest": (candidates or [None])[0]},
    }


def _patch_lane(monkeypatch, session, shot, state):
    def resolve(_session, *, shot, target_media, selected_profile_id=None):
        latest = state.get("latest", {}).get(target_media)
        official = state.get("official", {}).get(target_media)
        candidates = state.get("candidates", {}).get(target_media, [])
        return _lane(latest=latest, official=official, candidates=candidates)

    monkeypatch.setattr(facade, "resolve_current_production_lane", resolve)


def _request(kind: str, media: str, key: str, **extra):
    return facade.CreateShotGenerationAttemptRequest(
        operationKind=kind,
        targetMedia=media,
        operationIdempotencyKey=key,
        **extra,
    )


def test_retry_uses_current_failed_lane_execution_and_replays_same_attempt(db, monkeypatch):
    shot = StoryboardShot(book_id=1, episode=1, shot_id=101, scene_name="scene")
    db.add(shot)
    db.flush()
    source = _execution(db, shot.id, "failed-current")
    newer = _execution(db, shot.id, "failed-newer")
    source_id, newer_id = source.execution_id, newer.execution_id
    db.commit()
    state = {"latest": {"IMAGE": {"id": source_id, "state": "FAILED"}}, "official": {}}
    _patch_lane(monkeypatch, db, shot, state)
    request = _request("RETRY", "IMAGE", "retry-intent-1", sourceExecutionId=source_id)
    first = facade.create_shot_generation_attempt(1, 1, 101, request)
    assert first["providerCalls"] == 0
    assert first["executionCreated"] is False
    assert db.query(GenerationExecutionAttemptLineage).count() == 1
    assert db.query(GenerationExecutionRecord).count() == 2
    state["latest"]["IMAGE"] = {"id": newer_id, "state": "FAILED"}
    replay = facade.create_shot_generation_attempt(1, 1, 101, request)
    assert replay["reused"] is True
    assert replay["attempt"]["attempt_lineage_id"] == first["attempt"]["attempt_lineage_id"]
    assert replay["attemptConfirmationToken"] == first["attemptConfirmationToken"]


def test_retry_rejects_old_or_non_failed_source(db, monkeypatch):
    shot = StoryboardShot(book_id=1, episode=1, shot_id=101, scene_name="scene")
    db.add(shot)
    db.flush()
    old = _execution(db, shot.id, "failed-old")
    current = _execution(db, shot.id, "failed-current")
    success = _execution(db, shot.id, "success-current", status="SUCCEEDED")
    old_id, current_id, success_id = old.execution_id, current.execution_id, success.execution_id
    db.commit()
    state = {"latest": {"IMAGE": {"id": current_id, "state": "FAILED"}}, "official": {}}
    _patch_lane(monkeypatch, db, shot, state)
    with pytest.raises(HTTPException) as exc:
        facade.create_shot_generation_attempt(1, 1, 101, _request("RETRY", "IMAGE", "retry-old", sourceExecutionId=old_id))
    assert exc.value.detail["code"] == "GENERATION_RETRY_SOURCE_NOT_CURRENT_LANE_EXECUTION"
    state["latest"]["IMAGE"] = {"id": success_id, "state": "SUCCEEDED"}
    with pytest.raises(HTTPException) as exc:
        facade.create_shot_generation_attempt(1, 1, 101, _request("RETRY", "IMAGE", "retry-success", sourceExecutionId=success_id))
    assert exc.value.detail["code"] == "GENERATION_RETRY_SOURCE_NOT_FAILED"


def _official_graph(session, shot_id: int, *, media: str = "IMAGE"):
    candidate_id = f"candidate-{media.lower()}-official"
    execution_id = f"execution-{media.lower()}-official"
    _execution(session, shot_id, execution_id, status="SUCCEEDED", media=media)
    candidate = MediaCandidateRecord(
        candidate_id=candidate_id,
        execution_id=execution_id,
        status="MEDIA_CANDIDATE",
        media_type=media,
        storage_identity=f"fixture://{media.lower()}",
        storage_reference_json="{}",
        metadata_json="{}",
        checksum_sha256="checksum",
        mime_type="image/png" if media == "IMAGE" else "video/mp4",
        byte_size=1,
        width=1,
        height=1,
        duration_ms=None if media == "IMAGE" else 1000,
        prompt_ir_version_id=1,
        prompt_ir_payload_hash="prompt-hash",
        generation_payload_fingerprint="payload-fp",
        model_profile_id="builtin-mock-image",
        model_profile_fingerprint="profile-fp",
        provider_request_fingerprint="request-official",
        provider_response_hash="response",
    )
    role = "SHOT_PRIMARY_IMAGE" if media == "IMAGE" else "SHOT_PRIMARY_VIDEO"
    official_id = f"official-{media.lower()}-1"
    official = OfficialMediaVersion(
        official_media_version_id=official_id,
        book_id=1,
        episode=1,
        storyboard_shot_id=shot_id,
        plan_shot_id="plan-1",
        media_role=role,
        media_type=media,
        candidate_id=candidate_id,
        candidate_fingerprint="candidate-fp",
        storage_identity=candidate.storage_identity,
        checksum_sha256="checksum",
        mime_type=candidate.mime_type,
        byte_size=1,
        width=1,
        height=1,
        duration_ms=candidate.duration_ms,
        prompt_ir_version_id=1,
        prompt_ir_payload_hash="prompt-hash",
        generation_payload_fingerprint="payload-fp",
        provider_request_fingerprint="request-official",
        provider_response_hash="response",
        validation_id="validation-1",
        validation_fingerprint="validation-fp",
        revision=1,
        status="CURRENT",
        payload_hash="official-payload",
    )
    pointer = OfficialMediaPointer(
        book_id=1,
        episode=1,
        storyboard_shot_id=shot_id,
        media_role=role,
        official_media_version_id=official_id,
        authority_id=f"authority-{media.lower()}",
        fingerprint="pointer-fp",
    )
    session.add_all([candidate, official, pointer])
    session.commit()
    return candidate, official


@pytest.mark.parametrize("media", ["IMAGE", "VIDEO"])
def test_regenerate_resolves_current_official_and_never_writes_execution(db, monkeypatch, media):
    shot = StoryboardShot(book_id=1, episode=1, shot_id=101, scene_name="scene")
    db.add(shot)
    db.flush()
    candidate, official = _official_graph(db, shot.id, media=media)
    official_id = official.official_media_version_id
    candidate_execution_id = candidate.execution_id
    state = {"latest": {media: {"id": candidate_execution_id, "state": "SUCCEEDED"}}, "official": {media: {"current": True, "currentness": "current", "version": {"id": official_id, "candidate_id": candidate.candidate_id}}}}
    _patch_lane(monkeypatch, db, shot, state)
    before_exec = db.query(GenerationExecutionRecord).count()
    result = facade.create_shot_generation_attempt(1, 1, 101, _request("REGENERATE", media, f"regenerate-{media.lower()}"))
    assert result["providerCalls"] == 0
    assert result["executionCreated"] is False
    assert result["attempt"]["source_official_media_version_id"] == official_id
    assert db.query(GenerationExecutionRecord).count() == before_exec
    assert db.query(MediaCandidateRecord).count() == 1
    assert db.query(OfficialMediaPointer).count() == 1


def test_regenerate_rejects_client_source_and_pending_or_active_lane(db, monkeypatch):
    shot = StoryboardShot(book_id=1, episode=1, shot_id=101, scene_name="scene")
    db.add(shot)
    db.flush()
    candidate, official = _official_graph(db, shot.id)
    official_id = official.official_media_version_id
    state = {"latest": {"IMAGE": {"id": candidate.execution_id, "state": "SUCCEEDED"}}, "official": {"IMAGE": {"current": True, "currentness": "current", "version": {"id": official_id, "candidate_id": candidate.candidate_id}}}, "candidates": {"IMAGE": []}}
    _patch_lane(monkeypatch, db, shot, state)
    with pytest.raises(HTTPException) as exc:
        facade.create_shot_generation_attempt(1, 1, 101, _request("REGENERATE", "IMAGE", "regenerate-client", sourceOfficialMediaVersionId=official_id))
    assert exc.value.detail["code"] == "GENERATION_REGENERATE_SOURCE_CLIENT_FORBIDDEN"
    pending_execution_id = "execution-pending"
    _execution(db, shot.id, pending_execution_id, status="SUCCEEDED")
    db.add(MediaCandidateRecord(
        candidate_id="candidate-pending",
        execution_id=pending_execution_id,
        status="MEDIA_CANDIDATE",
        media_type="IMAGE",
        storage_identity="fixture://pending",
        storage_reference_json="{}",
        metadata_json="{}",
        checksum_sha256="pending-checksum",
        mime_type="image/png",
        byte_size=1,
        width=1,
        height=1,
        duration_ms=None,
        prompt_ir_version_id=1,
        prompt_ir_payload_hash="prompt-hash",
        generation_payload_fingerprint="payload-fp",
        model_profile_id="builtin-mock-image",
        model_profile_fingerprint="profile-fp",
        provider_request_fingerprint="request-pending",
        provider_response_hash="response",
    ))
    db.commit()
    state["candidates"]["IMAGE"] = [{"id": "candidate-new", "state": "MEDIA_CANDIDATE"}]
    with pytest.raises(HTTPException) as exc:
        facade.create_shot_generation_attempt(1, 1, 101, _request("REGENERATE", "IMAGE", "regenerate-pending"))
    assert exc.value.detail["code"] == "GENERATION_REGENERATE_PENDING_CANDIDATE_EXISTS"
    db.query(MediaCandidateRecord).filter_by(candidate_id="candidate-pending").delete()
    db.commit()
    state["candidates"]["IMAGE"] = []
    state["latest"]["IMAGE"] = {"id": "active", "state": "RUNNING"}
    with pytest.raises(HTTPException) as exc:
        facade.create_shot_generation_attempt(1, 1, 101, _request("REGENERATE", "IMAGE", "regenerate-active"))
    assert exc.value.detail["code"] == "GENERATION_REGENERATE_ACTIVE_EXECUTION"


def test_regenerate_fails_closed_without_current_official(db, monkeypatch):
    shot = StoryboardShot(book_id=1, episode=1, shot_id=101, scene_name="scene")
    db.add(shot)
    db.flush()
    _execution(db, shot.id, "success", status="SUCCEEDED")
    db.commit()
    state = {"latest": {"IMAGE": {"id": "success", "state": "SUCCEEDED"}}, "official": {"IMAGE": {"current": False, "currentness": "missing", "version": None}}}
    _patch_lane(monkeypatch, db, shot, state)
    with pytest.raises(HTTPException) as exc:
        facade.create_shot_generation_attempt(1, 1, 101, _request("REGENERATE", "IMAGE", "regenerate-missing"))
    assert exc.value.detail["code"] == "GENERATION_REGENERATE_SOURCE_NOT_CURRENT"
