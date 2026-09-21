"""Deterministic Phase G2 media validation, promotion, and resolution.

This module deliberately contains no Provider, LLM, image API, or video API
calls.  It treats a Phase F candidate as immutable evidence and creates
Official Media rows only after an explicit promotion confirmation.
"""

from __future__ import annotations

import hashlib
import io
import json
import mimetypes
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from sqlalchemy.exc import IntegrityError

from core.public_asset_storage import _load_source_bytes
from models import (
    GenerationExecutionRecord,
    MediaCandidateRecord,
    MediaValidationRecord,
    OfficialMediaAuthority,
    OfficialMediaPointer,
    OfficialMediaVersion,
    PromptIRPointer,
    PromptIRVersion,
    VisualAssetPointer,
    VisualReferenceAuthority,
)


VALIDATION_VERSION = "media_validator_v1"
MEDIA_ROLE_DEFAULT = "SHOT_PRIMARY_IMAGE"


class MediaAuthorityError(Exception):
    """Stable, API-safe failure raised by the deterministic authority spine."""

    def __init__(self, code: str, message: str, *, status_code: int = 409, diagnostics: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.diagnostics = diagnostics if diagnostics is not None else []

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "diagnostics": self.diagnostics}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _fail(code: str, message: str, diagnostics: Any = None, *, status_code: int = 409) -> None:
    raise MediaAuthorityError(code, message, diagnostics=diagnostics, status_code=status_code)


def _candidate_fingerprint(candidate: MediaCandidateRecord, execution: GenerationExecutionRecord) -> str:
    """Hash immutable candidate and execution lineage, excluding timestamps."""
    return _fingerprint(
        {
            "schema_version": "media_candidate_fingerprint_v1",
            "candidate_id": str(candidate.candidate_id),
            "execution_id": str(candidate.execution_id),
            "storage_identity": str(candidate.storage_identity),
            "checksum_sha256": str(candidate.checksum_sha256),
            "media_type": str(candidate.media_type),
            "mime_type": str(candidate.mime_type),
            "byte_size": int(candidate.byte_size or 0),
            "width": candidate.width,
            "height": candidate.height,
            "duration_ms": candidate.duration_ms,
            "prompt_ir_version_id": int(candidate.prompt_ir_version_id),
            "prompt_ir_payload_hash": str(candidate.prompt_ir_payload_hash),
            "generation_payload_fingerprint": str(candidate.generation_payload_fingerprint),
            "provider_request_fingerprint": str(candidate.provider_request_fingerprint),
            "provider_response_hash": str(candidate.provider_response_hash),
            "execution_policy_fingerprint": str(execution.generation_policy_fingerprint),
            "model_profile_fingerprint": str(candidate.model_profile_fingerprint),
        }
    )


def _candidate_storage_sources(candidate: MediaCandidateRecord) -> list[str]:
    reference = _json(candidate.storage_reference_json, {})
    values: list[str] = []
    if isinstance(reference, dict):
        for key in ("local_path", "filepath", "path", "storage_path", "image_url", "url"):
            value = str(reference.get(key) or "").strip()
            if value and value not in values:
                values.append(value)
    identity = str(candidate.storage_identity or "").strip()
    if identity and identity not in values:
        values.append(identity)
    return values


def _read_candidate_bytes(candidate: MediaCandidateRecord) -> tuple[bytes, str, str]:
    """Read canonical bytes from storage, preferring the durable local copy."""
    errors: list[str] = []
    for source in _candidate_storage_sources(candidate):
        try:
            if source.startswith("/") and not source.startswith("//") and not source.startswith("/api/"):
                path = Path(source)
                if path.is_file():
                    return path.read_bytes(), mimetypes.guess_type(str(path))[0] or "", source
            if os.path.isabs(source) and Path(source).is_file():
                return Path(source).read_bytes(), mimetypes.guess_type(source)[0] or "", source
            data, content_type = _load_source_bytes(source)
            return data, content_type, source
        except Exception as exc:  # pragma: no cover - source-specific failures are reported below
            errors.append(f"{source}: {type(exc).__name__}: {exc}")
    _fail("MEDIA_STORAGE_UNREADABLE", "Canonical candidate storage bytes could not be read.", errors)
    raise AssertionError("unreachable")


