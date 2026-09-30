"""Canonical production facade for Retry/Regenerate attempt intents.

This module owns only the business-operation boundary.  PromptIR resolution,
transport validation, provider dispatch, candidate persistence, and replay are
delegated to the existing canonical generation runtime.
"""

from __future__ import annotations

import json
import hashlib
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from api.generation_canary_api import (
    _canonical_preview_metadata,
    _confirmation_token,
    _error,
    _execute_generation_canary_impl,
    _json,
    _redact,
    _resolve_canonical_execution_inputs,
    _serialize_candidate,
    _serialize_execution,
)
from core.generation_attempt_lineage import (
    GenerationAttemptLineageError,
    GenerationAttemptLineageService,
    serialize_attempt_lineage,
)
from core.canonical_generation import derive_business_attempt_provider_request_fingerprint
from models import (
    GenerationExecutionAttemptLineage,
    GenerationExecutionRecord,
    OfficialMediaPointer,
    OfficialMediaVersion,
    Session,
    StoryboardShot,
    MediaCandidateRecord,
)


router = APIRouter(prefix="/api/books", tags=["generation-attempt-canonical"])


class AttemptPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    attempt_confirmation_token: str = Field(min_length=1, validation_alias=AliasChoices("attemptConfirmationToken", "attempt_confirmation_token"))


class AttemptExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    execute: bool = False
    confirmed: bool = False
    allow_external_call: bool = Field(default=False, validation_alias=AliasChoices("allowExternalCall", "allow_external_call"))
    attempt_confirmation_token: str = Field(min_length=1, validation_alias=AliasChoices("attemptConfirmationToken", "attempt_confirmation_token"))
    preview_execution_id: str = Field(min_length=1, validation_alias=AliasChoices("previewExecutionId", "preview_execution_id"))
    execution_confirmation_token: str = Field(min_length=1, validation_alias=AliasChoices("executionConfirmationToken", "execution_confirmation_token"))


def _raise_lineage(exc: GenerationAttemptLineageError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.message, "provider_calls": 0, "official_promotion_count": 0},
    ) from exc


def _business_shot(session: Any, *, book_id: int, episode: int, shot_id: int) -> StoryboardShot:
    row = session.query(StoryboardShot).filter_by(book_id=book_id, episode=episode, shot_id=shot_id).first()
    if row is None:
        raise _error(404, "GENERATION_ATTEMPT_SHOT_NOT_FOUND", "The URL shot_id is not a StoryboardShot.shot_id.", provider_calls=0)
    return row


def _source_base_provider_fingerprint(session: Any, source: GenerationExecutionRecord) -> str:
    snapshot = _json(source.request_snapshot_json, {})
    has_lineage = isinstance(snapshot, dict) and "_generation_attempt" in snapshot
    lineage = snapshot.get("_generation_attempt") if isinstance(snapshot, dict) else None
    if has_lineage:
        lineage_id = str(lineage.get("attempt_lineage_id") or "") if isinstance(lineage, dict) else ""
        lineage_row = session.query(GenerationExecutionAttemptLineage).filter_by(attempt_lineage_id=lineage_id).one_or_none() if lineage_id else None
        if (
            not isinstance(lineage, dict)
            or lineage_row is None
            or str(lineage_row.produced_execution_id or "") != str(source.execution_id)
            or not str(lineage.get("operation_identity_fingerprint") or "")
            or not str(lineage.get("base_provider_request_fingerprint") or "")
        ):
            raise _error(409, "GENERATION_ATTEMPT_SOURCE_LINEAGE_INVALID", "Attempt-produced source execution has incomplete lineage metadata.", provider_calls=0)
        return str(lineage["base_provider_request_fingerprint"])
    return str(source.provider_request_fingerprint or "")


