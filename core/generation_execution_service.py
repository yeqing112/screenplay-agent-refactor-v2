"""Provider-free foundation service for durable generation executions.

This module deliberately stops before ModelAdapter/provider dispatch.  It
creates and transitions the existing GenerationExecutionRecord so the next
runtime phase has one durable fact boundary without introducing another task,
model, provider, or asset manager.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import uuid
from typing import Any, Mapping

from models import GenerationExecutionRecord, PromptIRAuthority, PromptIRPointer, PromptIRVersion, Session, StoryboardShot


FOUNDATION_SCHEMA_VERSION = "generation_execution_foundation_v1"
EXECUTION_STATUSES = frozenset({"CREATED", "QUEUED", "RUNNING", "PROVIDER_CALLED", "SUCCESS", "FAILED", "RETRYING"})
_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "CREATED": frozenset({"QUEUED"}),
    "QUEUED": frozenset({"RUNNING"}),
    # SUCCESS remains a valid direct terminal transition for the deterministic
    # provider-free MockAdapter.  Real media adapters take the explicit
    # RUNNING -> PROVIDER_CALLED -> SUCCESS path.
    "RUNNING": frozenset({"PROVIDER_CALLED", "SUCCESS", "FAILED"}),
    "PROVIDER_CALLED": frozenset({"SUCCESS", "FAILED"}),
    "FAILED": frozenset({"RETRYING"}),
    "RETRYING": frozenset({"QUEUED"}),
    "SUCCESS": frozenset(),
}


class GenerationExecutionError(ValueError):
    """Stable service error for invalid foundation operations."""

    status_code = 409

    def __init__(self, message: str, *, code: str = "GENERATION_EXECUTION_INVALID"):
        super().__init__(message)
        self.message = message
        self.code = code


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _required_id(value: Any, field: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise GenerationExecutionError(f"{field} must be a positive integer", code="GENERATION_EXECUTION_INPUT_INVALID") from exc
    if result <= 0:
        raise GenerationExecutionError(f"{field} must be a positive integer", code="GENERATION_EXECUTION_INPUT_INVALID")
    return result


def _resolve_shot(session: Any, shot_id: Any) -> StoryboardShot:
    requested = _required_id(shot_id, "shot_id")
    row = session.query(StoryboardShot).filter_by(id=requested).one_or_none()
    if row is None:
        row = session.query(StoryboardShot).filter_by(shot_id=requested).one_or_none()
    if row is None:
        raise GenerationExecutionError("shot_id does not identify an existing StoryboardShot", code="GENERATION_SHOT_NOT_FOUND")
    return row


def _resolve_prompt_inputs(session: Any, *, shot: StoryboardShot, prompt_pointer_id: Any, prompt_version_id: Any) -> tuple[PromptIRPointer, PromptIRVersion, PromptIRAuthority | None]:
    pointer_id = _required_id(prompt_pointer_id, "prompt_pointer_id")
    version_id = _required_id(prompt_version_id, "prompt_version_id")
    pointer = session.query(PromptIRPointer).filter_by(id=pointer_id).one_or_none()
    if pointer is None:
        raise GenerationExecutionError("prompt_pointer_id does not identify an existing PromptIRPointer", code="GENERATION_PROMPT_POINTER_NOT_FOUND")
    if int(pointer.storyboard_shot_id) not in {int(shot.id), int(shot.shot_id)}:
        raise GenerationExecutionError("PromptIRPointer does not belong to the requested shot", code="GENERATION_PROMPT_POINTER_SHOT_MISMATCH")
    if int(pointer.prompt_ir_version_id) != version_id:
        raise GenerationExecutionError("prompt_version_id does not match the PromptIRPointer", code="GENERATION_PROMPT_VERSION_MISMATCH")
    version = session.query(PromptIRVersion).filter_by(id=version_id).one_or_none()
    if version is None:
        raise GenerationExecutionError("prompt_version_id does not identify an existing PromptIRVersion", code="GENERATION_PROMPT_VERSION_NOT_FOUND")
    authority = session.query(PromptIRAuthority).filter_by(prompt_ir_version_id=version.id).one_or_none()
    return pointer, version, authority


def _serialize(row: GenerationExecutionRecord) -> dict[str, Any]:
    return {
        "execution_id": row.execution_id,
        "status": row.execution_status,
        "execution_status": row.execution_status,
        "metadata": {
            "schema_version": FOUNDATION_SCHEMA_VERSION,
            "shot_id": row.shot_id,
            "prompt_pointer_id": row.prompt_pointer_id,
            "prompt_version_id": row.prompt_version_id,
            "model_profile_id": row.model_profile_id,
            "target_media": row.target_media,
            "execution_mode": row.execution_mode,
            "provider_calls": int(row.logical_provider_calls or 0),
            "provider": row.provider,
            "model": row.model,
            "provider_request_id": row.provider_request_id,
            "provider_task_id": row.provider_task_id,
            "provider_response_hash": row.provider_response_hash,
            "candidate_id": row.candidate_id,
            "official_promotion_count": int(row.official_promotion_count or 0),
        },
        "request_payload": row.request_payload,
        "response_payload": row.response_payload,
        "error_message": row.error_message,
        "retry_count": row.retry_count,
        "timestamps": {
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        },
    }


class GenerationExecutionService:
    """Create, transition, and query provider-free execution facts."""

    def __init__(self, session: Any):
        self.session = session

    def create_execution(
        self,
        *,
        shot_id: Any,
        prompt_pointer_id: Any,
        prompt_version_id: Any,
        model_profile_id: str,
    ) -> GenerationExecutionRecord:
        shot = _resolve_shot(self.session, shot_id)
        pointer, version, authority = _resolve_prompt_inputs(
            self.session,
            shot=shot,
            prompt_pointer_id=prompt_pointer_id,
            prompt_version_id=prompt_version_id,
        )
        profile_id = str(model_profile_id or "").strip()
        if not profile_id:
            raise GenerationExecutionError("model_profile_id is required", code="GENERATION_MODEL_PROFILE_REQUIRED")

        foundation_request = {
            "schema_version": FOUNDATION_SCHEMA_VERSION,
            "shot_id": int(shot.id),
            "prompt_pointer_id": int(pointer.id),
            "prompt_version_id": int(version.id),
            "model_profile_id": profile_id,
            "target_media": str(pointer.target_media or "IMAGE").upper(),
            "provider_calls": 0,
        }
        execution_id = "gex_" + uuid.uuid4().hex
        payload_fp = _fingerprint(foundation_request)
        profile_fp = _fingerprint({"model_profile_id": profile_id})
        policy_fp = _fingerprint({"schema_version": FOUNDATION_SCHEMA_VERSION, "mode": "FOUNDATION"})
        provider_request_fp = _fingerprint({"execution_id": execution_id, **foundation_request})
        now = datetime.utcnow()
        row = GenerationExecutionRecord(
            execution_id=execution_id,
            schema_version=FOUNDATION_SCHEMA_VERSION,
            book_id=int(shot.book_id),
            episode=int(shot.episode),
            storyboard_shot_id=int(shot.id),
            plan_shot_id=str(shot.plan_shot_id or ""),
            execution_mode="FOUNDATION",
            status="CREATED",
            target_media=str(pointer.target_media or "IMAGE").upper(),
            prompt_ir_version_id=int(version.id),
            prompt_ir_authority_id=int(authority.id) if authority is not None else 0,
            prompt_ir_payload_hash=str(pointer.payload_hash or version.payload_hash or ""),
            generation_payload_fingerprint=payload_fp,
            generation_policy_fingerprint=policy_fp,
            model_profile_id=profile_id,
            model_profile_fingerprint=profile_fp,
            provider_adapter_id="foundation",
            provider_adapter_version="foundation_v1",
            reference_bindings_fingerprint="",
            provider_request_fingerprint=provider_request_fp,
            provider="",
            model="",
            logical_provider_calls=0,
            transport_retry_count=0,
            created_at=now,
            updated_at=now,
        )
        row.request_payload = foundation_request
        row.prompt_pointer_id = int(pointer.id)
        row.response_payload = {}
        self.session.add(row)
        self.session.flush()
        return row

    def transition(
        self,
        execution_id: str,
        target_status: str,
        *,
        error_message: str = "",
        response_payload: Mapping[str, Any] | None = None,
    ) -> GenerationExecutionRecord:
        row = self.session.query(GenerationExecutionRecord).filter_by(execution_id=str(execution_id)).one_or_none()
        if row is None:
            raise GenerationExecutionError("execution_id does not exist", code="GENERATION_EXECUTION_NOT_FOUND")
        current = row.execution_status
        target = str(target_status or "").strip().upper()
        if target not in EXECUTION_STATUSES:
            raise GenerationExecutionError(f"unsupported execution status: {target}", code="GENERATION_EXECUTION_STATUS_INVALID")
        if target not in _ALLOWED_TRANSITIONS.get(current, frozenset()):
            raise GenerationExecutionError(f"invalid execution transition {current} -> {target}", code="GENERATION_EXECUTION_TRANSITION_INVALID")
        now = datetime.utcnow()
        row.execution_status = target
        row.updated_at = now
        if target == "RUNNING":
            row.started_at = now
        if target in {"SUCCESS", "FAILED"}:
            row.completed_at = now
        if target == "FAILED":
            row.error_message = str(error_message or "")
        if target == "RETRYING":
            row.retry_count = row.retry_count + 1
            row.error_message = str(error_message or row.error_message or "")
        if response_payload is not None:
            row.response_payload = dict(response_payload)
        self.session.flush()
        return row

    def get_execution(self, execution_id: str) -> GenerationExecutionRecord:
        row = self.session.query(GenerationExecutionRecord).filter_by(execution_id=str(execution_id)).one_or_none()
        if row is None:
            raise GenerationExecutionError("execution_id does not exist", code="GENERATION_EXECUTION_NOT_FOUND")
        return row

    def list_for_shot(self, shot_id: Any) -> list[GenerationExecutionRecord]:
        shot = _resolve_shot(self.session, shot_id)
        return (
            self.session.query(GenerationExecutionRecord)
            .filter_by(storyboard_shot_id=int(shot.id))
            .order_by(GenerationExecutionRecord.created_at.desc(), GenerationExecutionRecord.id.desc())
            .all()
        )


def create_generation_execution(*, session: Any, shot_id: Any, prompt_pointer_id: Any, prompt_version_id: Any, model_profile_id: str) -> GenerationExecutionRecord:
    """Functional entry point used by API callers and isolated tests."""
    return GenerationExecutionService(session).create_execution(
        shot_id=shot_id,
        prompt_pointer_id=prompt_pointer_id,
        prompt_version_id=prompt_version_id,
        model_profile_id=model_profile_id,
    )


def serialize_generation_execution(row: GenerationExecutionRecord) -> dict[str, Any]:
    return _serialize(row)


__all__ = [
    "EXECUTION_STATUSES",
    "FOUNDATION_SCHEMA_VERSION",
    "GenerationExecutionError",
    "GenerationExecutionService",
    "create_generation_execution",
    "serialize_generation_execution",
]