def _detect_media(data: bytes, declared_type: str) -> tuple[str, int | None, int | None]:
    if not data:
        _fail("MEDIA_BYTES_EMPTY", "Candidate storage bytes are empty.")
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return "image/png", int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data.startswith(b"\xff\xd8\xff"):
        try:
            from PIL import Image

            with Image.open(io.BytesIO(data)) as image:
                return "image/jpeg", int(image.width), int(image.height)
        except Exception:
            _fail("MEDIA_BYTES_INVALID", "JPEG candidate bytes could not be decoded.")
    if data.startswith(b"RIFF") and len(data) >= 30 and data[8:12] == b"WEBP":
        try:
            from PIL import Image

            with Image.open(io.BytesIO(data)) as image:
                return "image/webp", int(image.width), int(image.height)
        except Exception:
            _fail("MEDIA_BYTES_INVALID", "WebP candidate bytes could not be decoded.")
    # Do not infer media truth from a filename or a declared MIME type.
    _fail("MEDIA_MIME_UNDETECTABLE", "Candidate bytes have no supported, parseable media signature.", {"declared_mime_type": declared_type})
    raise AssertionError("unreachable")


def validate_media_candidate_technical(candidate: MediaCandidateRecord) -> dict[str, Any]:
    """Pure deterministic storage validation; it never writes or calls a provider."""
    data, declared_content_type, source = _read_candidate_bytes(candidate)
    observed_mime, width, height = _detect_media(data, declared_content_type)
    expected_mime = str(candidate.mime_type or "").split(";", 1)[0].strip().lower()
    expected_media_type = str(candidate.media_type or "").strip().upper()
    checksum = hashlib.sha256(data).hexdigest()
    payload = {
        "schema_version": "media_technical_validation_v1",
        "bytes_valid": bool(data),
        "byte_size": len(data),
        "byte_size_valid": len(data) == int(candidate.byte_size or 0),
        "checksum_observed": checksum,
        "checksum_valid": checksum == str(candidate.checksum_sha256 or ""),
        "mime_observed": observed_mime,
        "mime_valid": observed_mime == expected_mime,
        "media_type": expected_media_type,
        "media_type_valid": expected_media_type == "IMAGE" and observed_mime.startswith("image/"),
        "width_observed": width,
        "height_observed": height,
        "dimensions_valid": width == candidate.width and height == candidate.height and bool(width) and bool(height),
        "storage_valid": bool(source),
        "storage_source": source,
    }
    payload["valid"] = all(
        payload[key]
        for key in ("bytes_valid", "byte_size_valid", "checksum_valid", "mime_valid", "media_type_valid", "dimensions_valid", "storage_valid")
    )
    payload["technical_validation_fingerprint"] = _fingerprint(payload)
    return payload


