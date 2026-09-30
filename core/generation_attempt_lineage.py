"""Provider-free durable business operation lineage for Retry/Regenerate."""

from __future__ import annotations

from datetime import datetime
import hashlib
import hmac
import json
import uuid
from typing import Any

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from models import (
    GenerationExecutionAttemptLineage,
    GenerationExecutionRecord,
    MediaCandidateRecord,
    OfficialMediaPointer,
    OfficialMediaVersion,
)
from core.canonical_generation import derive_business_attempt_provider_request_fingerprint


class GenerationAttemptLineageError(ValueError):
    def __init__(self, message: str, *, code: str, status_code: int = 409):
        super().__init__(message)
        self.message, self.code, self.status_code = message, code, status_code


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _reason(value: Any) -> str:
    return _text(value)[:2000]


def _media(value: Any) -> str:
    result = _text(value).upper()
    if result not in {"IMAGE", "VIDEO"}:
        raise GenerationAttemptLineageError("target_media must be IMAGE or VIDEO", code="GENERATION_ATTEMPT_MEDIA_MISMATCH")
    return result


def _regenerate_variant_key(*, book_id: int, episode: int, storyboard_shot_id: int, target_media: str, variant_index: int) -> str:
    return _fingerprint({
        "schema_version": "regenerate_variant_key_v1",
        "book_id": int(book_id), "episode": int(episode),
        "storyboard_shot_id": int(storyboard_shot_id),
        "target_media": _media(target_media), "variant_index": int(variant_index),
    })


def _retry_attempt_key(*, root_execution_id: str, attempt_number: int) -> str:
    return _fingerprint({
        "schema_version": "retry_attempt_key_v1",
        "root_execution_id": _text(root_execution_id), "attempt_number": int(attempt_number),
    })


def _scope_matches(row: GenerationExecutionRecord, *, book_id: Any = None, episode: Any = None, storyboard_shot_id: Any = None, target_media: Any = None) -> bool:
    return (
        book_id is None or int(book_id) == int(row.book_id)
    ) and (
        episode is None or int(episode) == int(row.episode)
    ) and (
        storyboard_shot_id is None or int(storyboard_shot_id) == int(row.storyboard_shot_id)
    ) and (
        target_media is None or _media(target_media) == _media(row.target_media)
    )