def _validate_source_freshness(session: Any, *, attempt: GenerationExecutionAttemptLineage, shot: StoryboardShot) -> tuple[GenerationExecutionRecord, str]:
    if int(attempt.storyboard_shot_id) != int(shot.id) or int(attempt.book_id) != int(shot.book_id) or int(attempt.episode) != int(shot.episode):
        raise _error(409, "GENERATION_ATTEMPT_SCOPE_MISMATCH", "Attempt scope does not match the URL business shot.", provider_calls=0)
    source = session.query(GenerationExecutionRecord).filter_by(execution_id=attempt.source_execution_id).one_or_none()
    if source is None:
        raise _error(404, "GENERATION_ATTEMPT_SOURCE_NOT_FOUND", "Attempt source execution does not exist.", provider_calls=0)
    if int(source.storyboard_shot_id) != int(shot.id) or int(source.book_id) != int(shot.book_id) or int(source.episode) != int(shot.episode) or str(source.target_media).upper() != str(attempt.target_media).upper():
        raise _error(409, "GENERATION_ATTEMPT_SCOPE_MISMATCH", "Attempt source execution scope does not match the URL business shot.", provider_calls=0)
    if str(attempt.operation_kind).upper() == "RETRY" and str(source.status).upper() != "FAILED":
        raise _error(409, "GENERATION_ATTEMPT_SOURCE_STALE", "Retry source execution is no longer FAILED.", provider_calls=0)
    if str(attempt.operation_kind).upper() == "REGENERATE":
        official_id = str(attempt.source_official_media_version_id or "")
        official = session.query(OfficialMediaVersion).filter_by(official_media_version_id=official_id).one_or_none()
        pointer = session.query(OfficialMediaPointer).filter_by(
            book_id=shot.book_id, episode=shot.episode, storyboard_shot_id=shot.id,
            media_role=("SHOT_PRIMARY_IMAGE" if str(attempt.target_media).upper() == "IMAGE" else "SHOT_PRIMARY_VIDEO"),
        ).one_or_none()
        if official is None or str(official.status).upper() != "CURRENT" or pointer is None or str(pointer.official_media_version_id) != official_id:
            raise _error(409, "GENERATION_ATTEMPT_SOURCE_STALE", "Regenerate source OfficialMedia is no longer current.", provider_calls=0)
    base_fp = _source_base_provider_fingerprint(session, source)
    if not base_fp:
        raise _error(409, "GENERATION_ATTEMPT_SOURCE_LINEAGE_INVALID", "Attempt source has no provider request fingerprint.", provider_calls=0)
    return source, base_fp


def _resolve_attempt(session: Any, *, book_id: int, episode: int, shot_id: int, attempt_lineage_id: str, attempt_confirmation_token: str) -> tuple[GenerationExecutionAttemptLineage, StoryboardShot, GenerationExecutionRecord, str, dict[str, Any]]:
    shot = _business_shot(session, book_id=book_id, episode=episode, shot_id=shot_id)
    service = GenerationAttemptLineageService(session)
    try:
        attempt = service.get_intent(attempt_lineage_id)
        service.verify_confirmation(attempt_lineage_id, attempt_confirmation_token)
    except GenerationAttemptLineageError as exc:
        _raise_lineage(exc)
    source, base_fp = _validate_source_freshness(session, attempt=attempt, shot=shot)
    context = _resolve_canonical_execution_inputs(
        session,
        book_id=book_id,
        episode=episode,
        shot_id=shot_id,
        target_media=str(attempt.target_media).upper(),
        model_profile_id=str(source.model_profile_id),
    )
    if int(context["row"].id) != int(shot.id) or int(attempt.storyboard_shot_id) != int(context["row"].id):
        raise _error(409, "GENERATION_ATTEMPT_SCOPE_MISMATCH", "Current canonical shot does not match the attempt scope.", provider_calls=0)
    if str(context["provider_request_fingerprint"] or "") != base_fp:
        raise _error(409, "GENERATION_ATTEMPT_SOURCE_STALE", "Current canonical authority no longer matches the attempt source.", provider_calls=0)
    return attempt, shot, source, base_fp, context