def validate_media_candidate_integrity(session: Any, candidate_id: str | None = None, *, candidate: MediaCandidateRecord | None = None) -> dict[str, Any]:
    """Validate immutable Candidate/Execution lineage without mutating either row."""
    if candidate is None:
        if not candidate_id:
            _fail("MEDIA_CANDIDATE_ID_REQUIRED", "candidate_id is required.", status_code=400)
        candidate = session.query(MediaCandidateRecord).filter_by(candidate_id=str(candidate_id)).first()
    if candidate is None:
        _fail("MEDIA_CANDIDATE_NOT_FOUND", "Media Candidate does not exist.", status_code=404)
    if str(candidate.status or "").upper() != "MEDIA_CANDIDATE":
        _fail("MEDIA_CANDIDATE_IMMUTABLE_STATUS", "Candidate status must remain MEDIA_CANDIDATE.")
    execution = session.query(GenerationExecutionRecord).filter_by(execution_id=str(candidate.execution_id)).first()
    if execution is None:
        _fail("MEDIA_EXECUTION_NOT_FOUND", "Candidate execution lineage does not exist.")
    checks = {
        "execution_id": (candidate.execution_id, execution.execution_id),
        "prompt_ir_version_id": (candidate.prompt_ir_version_id, execution.prompt_ir_version_id),
        "prompt_ir_payload_hash": (candidate.prompt_ir_payload_hash, execution.prompt_ir_payload_hash),
        "generation_payload_fingerprint": (candidate.generation_payload_fingerprint, execution.generation_payload_fingerprint),
        "provider_request_fingerprint": (candidate.provider_request_fingerprint, execution.provider_request_fingerprint),
        "provider_response_hash": (candidate.provider_response_hash, execution.provider_response_hash),
        "model_profile_id": (candidate.model_profile_id, execution.model_profile_id),
        "model_profile_fingerprint": (candidate.model_profile_fingerprint, execution.model_profile_fingerprint),
    }
    invalid = [field for field, (actual, expected) in checks.items() if str(actual or "") != str(expected or "")]
    if invalid:
        _fail("MEDIA_CANDIDATE_LINEAGE_INVALID", "Candidate lineage does not match GenerationExecutionRecord.", invalid)
    sources = _candidate_storage_sources(candidate)
    if not sources:
        _fail("MEDIA_STORAGE_IDENTITY_MISSING", "Candidate has no canonical storage identity.")
    return {"candidate": candidate, "execution": execution, "candidate_fingerprint": _candidate_fingerprint(candidate, execution)}


def _reference_snapshot(session: Any, execution: GenerationExecutionRecord) -> dict[str, Any]:
    request = _json(execution.request_snapshot_json, {})
    bindings = request.get("reference_bindings") if isinstance(request, dict) else []
    result = []
    for item in bindings if isinstance(bindings, list) else []:
        if not isinstance(item, dict):
            continue
        authority_fp = str(item.get("reference_authority_fingerprint") or item.get("reference_authority_ref") or "").strip()
        if not authority_fp:
            continue
        authority = session.query(VisualReferenceAuthority).filter_by(authority_fingerprint=authority_fp).first()
        pointer = session.query(VisualAssetPointer).filter_by(book_id=execution.book_id, asset_key=getattr(authority, "asset_key", "")) .first() if authority is not None else None
        pointer_matches = bool(authority and pointer and int(pointer.current_version_id or 0) == int(authority.asset_version_id or 0) and str(pointer.payload_hash or "") == str(authority.asset_version_fingerprint or ""))
        result.append({
            "authority_fingerprint": authority_fp,
            "exists": authority is not None,
            "status": str(getattr(authority, "status", "") or "") if authority else "",
            "stale_status": str(getattr(authority, "stale_status", "") or "") if authority else "",
            "asset_version_id": getattr(authority, "asset_version_id", None) if authority else None,
            "asset_version_fingerprint": str(getattr(authority, "asset_version_fingerprint", "") or "") if authority else "",
            "pointer_matches": pointer_matches,
        })
    return {"declared": bool(result), "bindings": result, "fingerprint": _fingerprint(result)}