class GenerationAttemptLineageService:
    def __init__(self, session: Any):
        self.session = session

    def _execution(self, execution_id: Any) -> GenerationExecutionRecord:
        row = self.session.query(GenerationExecutionRecord).filter_by(execution_id=_text(execution_id)).one_or_none()
        if row is None:
            raise GenerationAttemptLineageError("source execution does not exist", code="GENERATION_ATTEMPT_SOURCE_NOT_FOUND", status_code=404)
        return row

    @staticmethod
    def _execution_snapshot(row: GenerationExecutionRecord) -> dict[str, Any]:
        return {
            "execution_id": _text(row.execution_id), "status": _text(row.status).upper(),
            "book_id": int(row.book_id), "episode": int(row.episode),
            "storyboard_shot_id": int(row.storyboard_shot_id), "target_media": _media(row.target_media),
            "provider_request_fingerprint": _text(row.provider_request_fingerprint),
            "request_snapshot_fingerprint": _fingerprint(row.request_snapshot_json or "{}"),
            "generation_payload_fingerprint": _text(row.generation_payload_fingerprint),
            "generation_policy_fingerprint": _text(row.generation_policy_fingerprint),
            "model_profile_id": _text(row.model_profile_id),
            "model_profile_fingerprint": _text(row.model_profile_fingerprint),
            "reference_bindings_fingerprint": _text(row.reference_bindings_fingerprint),
            "prompt_ir_payload_hash": _text(row.prompt_ir_payload_hash),
            "prompt_ir_version_id": int(row.prompt_ir_version_id),
        }

    @staticmethod
    def _official_role(media: str) -> str:
        return "SHOT_PRIMARY_IMAGE" if media == "IMAGE" else "SHOT_PRIMARY_VIDEO"

    def _existing_by_key(self, key: str, book_id: int) -> GenerationExecutionAttemptLineage | None:
        return self.session.query(GenerationExecutionAttemptLineage).filter_by(
            book_id=int(book_id), operation_idempotency_key=key,
        ).one_or_none()

    def _confirm_token(self, row: GenerationExecutionAttemptLineage) -> str:
        payload = {
            "schema_version": "generation_attempt_confirmation_v1",
            "attempt_lineage_id": _text(row.attempt_lineage_id), "operation_kind": _text(row.operation_kind),
            "operation_identity_fingerprint": _text(row.operation_identity_fingerprint),
            "source_execution_id": _text(row.source_execution_id), "root_execution_id": _text(row.root_execution_id),
            "source_snapshot_fingerprint": _text(row.source_snapshot_fingerprint),
            "book_id": int(row.book_id), "episode": int(row.episode),
            "storyboard_shot_id": int(row.storyboard_shot_id), "target_media": _media(row.target_media),
            "attempt_number": int(row.attempt_number), "variant_index": int(row.variant_index),
        }
        return "gat_" + hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()

    @staticmethod
    def _operation_identity(*, kind: str, key: str, execution: GenerationExecutionRecord, source_snapshot: dict[str, Any], reason: str, source_candidate_id: str | None, source_official_media_version_id: str | None, root_execution_id: str, attempt_number: int, variant_index: int) -> str:
        return _fingerprint({
            "schema_version": "generation_attempt_operation_v1", "operation_kind": _text(kind).upper(),
            "operation_idempotency_key": _text(key), "source_execution_id": _text(execution.execution_id),
            "root_execution_id": _text(root_execution_id), "target_media": _media(execution.target_media),
            "attempt_number": int(attempt_number), "variant_index": int(variant_index),
            "source_snapshot": source_snapshot, "reason": _reason(reason),
            "source_candidate_id": source_candidate_id, "source_official_media_version_id": source_official_media_version_id,
        })

    def build_confirmation(self, attempt_lineage_id: str) -> str:
        row = self.get_intent(attempt_lineage_id)
        return self._confirm_token(row)

    def verify_confirmation(self, attempt_lineage_id: str, confirmation_token: str) -> bool:
        row = self.get_intent(attempt_lineage_id)
        token = _text(confirmation_token)
        if not token or not hmac.compare_digest(hashlib.sha256(token.encode("utf-8")).hexdigest(), _text(row.confirmation_binding_hash)):
            raise GenerationAttemptLineageError("confirmation token is not bound to this attempt", code="GENERATION_ATTEMPT_CONFIRMATION_MISMATCH")
        return True

    def _create(self, *, key: str, kind: str, execution: GenerationExecutionRecord, source_snapshot: dict[str, Any], reason: str, source_candidate_id: str | None = None, source_official_media_version_id: str | None = None, variant_index: int = 0, root_execution_id: str | None = None, attempt_number: int = 1, regenerate_variant_key: str | None = None, retry_attempt_key: str | None = None) -> GenerationExecutionAttemptLineage:
        key = _text(key)
        if not key:
            raise GenerationAttemptLineageError("operation_idempotency_key is required", code="GENERATION_ATTEMPT_IDEMPOTENCY_CONFLICT")
        kind = _text(kind).upper()
        if kind not in {"RETRY", "REGENERATE"}:
            raise GenerationAttemptLineageError("operation_kind must be RETRY or REGENERATE", code="GENERATION_ATTEMPT_IDEMPOTENCY_CONFLICT")
        if kind == "RETRY" and int(variant_index) != 0:
            raise GenerationAttemptLineageError("Retry variant_index must be zero", code="GENERATION_ATTEMPT_SCOPE_MISMATCH")
        if kind == "REGENERATE" and int(variant_index) < 1:
            raise GenerationAttemptLineageError("Regenerate variant_index must be positive", code="GENERATION_ATTEMPT_SCOPE_MISMATCH")
        identity = self._operation_identity(kind=kind, key=key, execution=execution, source_snapshot=source_snapshot, reason=reason, source_candidate_id=source_candidate_id, source_official_media_version_id=source_official_media_version_id, root_execution_id=_text(root_execution_id or execution.execution_id), attempt_number=attempt_number, variant_index=variant_index)
        existing = self._existing_by_key(key, int(execution.book_id))
        if existing is not None:
            if _text(existing.operation_identity_fingerprint) != identity:
                raise GenerationAttemptLineageError("idempotency key is bound to a different operation", code="GENERATION_ATTEMPT_IDEMPOTENCY_CONFLICT")
            return existing
        now = datetime.utcnow()
        row = GenerationExecutionAttemptLineage(
            attempt_lineage_id="gat_" + uuid.uuid4().hex,
            operation_idempotency_key=key, operation_kind=kind,
            book_id=int(execution.book_id), episode=int(execution.episode), storyboard_shot_id=int(execution.storyboard_shot_id),
            target_media=_media(execution.target_media), source_execution_id=_text(execution.execution_id),
            root_execution_id=_text(root_execution_id or execution.execution_id), produced_execution_id=None,
            attempt_number=int(attempt_number), variant_index=int(variant_index), reason=_reason(reason),
            regenerate_variant_key=regenerate_variant_key, retry_attempt_key=retry_attempt_key,
            source_candidate_id=source_candidate_id, source_official_media_version_id=source_official_media_version_id,
            source_snapshot_fingerprint=_fingerprint(source_snapshot), operation_identity_fingerprint=identity,
            confirmation_binding_hash="", status="PREVIEWED", created_at=now, updated_at=now,
        )
        self.session.add(row)
        try:
            self.session.flush()
        except IntegrityError:
            # A concurrent request may have won the durable operation-key
            # race. Resolve that expected conflict after rollback; unrelated
            # integrity failures remain visible to the caller.
            self.session.rollback()
            winner = self._existing_by_key(key, int(execution.book_id))
            if winner is None:
                raise
            if _text(winner.operation_identity_fingerprint) != identity:
                raise GenerationAttemptLineageError("idempotency key is bound to a different operation", code="GENERATION_ATTEMPT_IDEMPOTENCY_CONFLICT")
            return winner
        row.confirmation_binding_hash = hashlib.sha256(self._confirm_token(row).encode("utf-8")).hexdigest()
        self.session.flush()
        return row

    def create_retry_intent(self, *, source_execution_id: str, operation_idempotency_key: str, reason: str = "", book_id: Any = None, episode: Any = None, storyboard_shot_id: Any = None, target_media: Any = None) -> GenerationExecutionAttemptLineage:
        execution = self._execution(source_execution_id)
        snapshot = self._execution_snapshot(execution)
        existing = self._existing_by_key(operation_idempotency_key, int(execution.book_id))
        if existing is not None:
            expected_identity = self._operation_identity(kind="RETRY", key=operation_idempotency_key, execution=execution, source_snapshot=snapshot, reason=reason, source_candidate_id=None, source_official_media_version_id=None, root_execution_id=_text(existing.root_execution_id), attempt_number=int(existing.attempt_number), variant_index=0)
            if existing.operation_kind != "RETRY" or _text(existing.source_execution_id) != _text(source_execution_id) or _text(existing.operation_identity_fingerprint) != expected_identity:
                raise GenerationAttemptLineageError("idempotency key is bound to a different operation", code="GENERATION_ATTEMPT_IDEMPOTENCY_CONFLICT")
            return existing
        if _text(execution.status).upper() != "FAILED":
            raise GenerationAttemptLineageError("Retry requires a FAILED source execution", code="GENERATION_RETRY_SOURCE_NOT_FAILED")
        if not _scope_matches(execution, book_id=book_id, episode=episode, storyboard_shot_id=storyboard_shot_id, target_media=target_media):
            raise GenerationAttemptLineageError("source execution scope does not match the request", code="GENERATION_ATTEMPT_SCOPE_MISMATCH")
        parent = self.session.query(GenerationExecutionAttemptLineage).filter_by(produced_execution_id=execution.execution_id).one_or_none()
        root_id = parent.root_execution_id if parent else execution.execution_id
        for _ in range(3):
            max_attempt = self.session.query(func.max(GenerationExecutionAttemptLineage.attempt_number)).filter_by(operation_kind="RETRY", root_execution_id=_text(root_id)).scalar() or 0
            attempt_number = int(max_attempt) + 1
            try:
                return self._create(key=operation_idempotency_key, kind="RETRY", execution=execution, source_snapshot=snapshot, reason=reason, root_execution_id=root_id, attempt_number=attempt_number, variant_index=0, retry_attempt_key=_retry_attempt_key(root_execution_id=root_id, attempt_number=attempt_number))
            except IntegrityError as exc:
                if "retry_attempt_key" not in str(exc).lower():
                    raise
        raise GenerationAttemptLineageError("retry ordinal allocation conflicted repeatedly", code="GENERATION_ATTEMPT_IDEMPOTENCY_CONFLICT")

    def create_regenerate_intent(self, *, source_official_media_version_id: str, operation_idempotency_key: str, reason: str = "", book_id: Any = None, episode: Any = None, storyboard_shot_id: Any = None, target_media: Any = None) -> GenerationExecutionAttemptLineage:
        official = self.session.query(OfficialMediaVersion).filter_by(official_media_version_id=_text(source_official_media_version_id)).one_or_none()
        if official is None:
            raise GenerationAttemptLineageError("source OfficialMediaVersion does not exist", code="GENERATION_ATTEMPT_SOURCE_NOT_FOUND", status_code=404)
        media = _media(official.media_type)
        if target_media is not None and _media(target_media) != media:
            raise GenerationAttemptLineageError("source OfficialMediaVersion media does not match target_media", code="GENERATION_ATTEMPT_MEDIA_MISMATCH")
        if not _scope_matches(official, book_id=book_id, episode=episode, storyboard_shot_id=storyboard_shot_id):
            raise GenerationAttemptLineageError("OfficialMediaVersion scope does not match the request", code="GENERATION_ATTEMPT_SCOPE_MISMATCH")
        pointer = self.session.query(OfficialMediaPointer).filter_by(book_id=official.book_id, episode=official.episode, storyboard_shot_id=official.storyboard_shot_id, media_role=official.media_role).one_or_none()
        if pointer is None or _text(pointer.official_media_version_id) != _text(official.official_media_version_id) or _text(official.status).upper() != "CURRENT":
            raise GenerationAttemptLineageError("source OfficialMediaVersion is not current", code="GENERATION_REGENERATE_SOURCE_NOT_CURRENT")
        candidate = self.session.query(MediaCandidateRecord).filter_by(candidate_id=_text(official.candidate_id)).one_or_none()
        if candidate is None:
            raise GenerationAttemptLineageError("source candidate does not exist", code="GENERATION_ATTEMPT_SOURCE_NOT_FOUND", status_code=404)
        execution = self._execution(candidate.execution_id)
        if not _scope_matches(execution, book_id=official.book_id, episode=official.episode, storyboard_shot_id=official.storyboard_shot_id, target_media=media):
            raise GenerationAttemptLineageError("source candidate execution scope mismatch", code="GENERATION_ATTEMPT_SCOPE_MISMATCH")
        snapshot = {
            "official_media_version_id": _text(official.official_media_version_id), "official_status": _text(official.status).upper(),
            "pointer_fingerprint": _text(pointer.fingerprint), "candidate_id": _text(candidate.candidate_id),
            "execution": self._execution_snapshot(execution), "media_role": _text(official.media_role),
        }
        existing = self._existing_by_key(operation_idempotency_key, int(official.book_id))
        if existing is not None:
            expected_identity = self._operation_identity(kind="REGENERATE", key=operation_idempotency_key, execution=execution, source_snapshot=snapshot, reason=reason, source_candidate_id=_text(candidate.candidate_id), source_official_media_version_id=_text(official.official_media_version_id), root_execution_id=_text(existing.root_execution_id), attempt_number=int(existing.attempt_number), variant_index=int(existing.variant_index))
            if existing.operation_kind != "REGENERATE" or _text(existing.source_official_media_version_id) != _text(source_official_media_version_id) or _text(existing.operation_identity_fingerprint) != expected_identity:
                raise GenerationAttemptLineageError("idempotency key is bound to a different operation", code="GENERATION_ATTEMPT_IDEMPOTENCY_CONFLICT")
            return existing
        for _ in range(3):
            max_variant = self.session.query(func.max(GenerationExecutionAttemptLineage.variant_index)).filter_by(
                operation_kind="REGENERATE", book_id=int(official.book_id), episode=int(official.episode),
                storyboard_shot_id=int(official.storyboard_shot_id), target_media=media,
            ).scalar() or 0
            variant_index = int(max_variant) + 1
            try:
                return self._create(key=operation_idempotency_key, kind="REGENERATE", execution=execution, source_snapshot=snapshot, reason=reason, source_candidate_id=_text(candidate.candidate_id), source_official_media_version_id=_text(official.official_media_version_id), variant_index=variant_index, attempt_number=1, regenerate_variant_key=_regenerate_variant_key(book_id=official.book_id, episode=official.episode, storyboard_shot_id=official.storyboard_shot_id, target_media=media, variant_index=variant_index))
            except IntegrityError as exc:
                if "regenerate_variant_key" not in str(exc).lower():
                    raise
        raise GenerationAttemptLineageError("regenerate variant allocation conflicted repeatedly", code="GENERATION_ATTEMPT_IDEMPOTENCY_CONFLICT")

    def get_intent(self, attempt_lineage_id: str) -> GenerationExecutionAttemptLineage:
        row = self.session.query(GenerationExecutionAttemptLineage).filter_by(attempt_lineage_id=_text(attempt_lineage_id)).one_or_none()
        if row is None:
            raise GenerationAttemptLineageError("attempt lineage does not exist", code="GENERATION_ATTEMPT_SOURCE_NOT_FOUND", status_code=404)
        return row

    def derive_attempt_provider_request_fingerprint(self, base_provider_request_fingerprint: str, operation_identity_fingerprint: str) -> str:
        return derive_business_attempt_provider_request_fingerprint(base_provider_request_fingerprint, operation_identity_fingerprint)

    def bind_produced_execution(self, attempt_lineage_id: str, produced_execution_id: str) -> GenerationExecutionAttemptLineage:
        row = self.get_intent(attempt_lineage_id)
        if row.produced_execution_id and _text(row.produced_execution_id) != _text(produced_execution_id):
            raise GenerationAttemptLineageError("attempt is already bound to another execution", code="GENERATION_ATTEMPT_ALREADY_BOUND")
        execution = self._execution(produced_execution_id)
        if not _scope_matches(execution, book_id=row.book_id, episode=row.episode, storyboard_shot_id=row.storyboard_shot_id, target_media=row.target_media):
            raise GenerationAttemptLineageError("produced execution scope does not match the attempt", code="GENERATION_ATTEMPT_SCOPE_MISMATCH")
        if _text(execution.execution_id) in {_text(row.source_execution_id), _text(row.root_execution_id)}:
            raise GenerationAttemptLineageError("produced execution cannot be the source or root execution", code="GENERATION_ATTEMPT_SCOPE_MISMATCH")
        row.produced_execution_id = _text(produced_execution_id)
        row.status = "BOUND"
        row.updated_at = datetime.utcnow()
        self.session.flush()
        return row


def serialize_attempt_lineage(row: GenerationExecutionAttemptLineage, *, include_confirmation: bool = False, service: GenerationAttemptLineageService | None = None) -> dict[str, Any]:
    payload = {key: getattr(row, key) for key in (
        "attempt_lineage_id", "operation_idempotency_key", "operation_kind", "book_id", "episode", "storyboard_shot_id", "target_media", "source_execution_id", "root_execution_id", "produced_execution_id", "attempt_number", "variant_index", "regenerate_variant_key", "retry_attempt_key", "reason", "source_candidate_id", "source_official_media_version_id", "source_snapshot_fingerprint", "operation_identity_fingerprint", "status",
    )}
    payload["created_at"] = row.created_at.isoformat() if row.created_at else None
    payload["updated_at"] = row.updated_at.isoformat() if row.updated_at else None
    payload["confirmation_required"] = True
    if include_confirmation and service is not None:
        payload["confirmation_token"] = service.build_confirmation(row.attempt_lineage_id)
    payload.update({"provider_calls": 0, "execution_created": False, "media_generated": False})
    return payload


__all__ = ["GenerationAttemptLineageError", "GenerationAttemptLineageService", "serialize_attempt_lineage"]