def _attempt_response(session: Any, *, attempt: GenerationExecutionAttemptLineage, service: GenerationAttemptLineageService, execution: GenerationExecutionRecord, candidate: MediaCandidateRecord | None, context: dict[str, Any] | None = None, reused: bool = False) -> dict[str, Any]:
    execution_token = _confirmation_token(
        execution_id=execution.execution_id,
        prompt_ir_version_id=execution.prompt_ir_version_id,
        payload_fp=execution.generation_payload_fingerprint,
        model_profile_id=execution.model_profile_id,
        provider_request_fp=execution.provider_request_fingerprint,
    )
    payload: dict[str, Any] = {
        "attempt": serialize_attempt_lineage(attempt, include_confirmation=True, service=service),
        "execution": _serialize_execution(execution),
        "candidate": _serialize_candidate(candidate),
        "execution_confirmation_token": execution_token,
        "provider_calls": 0,
        "official_promotion_count": 0,
        "reused": reused,
        "media_generated": candidate is not None,
    }
    if context is not None:
        payload.update(_canonical_preview_metadata(context))
        payload["generation_payload"] = context["payload"]
        payload["provider_request_snapshot"] = _redact(context["request_snapshot"])
    return payload


@router.post("/{book_id}/episodes/{episode}/shots/{shot_id}/generation-attempts/{attempt_lineage_id}/preview")
def preview_generation_attempt(book_id: int, episode: int, shot_id: int, attempt_lineage_id: str, req: AttemptPreviewRequest):
    with Session() as session:
        attempt, _shot, source, base_fp, context = _resolve_attempt(
            session,
            book_id=book_id,
            episode=episode,
            shot_id=shot_id,
            attempt_lineage_id=attempt_lineage_id,
            attempt_confirmation_token=req.attempt_confirmation_token,
        )
        service = GenerationAttemptLineageService(session)
        if attempt.produced_execution_id:
            execution = session.query(GenerationExecutionRecord).filter_by(execution_id=attempt.produced_execution_id).one_or_none()
            if execution is None:
                raise _error(409, "GENERATION_ATTEMPT_SOURCE_LINEAGE_INVALID", "Attempt is bound to a missing produced execution.", provider_calls=0)
            candidate = session.query(MediaCandidateRecord).filter_by(execution_id=execution.execution_id).one_or_none()
            return _attempt_response(session, attempt=attempt, service=service, execution=execution, candidate=candidate, context=context, reused=True)
        attempt_fp = derive_business_attempt_provider_request_fingerprint(base_fp, str(attempt.operation_identity_fingerprint))
        existing = session.query(GenerationExecutionRecord).filter_by(provider_request_fingerprint=attempt_fp).one_or_none()
        if existing is not None:
            try:
                service.bind_produced_execution(attempt.attempt_lineage_id, existing.execution_id)
                session.commit()
            except GenerationAttemptLineageError as exc:
                session.rollback()
                _raise_lineage(exc)
            return _attempt_response(session, attempt=attempt, service=service, execution=existing, candidate=session.query(MediaCandidateRecord).filter_by(execution_id=existing.execution_id).one_or_none(), context=context, reused=True)
        snapshot = dict(context["request_snapshot"])
        snapshot["_generation_attempt"] = {
            "schema_version": "generation_attempt_execution_v1",
            "attempt_lineage_id": attempt.attempt_lineage_id,
            "operation_kind": attempt.operation_kind,
            "operation_identity_fingerprint": attempt.operation_identity_fingerprint,
            "source_execution_id": attempt.source_execution_id,
            "root_execution_id": attempt.root_execution_id,
            "attempt_number": int(attempt.attempt_number),
            "variant_index": int(attempt.variant_index),
            "source_snapshot_fingerprint": attempt.source_snapshot_fingerprint,
            "base_provider_request_fingerprint": base_fp,
        }
        execution_id = uuid.uuid4().hex
        execution_token = _confirmation_token(
            execution_id=execution_id,
            prompt_ir_version_id=int(context["resolved"]["version"].id),
            payload_fp=str(context["payload"]["generation_payload_fingerprint"]),
            model_profile_id=str(source.model_profile_id),
            provider_request_fp=attempt_fp,
        )
        now = datetime.utcnow()
        execution = GenerationExecutionRecord(
            execution_id=execution_id,
            schema_version="generation_execution_request_v1",
            book_id=book_id,
            episode=episode,
            storyboard_shot_id=int(context["row"].id),
            plan_shot_id=str(context["payload"].get("prompt_ir_ref", {}).get("plan_shot_id") or ""),
            execution_mode="PREVIEW",
            status="PREVIEWED",
            target_media=str(attempt.target_media).upper(),
            prompt_ir_version_id=int(context["resolved"]["version"].id),
            prompt_ir_authority_id=int(context["resolved"]["authority"].id),
            prompt_ir_payload_hash=str(context["resolved"]["version"].payload_hash or ""),
            generation_payload_fingerprint=str(context["payload"].get("generation_payload_fingerprint") or ""),
            generation_policy_fingerprint=str(context["policy"].get("fingerprint") or ""),
            model_profile_id=str(source.model_profile_id),
            model_profile_fingerprint=context["profile_fingerprint"],
            provider_adapter_id=str(context["adapter"].get("adapter_id") or ""),
            provider_adapter_version=str(context["adapter"].get("adapter_version") or ""),
            reference_bindings_fingerprint=context["reference_bindings_fingerprint"],
            provider_request_fingerprint=attempt_fp,
            request_snapshot_json=json.dumps(_redact(snapshot), ensure_ascii=False, sort_keys=True),
            confirmation_binding_hash=hashlib.sha256(execution_token.encode("utf-8")).hexdigest(),
            provider=str(context["profile"].get("provider") or ""),
            model=str(context["profile"].get("model_name") or ""),
            created_at=now,
            updated_at=now,
        )
        session.add(execution)
        try:
            session.flush()
            service.bind_produced_execution(attempt.attempt_lineage_id, execution.execution_id)
            session.commit()
        except GenerationAttemptLineageError as exc:
            session.rollback()
            _raise_lineage(exc)
        except Exception:
            session.rollback()
            existing = session.query(GenerationExecutionRecord).filter_by(provider_request_fingerprint=attempt_fp).one_or_none()
            if existing is None:
                raise
            service.bind_produced_execution(attempt.attempt_lineage_id, existing.execution_id)
            session.commit()
            execution = existing
        return _attempt_response(session, attempt=attempt, service=service, execution=execution, candidate=None, context=context)