def _current_authority_snapshot(session: Any, *, candidate: MediaCandidateRecord, execution: GenerationExecutionRecord) -> dict[str, Any]:
    prompt = {"declared": True, "candidate_version_id": int(candidate.prompt_ir_version_id), "candidate_payload_hash": str(candidate.prompt_ir_payload_hash)}
    pointer = session.query(PromptIRPointer).filter_by(book_id=execution.book_id, episode=execution.episode, storyboard_shot_id=execution.storyboard_shot_id).first()
    if pointer is None:
        prompt.update({"pointer_present": False, "current_version_id": None, "current_payload_hash": "", "matches": True})
    else:
        version = session.query(PromptIRVersion).filter_by(id=pointer.prompt_ir_version_id).first()
        current_hash = str(getattr(version, "payload_hash", "") or "") if version else ""
        prompt_payload = _json(getattr(version, "payload_json", "{}"), {}) if version else {}
        current_policy_fp = str((prompt_payload.get("generation_policy") or {}).get("fingerprint") or "") if isinstance(prompt_payload, dict) else ""
        prompt.update({"pointer_present": True, "current_version_id": getattr(version, "id", None), "current_payload_hash": current_hash, "pointer_payload_hash": str(pointer.payload_hash or ""), "current_generation_policy_fingerprint": current_policy_fp, "matches": bool(version and pointer.payload_hash == version.payload_hash and int(candidate.prompt_ir_version_id) == int(version.id) and candidate.prompt_ir_payload_hash == version.payload_hash)})
    request = _json(execution.request_snapshot_json, {})
    generation_policy = request.get("generation_policy") if isinstance(request, dict) else {}
    raw_assets = request.get("asset_bindings", []) if isinstance(request, dict) else []
    asset_bindings = []
    for item in raw_assets if isinstance(raw_assets, list) else []:
        if not isinstance(item, dict):
            continue
        asset_key = str(item.get("asset_key") or "").strip()
        pointer = session.query(VisualAssetPointer).filter_by(book_id=execution.book_id, asset_key=asset_key).first() if asset_key else None
        expected_version = item.get("current_version_id")
        expected_hash = str(item.get("payload_hash") or "")
        pointer_matches = bool(pointer and (expected_version is None or int(pointer.current_version_id or 0) == int(expected_version)) and (not expected_hash or str(pointer.payload_hash or "") == expected_hash) and str(pointer.stale_status or "FRESH").upper() == "FRESH")
        asset_bindings.append({"asset_key": asset_key, "pointer_present": pointer is not None, "current_version_id": getattr(pointer, "current_version_id", None) if pointer else None, "payload_hash": str(getattr(pointer, "payload_hash", "") or "") if pointer else "", "pointer_matches": pointer_matches})
    asset = {"declared": bool(asset_bindings), "bindings": asset_bindings}
    reference = _reference_snapshot(session, execution)
    return {
        "schema_version": "media_authority_snapshot_v1",
        "prompt_ir": prompt,
        "asset": asset,
        "reference": reference,
        "generation_policy_fingerprint": str(execution.generation_policy_fingerprint or ""),
        "generation_policy_current_fingerprint": str(prompt.get("current_generation_policy_fingerprint") or ""),
        "generation_policy_matches": not prompt.get("current_generation_policy_fingerprint") or str(prompt.get("current_generation_policy_fingerprint")) == str(execution.generation_policy_fingerprint or ""),
        "generation_policy_request": generation_policy if isinstance(generation_policy, dict) else {},
        "reference_bindings_fingerprint": str(execution.reference_bindings_fingerprint or ""),
        "currentness_valid": bool(prompt.get("matches", True)) and bool(prompt.get("generation_policy_matches", True)) and all(item.get("pointer_matches", True) for item in asset.get("bindings", [])) and all(item.get("exists") and item.get("pointer_matches", True) and str(item.get("status") or "").upper() in {"LOCKED", "REFERENCE_LOCKED"} and str(item.get("stale_status") or "FRESH").upper() == "FRESH" for item in reference.get("bindings", [])),
    }


def _validation_fingerprint(record: MediaValidationRecord) -> str:
    return _fingerprint({"validation_id": record.validation_id, "candidate_fingerprint": record.candidate_fingerprint, "technical_validation_fingerprint": record.technical_validation_fingerprint, "authority_snapshot_fingerprint": record.authority_snapshot_fingerprint, "status": record.status})


def validate_media_candidate(session: Any, candidate_id: str, *, validator_version: str = VALIDATION_VERSION) -> dict[str, Any]:
    """Create or reuse one deterministic validation record."""
    integrity = validate_media_candidate_integrity(session, candidate_id)
    candidate = integrity["candidate"]
    execution = integrity["execution"]
    technical = validate_media_candidate_technical(candidate)
    if not technical.get("valid"):
        _fail("MEDIA_VALIDATION_FAILED", "Candidate failed deterministic technical validation.", technical)
    snapshot = _current_authority_snapshot(session, candidate=candidate, execution=execution)
    snapshot_fp = _fingerprint(snapshot)
    existing = session.query(MediaValidationRecord).filter_by(candidate_fingerprint=integrity["candidate_fingerprint"], authority_snapshot_fingerprint=snapshot_fp, validator_version=validator_version).first()
    if existing is not None:
        return {"validation": existing, "validation_id": existing.validation_id, "reused": True, "provider_calls": 0, "llm_calls": 0, "image_calls": 0, "video_calls": 0}
    now = datetime.utcnow()
    validation_id = f"mvr-{_fingerprint({'candidate': integrity['candidate_fingerprint'], 'snapshot': snapshot_fp, 'validator_version': validator_version})[:40]}"
    row = MediaValidationRecord(validation_id=validation_id, candidate_id=candidate.candidate_id, execution_id=execution.execution_id, candidate_fingerprint=integrity["candidate_fingerprint"], technical_validation_payload_json=_canonical(technical), technical_validation_fingerprint=str(technical["technical_validation_fingerprint"]), authority_snapshot_json=_canonical(snapshot), authority_snapshot_fingerprint=snapshot_fp, validator_version=validator_version, status="TECHNICALLY_VALID", created_at=now, updated_at=now)
    try:
        session.add(row)
        session.commit()
    except Exception:
        session.rollback()
        existing = session.query(MediaValidationRecord).filter_by(candidate_fingerprint=integrity["candidate_fingerprint"], authority_snapshot_fingerprint=snapshot_fp, validator_version=validator_version).first()
        if existing is None:
            raise
        row = existing
        return {"validation": row, "validation_id": row.validation_id, "reused": True, "provider_calls": 0, "llm_calls": 0, "image_calls": 0, "video_calls": 0}
    return {"validation": row, "validation_id": row.validation_id, "reused": False, "provider_calls": 0, "llm_calls": 0, "image_calls": 0, "video_calls": 0}


def _load_validation(session: Any, validation_id: str) -> MediaValidationRecord:
    row = session.query(MediaValidationRecord).filter_by(validation_id=str(validation_id)).first()
    if row is None:
        _fail("MEDIA_VALIDATION_NOT_FOUND", "Validation record does not exist.", status_code=404)
    return row


def _mark_validation_stale(session: Any, row: MediaValidationRecord) -> None:
    row.status = "STALE"
    row.updated_at = datetime.utcnow()
    session.commit()


def _promotion_scope(execution: GenerationExecutionRecord) -> tuple[int, int, int, str]:
    request = _json(execution.request_snapshot_json, {})
    role = str(request.get("media_role") or MEDIA_ROLE_DEFAULT) if isinstance(request, dict) else MEDIA_ROLE_DEFAULT
    return int(execution.book_id), int(execution.episode), int(execution.storyboard_shot_id), role


def _pointer_fingerprint(pointer_values: dict[str, Any]) -> str:
    return _fingerprint({"schema_version": "official_media_pointer_v1", **pointer_values})


def _lineage_hash(candidate: MediaCandidateRecord, execution: GenerationExecutionRecord, validation: MediaValidationRecord) -> str:
    return _fingerprint({"candidate_id": candidate.candidate_id, "candidate_fingerprint": validation.candidate_fingerprint, "validation_id": validation.validation_id, "validation_fingerprint": validation.technical_validation_fingerprint, "prompt_ir_version_id": candidate.prompt_ir_version_id, "prompt_ir_payload_hash": candidate.prompt_ir_payload_hash, "generation_payload_fingerprint": candidate.generation_payload_fingerprint, "provider_request_fingerprint": candidate.provider_request_fingerprint, "provider_response_hash": candidate.provider_response_hash, "storage_identity": candidate.storage_identity, "checksum_sha256": candidate.checksum_sha256, "execution_id": execution.execution_id})