@router.post("/{book_id}/episodes/{episode}/shots/{shot_id}/generation-attempts/{attempt_lineage_id}/execute")
async def execute_generation_attempt(book_id: int, episode: int, shot_id: int, attempt_lineage_id: str, req: AttemptExecuteRequest):
    if not req.execute or not req.confirmed or not req.allow_external_call:
        raise _error(409, "GENERATION_ATTEMPT_EXECUTE_CONFIRMATION_REQUIRED", "Attempt execution requires execute=true, confirmed=true, and allowExternalCall=true.", provider_calls=0, official_promotion_count=0)
    with Session() as session:
        attempt, _shot, _source, _base_fp, _context = _resolve_attempt(
            session,
            book_id=book_id,
            episode=episode,
            shot_id=shot_id,
            attempt_lineage_id=attempt_lineage_id,
            attempt_confirmation_token=req.attempt_confirmation_token,
        )
        if str(attempt.produced_execution_id or "") != str(req.preview_execution_id):
            raise _error(409, "GENERATION_ATTEMPT_EXECUTION_MISMATCH", "previewExecutionId is not the execution bound to the attempt.", provider_calls=0)
        execution = session.query(GenerationExecutionRecord).filter_by(execution_id=req.preview_execution_id, book_id=book_id, episode=episode).one_or_none()
        if execution is None:
            raise _error(404, "GENERATION_ATTEMPT_EXECUTION_NOT_FOUND", "The attempt preview execution does not exist.", provider_calls=0)
        expected = _confirmation_token(
            execution_id=execution.execution_id,
            prompt_ir_version_id=execution.prompt_ir_version_id,
            payload_fp=execution.generation_payload_fingerprint,
            model_profile_id=execution.model_profile_id,
            provider_request_fp=execution.provider_request_fingerprint,
        )
        if req.execution_confirmation_token != expected:
            raise _error(409, "GENERATION_EXECUTION_CONFIRMATION_MISMATCH", "The execution confirmation token is not bound to this preview.", provider_calls=0)
    delegated = type("AttemptCanaryRequest", (), {"execute": True, "confirmation_token": req.execution_confirmation_token, "preview_execution_id": req.preview_execution_id})()
    return await _execute_generation_canary_impl(
        book_id,
        episode,
        shot_id,
        delegated,
        _canonical=True,
        _attempt_lineage_id=attempt_lineage_id,
    )


__all__ = ["router", "AttemptPreviewRequest", "AttemptExecuteRequest", "preview_generation_attempt", "execute_generation_attempt"]