def promote_media_candidate(session: Any, candidate_id: str, validation_id: str, *, confirmation: bool | str) -> dict[str, Any]:
    """Explicitly promote a validated Candidate atomically into official rows."""
    accepted_confirmation = confirmation is True or (
        isinstance(confirmation, str)
        and confirmation.strip().lower() in {"true", "confirm", "confirmed", "yes"}
    )
    if not accepted_confirmation:
        _fail("MEDIA_PROMOTION_CONFIRMATION_REQUIRED", "Explicit promotion confirmation is required.")
    validation = _load_validation(session, validation_id)
    if validation.status not in {"TECHNICALLY_VALID", "REVIEW_REQUIRED"}:
        _fail("MEDIA_PROMOTION_STALE", "Validation is not eligible for promotion.")
    integrity = validate_media_candidate_integrity(session, candidate_id)
    candidate = integrity["candidate"]
    execution = integrity["execution"]
    if validation.candidate_id != candidate.candidate_id or validation.execution_id != execution.execution_id or validation.candidate_fingerprint != integrity["candidate_fingerprint"]:
        _fail("MEDIA_VALIDATION_TAMPERED", "Validation is not bound to the current Candidate and execution.")
    technical = validate_media_candidate_technical(candidate)
    stored_payload = _json(validation.technical_validation_payload_json, {})
    if stored_payload.get("technical_validation_fingerprint") != validation.technical_validation_fingerprint:
        _fail("MEDIA_VALIDATION_TAMPERED", "Validation payload and fingerprint do not match.")
    if not technical.get("valid") or technical.get("technical_validation_fingerprint") != validation.technical_validation_fingerprint:
        _fail("MEDIA_PROMOTION_STALE", "Candidate bytes or technical validation fingerprint changed.", technical)
    snapshot = _current_authority_snapshot(session, candidate=candidate, execution=execution)
    snapshot_fp = _fingerprint(snapshot)
    if not snapshot.get("currentness_valid") or snapshot_fp != validation.authority_snapshot_fingerprint:
        _mark_validation_stale(session, validation)
        _fail("MEDIA_PROMOTION_STALE", "Current PromptIR, Asset, Reference, or Generation Policy lineage changed.", snapshot)
    book_id, episode, shot_id, media_role = _promotion_scope(execution)
    existing = session.query(OfficialMediaVersion).filter_by(candidate_id=candidate.candidate_id, validation_id=validation.validation_id).first()
    if existing is not None:
        authority = session.query(OfficialMediaAuthority).filter_by(official_media_version_id=existing.official_media_version_id).first()
        pointer = session.query(OfficialMediaPointer).filter_by(book_id=book_id, episode=episode, storyboard_shot_id=shot_id, media_role=media_role).first()
        if authority is not None and pointer is not None:
            return {"version": existing, "authority": authority, "pointer": pointer, "reused": True, "provider_calls": 0, "llm_calls": 0, "image_calls": 0, "video_calls": 0}
    current_versions = session.query(OfficialMediaVersion).filter_by(book_id=book_id, episode=episode, storyboard_shot_id=shot_id, media_role=media_role).all()
    revision = max([int(item.revision or 0) for item in current_versions] or [0]) + 1
    lineage_hash = _lineage_hash(candidate, execution, validation)
    version_id = f"omv-{_fingerprint({'candidate': candidate.candidate_id, 'validation': validation.validation_id, 'scope': [book_id, episode, shot_id, media_role], 'revision': revision})[:40]}"
    promotion_fingerprint = _fingerprint({"candidate_fingerprint": validation.candidate_fingerprint, "validation_fingerprint": validation.technical_validation_fingerprint, "authority_snapshot_fingerprint": validation.authority_snapshot_fingerprint, "scope": [book_id, episode, shot_id, media_role], "revision": revision, "confirmation": bool(confirmation)})
    authority_id = f"oma-{promotion_fingerprint[:40]}"
    envelope = {"schema_version": "official_media_authority_v1", "official_media_version_id": version_id, "authority_id": authority_id, "candidate_id": candidate.candidate_id, "validation_id": validation.validation_id, "lineage_hash": lineage_hash, "validation_fingerprint": validation.technical_validation_fingerprint, "promotion_fingerprint": promotion_fingerprint, "media_role": media_role, "explicit_confirmation": True}
    payload_hash = _fingerprint({"version_id": version_id, "candidate_id": candidate.candidate_id, "storage_identity": candidate.storage_identity, "checksum_sha256": candidate.checksum_sha256, "validation_id": validation.validation_id})
    version = OfficialMediaVersion(official_media_version_id=version_id, book_id=book_id, episode=episode, storyboard_shot_id=shot_id, plan_shot_id=str(execution.plan_shot_id or ""), media_role=media_role, media_type=str(candidate.media_type), candidate_id=candidate.candidate_id, candidate_fingerprint=validation.candidate_fingerprint, storage_identity=str(candidate.storage_identity), checksum_sha256=str(candidate.checksum_sha256), mime_type=str(candidate.mime_type), byte_size=int(candidate.byte_size), width=candidate.width, height=candidate.height, duration_ms=candidate.duration_ms, prompt_ir_version_id=int(candidate.prompt_ir_version_id), prompt_ir_payload_hash=str(candidate.prompt_ir_payload_hash), generation_payload_fingerprint=str(candidate.generation_payload_fingerprint), provider_request_fingerprint=str(candidate.provider_request_fingerprint), provider_response_hash=str(candidate.provider_response_hash), validation_id=validation.validation_id, validation_fingerprint=validation.technical_validation_fingerprint, revision=revision, status="CURRENT", payload_hash=payload_hash, created_at=datetime.utcnow())
    authority = OfficialMediaAuthority(authority_id=authority_id, official_media_version_id=version_id, authority_envelope_json=_canonical(envelope), payload_hash=payload_hash, lineage_hash=lineage_hash, validation_fingerprint=validation.technical_validation_fingerprint, promotion_fingerprint=promotion_fingerprint, status="CURRENT", created_at=datetime.utcnow())
    pointer_values = {"book_id": book_id, "episode": episode, "storyboard_shot_id": shot_id, "media_role": media_role, "official_media_version_id": version_id, "authority_id": authority_id}
    pointer = session.query(OfficialMediaPointer).filter_by(book_id=book_id, episode=episode, storyboard_shot_id=shot_id, media_role=media_role).first()
    if pointer is None:
        pointer = OfficialMediaPointer(**pointer_values, fingerprint=_pointer_fingerprint(pointer_values), created_at=datetime.utcnow(), updated_at=datetime.utcnow())
        session.add(pointer)
    else:
        pointer.official_media_version_id = version_id; pointer.authority_id = authority_id; pointer.fingerprint = _pointer_fingerprint(pointer_values); pointer.updated_at = datetime.utcnow()
    for old in current_versions:
        if old.official_media_version_id != version_id:
            old.status = "SUPERSEDED"
            old_authority = session.query(OfficialMediaAuthority).filter_by(official_media_version_id=old.official_media_version_id).first()
            if old_authority is not None:
                old_authority.status = "SUPERSEDED"
    session.add(version); session.add(authority)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.query(OfficialMediaVersion).filter_by(candidate_id=candidate.candidate_id, validation_id=validation.validation_id).first()
        if existing is not None:
            authority = session.query(OfficialMediaAuthority).filter_by(official_media_version_id=existing.official_media_version_id).first()
            pointer = session.query(OfficialMediaPointer).filter_by(book_id=book_id, episode=episode, storyboard_shot_id=shot_id, media_role=media_role).first()
            if authority is not None and pointer is not None:
                return {"version": existing, "authority": authority, "pointer": pointer, "reused": True, "provider_calls": 0, "llm_calls": 0, "image_calls": 0, "video_calls": 0}
        _fail("MEDIA_PROMOTION_CONFLICT", "Concurrent promotion conflicted with another official revision.")
    return {"version": version, "authority": authority, "pointer": pointer, "reused": False, "provider_calls": 0, "llm_calls": 0, "image_calls": 0, "video_calls": 0}


def resolve_current_official_media(session: Any, *, book_id: int, episode: int, storyboard_shot_id: int, media_role: str = MEDIA_ROLE_DEFAULT) -> dict[str, Any]:
    """Resolve only the exact current pointer and fail closed on any mismatch."""
    pointer = session.query(OfficialMediaPointer).filter_by(book_id=book_id, episode=episode, storyboard_shot_id=storyboard_shot_id, media_role=media_role).first()
    if pointer is None:
        _fail("MEDIA_OFFICIAL_RESOLUTION_FAILED", "Current OfficialMediaPointer is missing.")
    pointer_values = {"book_id": pointer.book_id, "episode": pointer.episode, "storyboard_shot_id": pointer.storyboard_shot_id, "media_role": pointer.media_role, "official_media_version_id": pointer.official_media_version_id, "authority_id": pointer.authority_id}
    if pointer.fingerprint != _pointer_fingerprint(pointer_values):
        _fail("MEDIA_OFFICIAL_RESOLUTION_FAILED", "OfficialMediaPointer fingerprint is tampered.")
    version = session.query(OfficialMediaVersion).filter_by(official_media_version_id=pointer.official_media_version_id).first()
    authority = session.query(OfficialMediaAuthority).filter_by(authority_id=pointer.authority_id).first()
    if version is None or authority is None or version.status != "CURRENT" or authority.status != "CURRENT" or authority.official_media_version_id != version.official_media_version_id:
        _fail("MEDIA_OFFICIAL_RESOLUTION_FAILED", "Official version or authority is missing, stale, or mismatched.")
    validation = session.query(MediaValidationRecord).filter_by(validation_id=version.validation_id).first()
    candidate = session.query(MediaCandidateRecord).filter_by(candidate_id=version.candidate_id).first()
    execution = session.query(GenerationExecutionRecord).filter_by(execution_id=getattr(validation, "execution_id", "")).first() if validation else None
    if validation is None or candidate is None or execution is None or validation.status != "TECHNICALLY_VALID":
        _fail("MEDIA_OFFICIAL_RESOLUTION_FAILED", "Validation, Candidate, or Execution lineage is missing or stale.")
    envelope = _json(authority.authority_envelope_json, {})
    if not isinstance(envelope, dict) or envelope.get("official_media_version_id") != version.official_media_version_id or envelope.get("validation_fingerprint") != validation.technical_validation_fingerprint or envelope.get("promotion_fingerprint") != authority.promotion_fingerprint or authority.payload_hash != version.payload_hash:
        _fail("MEDIA_OFFICIAL_RESOLUTION_FAILED", "OfficialMediaAuthority envelope or payload hash is tampered.")
    integrity = validate_media_candidate_integrity(session, candidate=candidate)
    if authority.lineage_hash != _lineage_hash(candidate, execution, validation):
        _fail("MEDIA_OFFICIAL_RESOLUTION_FAILED", "OfficialMediaAuthority lineage hash is tampered.")
    if integrity["candidate_fingerprint"] != version.candidate_fingerprint:
        _fail("MEDIA_OFFICIAL_RESOLUTION_FAILED", "Candidate lineage no longer matches OfficialMediaVersion.")
    technical = validate_media_candidate_technical(candidate)
    if not technical.get("valid") or technical.get("technical_validation_fingerprint") != version.validation_fingerprint:
        _fail("MEDIA_OFFICIAL_RESOLUTION_FAILED", "Canonical storage bytes no longer match the official record.")
    snapshot = _current_authority_snapshot(session, candidate=candidate, execution=execution)
    if not snapshot.get("currentness_valid") or _fingerprint(snapshot) != validation.authority_snapshot_fingerprint:
        _fail("MEDIA_OFFICIAL_RESOLUTION_FAILED", "Current upstream authority no longer matches the official record.")
    return {"pointer": pointer, "version": version, "authority": authority, "validation": validation, "candidate": candidate, "execution": execution, "technical_validation": technical, "provider_calls": 0, "llm_calls": 0, "image_calls": 0, "video_calls": 0}
