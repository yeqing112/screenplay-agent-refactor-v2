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
import shutil
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from sqlalchemy.exc import IntegrityError

from core.public_asset_storage import _load_source_bytes
from models import (
    GenerationExecutionRecord,
    MediaCandidateRecord,
    MediaPromotionRecord,
    MediaValidationRecord,
    OfficialMediaAuthority,
    OfficialMediaPointer,
    OfficialMediaVersion,
    PromptIRPointer,
    PromptIRVersion,
    VisualAssetPointer,
    VisualReferenceAuthority,
)


VALIDATION_VERSION = "media_validator_v2"
MEDIA_ROLE_DEFAULT = "SHOT_PRIMARY_IMAGE"
IMAGE_TO_VIDEO_BINDING_SCHEMA_VERSION = "image_to_video_official_media_binding_v1"
PROMOTION_REVIEW_REQUIRED = "REVIEW_REQUIRED"
PROMOTION_APPROVED = "APPROVED"
PROMOTION_REJECTED = "REJECTED"
PROMOTION_REQUEST_CHANGE = "REQUEST_CHANGE"


# Promotion computes a new scope revision before inserting the official rows.
# Serialize that critical section in-process so concurrent requests cannot
# both observe the same next revision and publish duplicate official rows.
# Database uniqueness and the existing IntegrityError replay path remain the
# cross-process safety net.
_PROMOTION_LOCK = threading.RLock()


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


def build_image_to_video_source_binding(*, official_media_authority: OfficialMediaAuthority, official_media_version: OfficialMediaVersion, source_prompt_ir_version_id: int | None = None, source_prompt_ir_payload_hash: str | None = None) -> dict[str, Any]:
    """Build the structured IMAGE -> VIDEO source contract.

    This is a lineage projection only.  It does not copy media rows or create
    a VisualReferenceAuthority and it never invokes a provider.
    """
    return {
        "schema_version": IMAGE_TO_VIDEO_BINDING_SCHEMA_VERSION,
        "authority_class": "OFFICIAL_MEDIA",
        "official_media_authority_id": str(official_media_authority.authority_id),
        "official_media_version_id": str(official_media_version.official_media_version_id),
        "media_role": str(official_media_version.media_role),
        "checksum_sha256": str(official_media_version.checksum_sha256),
        "source_prompt_ir_version_id": int(source_prompt_ir_version_id if source_prompt_ir_version_id is not None else official_media_version.prompt_ir_version_id),
        "source_prompt_ir_payload_hash": str(source_prompt_ir_payload_hash if source_prompt_ir_payload_hash is not None else official_media_version.prompt_ir_payload_hash),
    }


def validate_image_to_video_source_binding(session: Any, *, execution: GenerationExecutionRecord, binding: dict[str, Any]) -> dict[str, Any]:
    """Validate an IMAGE_TO_VIDEO source against current OfficialMedia truth."""
    if not isinstance(binding, dict):
        _fail("IMAGE_TO_VIDEO_SOURCE_BINDING_INVALID", "IMAGE_TO_VIDEO requires a structured OfficialMedia source binding.")
    required = ("official_media_authority_id", "official_media_version_id", "media_role", "checksum_sha256", "source_prompt_ir_version_id", "source_prompt_ir_payload_hash")
    missing = [key for key in required if str(binding.get(key) or "").strip() == ""]
    if binding.get("authority_class") != "OFFICIAL_MEDIA" or missing:
        _fail("IMAGE_TO_VIDEO_SOURCE_BINDING_INVALID", "IMAGE_TO_VIDEO source binding must identify current OfficialMedia authority and PromptIR lineage.", {"missing": missing, "authority_class": binding.get("authority_class")})
    authority = session.query(OfficialMediaAuthority).filter_by(authority_id=str(binding["official_media_authority_id"])).first()
    version = session.query(OfficialMediaVersion).filter_by(official_media_version_id=str(binding["official_media_version_id"])).first()
    pointer = session.query(OfficialMediaPointer).filter_by(book_id=execution.book_id, episode=execution.episode, storyboard_shot_id=execution.storyboard_shot_id, media_role=str(binding["media_role"])).first()
    prompt = session.query(PromptIRVersion).filter_by(id=int(binding["source_prompt_ir_version_id"])).first()
    prompt_pointer = session.query(PromptIRPointer).filter_by(
        book_id=execution.book_id,
        episode=execution.episode,
        storyboard_shot_id=execution.storyboard_shot_id,
        target_media="IMAGE",
    ).first()
    valid = bool(
        authority and version and pointer and prompt
        and authority.status == "CURRENT"
        and version.status == "CURRENT"
        and pointer.authority_id == authority.authority_id
        and pointer.official_media_version_id == version.official_media_version_id
        and int(version.book_id) == int(execution.book_id)
        and int(version.episode) == int(execution.episode)
        and int(version.storyboard_shot_id) == int(execution.storyboard_shot_id)
        and str(version.media_type) == "IMAGE"
        and str(version.media_role) == "SHOT_PRIMARY_IMAGE"
        and str(binding["media_role"]) == "SHOT_PRIMARY_IMAGE"
        and str(binding["checksum_sha256"]) == str(version.checksum_sha256)
        and int(prompt.id) == int(version.prompt_ir_version_id)
        and str(prompt.payload_hash) == str(version.prompt_ir_payload_hash)
        and str(binding["source_prompt_ir_payload_hash"]) == str(version.prompt_ir_payload_hash)
        and prompt_pointer is not None
        and int(prompt_pointer.prompt_ir_version_id) == int(version.prompt_ir_version_id)
        and str(prompt_pointer.payload_hash) == str(version.prompt_ir_payload_hash)
    )
    if not valid:
        _fail("IMAGE_TO_VIDEO_SOURCE_BINDING_INVALID", "IMAGE_TO_VIDEO source is not the current OfficialMedia IMAGE authority for this shot.", {"authority_id": getattr(authority, "authority_id", None), "version_id": getattr(version, "official_media_version_id", None), "pointer_authority_id": getattr(pointer, "authority_id", None), "prompt_id": getattr(prompt, "id", None)})
    return {"valid": True, "binding": dict(binding), "authority_id": authority.authority_id, "version_id": version.official_media_version_id, "source_prompt_ir_version_id": prompt.id, "provider_calls": 0, "llm_calls": 0, "image_calls": 0, "video_calls": 0}


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


def _probe_video(data: bytes) -> tuple[str, int | None, int | None, int | None]:
    """Parse a real video container through the declared ffprobe dependency."""
    executable = os.getenv("FFPROBE_PATH") or shutil.which("ffprobe")
    if not executable:
        _fail("MEDIA_VIDEO_VALIDATOR_UNAVAILABLE", "ffprobe is required for deterministic VIDEO technical validation.")
    try:
        result = subprocess.run(
            [executable, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", "pipe:0"],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=15,
        )
        parsed = json.loads(result.stdout.decode("utf-8", errors="replace") or "{}")
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError) as exc:
        _fail("MEDIA_VIDEO_CONTAINER_INVALID", "Video bytes could not be parsed by ffprobe.", {"error": str(exc)})
    if result.returncode != 0 or not isinstance(parsed, dict):
        _fail("MEDIA_VIDEO_CONTAINER_INVALID", "Video bytes are not a valid supported container.", {"stderr": result.stderr.decode("utf-8", errors="replace")[-500:]})
    streams = parsed.get("streams") if isinstance(parsed.get("streams"), list) else []
    video_stream = next((item for item in streams if isinstance(item, dict) and item.get("codec_type") == "video"), None)
    fmt = parsed.get("format") if isinstance(parsed.get("format"), dict) else {}
    if not video_stream or str(fmt.get("format_name") or "").lower().split(",")[0] not in {"mov", "mp4", "m4v"}:
        _fail("MEDIA_VIDEO_CONTAINER_INVALID", "Candidate bytes do not contain a valid MP4 video stream.")
    try:
        duration = float(video_stream.get("duration") or fmt.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0
    width = int(video_stream.get("width") or 0) or None
    height = int(video_stream.get("height") or 0) or None
    duration_ms = int(round(duration * 1000)) if duration > 0 else None
    if not duration_ms:
        _fail("MEDIA_VIDEO_DURATION_MISSING", "Video container does not expose a positive duration.")
    return "video/mp4", width, height, duration_ms


def _detect_media(data: bytes, declared_type: str) -> tuple[str, int | None, int | None, int | None]:
    if not data:
        _fail("MEDIA_BYTES_EMPTY", "Candidate storage bytes are empty.")
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return "image/png", int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big"), None
    if data.startswith(b"\xff\xd8\xff"):
        try:
            from PIL import Image

            with Image.open(io.BytesIO(data)) as image:
                return "image/jpeg", int(image.width), int(image.height), None
        except Exception:
            _fail("MEDIA_BYTES_INVALID", "JPEG candidate bytes could not be decoded.")
    if data.startswith(b"RIFF") and len(data) >= 30 and data[8:12] == b"WEBP":
        try:
            from PIL import Image

            with Image.open(io.BytesIO(data)) as image:
                return "image/webp", int(image.width), int(image.height), None
        except Exception:
            _fail("MEDIA_BYTES_INVALID", "WebP candidate bytes could not be decoded.")
    # An MP4 must be parsed as a real container.  The signature check only
    # selects the parser; declared MIME or filename never establishes truth.
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return _probe_video(data)
    # Do not infer media truth from a filename or a declared MIME type.
    _fail("MEDIA_MIME_UNDETECTABLE", "Candidate bytes have no supported, parseable media signature.", {"declared_mime_type": declared_type})
    raise AssertionError("unreachable")


def validate_media_candidate_technical(candidate: MediaCandidateRecord) -> dict[str, Any]:
    """Pure deterministic storage validation; it never writes or calls a provider."""
    data, declared_content_type, source = _read_candidate_bytes(candidate)
    observed_mime, width, height, duration_ms = _detect_media(data, declared_content_type)
    expected_mime = str(candidate.mime_type or "").split(";", 1)[0].strip().lower()
    expected_media_type = str(candidate.media_type or "").strip().upper()
    checksum = hashlib.sha256(data).hexdigest()
    payload = {
        "schema_version": "media_technical_validation_v2",
        "bytes_valid": bool(data),
        "byte_size": len(data),
        "byte_size_valid": len(data) == int(candidate.byte_size or 0),
        "checksum_observed": checksum,
        "checksum_valid": checksum == str(candidate.checksum_sha256 or ""),
        "mime_observed": observed_mime,
        "mime_valid": observed_mime == expected_mime,
        "media_type": expected_media_type,
        "media_type_valid": (expected_media_type == "IMAGE" and observed_mime.startswith("image/")) or (expected_media_type == "VIDEO" and observed_mime.startswith("video/")),
        "width_observed": width,
        "height_observed": height,
        "dimensions_valid": width == candidate.width and height == candidate.height and bool(width) and bool(height),
        "duration_observed_ms": duration_ms,
        "duration_valid": (expected_media_type == "IMAGE" and candidate.duration_ms is None and duration_ms is None)
        or (expected_media_type == "VIDEO" and candidate.duration_ms is not None and duration_ms is not None and abs(int(candidate.duration_ms) - int(duration_ms)) <= 100),
        "storage_identity_valid": bool(str(candidate.storage_identity or "").strip()),
        "storage_valid": bool(source),
        "storage_source": source,
        "metadata_complete": bool(
            str(candidate.media_type or "").strip()
            and str(candidate.mime_type or "").strip()
            and int(candidate.byte_size or 0) > 0
            and int(candidate.width or 0) > 0
            and int(candidate.height or 0) > 0
            and isinstance(candidate.candidate_metadata, dict)
        ),
    }
    payload["valid"] = all(
        payload[key]
        for key in ("bytes_valid", "byte_size_valid", "checksum_valid", "mime_valid", "media_type_valid", "dimensions_valid", "duration_valid", "storage_identity_valid", "storage_valid", "metadata_complete")
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


def _asset_authority_snapshot(session: Any, *, book_id: int, prompt_payload: dict[str, Any]) -> dict[str, Any]:
    """Use the PromptIR Authority asset currentness service."""
    from core.prompt_ir_phase_e import build_current_prompt_ir_asset_authority

    return build_current_prompt_ir_asset_authority(session, book_id=book_id, prompt_payload=prompt_payload)


def _storyboard_shot_fingerprint(shot: Any) -> str:
    """Return the immutable storyboard identity used by Phase I binding."""
    projection = str(getattr(shot, "projection_fingerprint", "") or "").strip()
    if projection:
        return projection
    return _fingerprint(
        {
            "schema_version": "storyboard_shot_identity_v1",
            "id": getattr(shot, "id", None),
            "book_id": getattr(shot, "book_id", None),
            "episode": getattr(shot, "episode", None),
            "shot_id": getattr(shot, "shot_id", None),
            "plan_shot_id": getattr(shot, "plan_shot_id", ""),
            "scene_id": getattr(shot, "scene_id", ""),
        }
    )


def _production_asset_binding_snapshot(session: Any, *, storyboard_shot_id: int) -> dict[str, Any]:
    """Snapshot explicit H2.2 bindings without falling back to legacy metadata."""
    from core.production_asset_authority import AssetBindingInvalid, resolve_shot_assets
    from models import ShotAssetBinding

    rows = session.query(ShotAssetBinding).filter_by(storyboard_shot_id=storyboard_shot_id).all()
    if not rows:
        return {"schema_version": "phase_h2_2_binding_snapshot_v1", "declared": False, "currentness_valid": True, "bindings": [], "fingerprint": _fingerprint([])}
    try:
        resolved = resolve_shot_assets(session, storyboard_shot_id=storyboard_shot_id)
    except AssetBindingInvalid as exc:
        return {
            "schema_version": "phase_h2_2_binding_snapshot_v1",
            "declared": True,
            "currentness_valid": False,
            "bindings": [],
            "diagnostics": [{"code": exc.code, "message": exc.message, "diagnostics": exc.diagnostics}],
            "fingerprint": _fingerprint({"invalid": True, "diagnostics": exc.diagnostics}),
        }

    def compact(asset: dict[str, Any]) -> dict[str, Any]:
        return {
            "entity_id": asset["entity_id"],
            "asset_type": asset["asset_type"],
            "authority_id": asset["authority_id"],
            "version_id": asset["version_id"],
            "authority_fingerprint": asset["authority_fingerprint"],
            "version_fingerprint": asset["version_fingerprint"],
            "pointer_fingerprint": asset["pointer_fingerprint"],
        }

    bindings = [compact(item) for item in resolved["characters"]]
    if resolved.get("scene") is not None:
        bindings.append(compact(resolved["scene"]))
    bindings.extend(compact(item) for item in resolved["props"])
    bindings.sort(key=lambda item: (item["asset_type"], item["entity_id"]))
    return {
        "schema_version": "phase_h2_2_binding_snapshot_v1",
        "declared": True,
        "currentness_valid": True,
        "bindings": bindings,
        "fingerprint": _fingerprint(bindings),
    }


def _prompt_ir_current_scope_snapshot(session: Any, *, candidate: MediaCandidateRecord, execution: GenerationExecutionRecord) -> dict[str, Any]:
    """Project the single PromptIR current-scope contract for Media Authority."""
    from fastapi import HTTPException
    from core.prompt_ir_phase_e import validate_prompt_ir_current_scope

    target_media = str(execution.target_media or "").strip()
    candidate_media = str(candidate.media_type or "").strip()
    prompt = {
        "declared": True,
        "candidate_version_id": int(candidate.prompt_ir_version_id),
        "candidate_payload_hash": str(candidate.prompt_ir_payload_hash),
        "pointer_present": False,
        "pointer_scope_valid": False,
        "pointer_payload_integrity_valid": False,
        "prompt_authority_valid": False,
        "prompt_current_lineage_valid": False,
        "current_version_id": None,
        "current_payload_hash": "",
        "pointer_payload_hash": "",
        "current_generation_policy_fingerprint": "",
        "generation_policy_matches": False,
        "matches": False,
        "errors": [],
    }
    if target_media not in {"IMAGE", "VIDEO"} or candidate_media != target_media:
        prompt["errors"] = [{"code": "MEDIA_CURRENT_PROMPT_IR_INVALID", "message": "Execution and candidate media types must be exact IMAGE or VIDEO scope values."}]
        return prompt

    pointer = session.query(PromptIRPointer).filter_by(
        book_id=execution.book_id,
        episode=execution.episode,
        storyboard_shot_id=execution.storyboard_shot_id,
        target_media=target_media,
    ).first()
    if pointer is None:
        prompt["errors"] = [{"code": "PROMPT_IR_POINTER_MISSING", "message": "Current PromptIR pointer is missing for the execution media scope."}]
        return prompt

    prompt["pointer_present"] = True
    prompt["pointer_scope_valid"] = str(pointer.target_media or "") == target_media
    prompt["pointer_payload_hash"] = str(pointer.payload_hash or "")
    try:
        validated = validate_prompt_ir_current_scope(
            session,
            book_id=execution.book_id,
            episode=execution.episode,
            storyboard_shot_id=execution.storyboard_shot_id,
            target_media=target_media,
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        prompt["errors"] = [{"code": detail.get("code", "PROMPT_IR_POINTER_INVALID"), "message": detail.get("message", "Current PromptIR scope validation failed.")}]
        return prompt
    except Exception as exc:  # pragma: no cover - defensive authority boundary
        prompt["errors"] = [{"code": "PROMPT_IR_POINTER_INVALID", "message": str(exc)}]
        return prompt

    version = validated["version"]
    authority = validated["authority"]
    payload = validated["payload"]
    policy = payload.get("generation_policy") if isinstance(payload, dict) and isinstance(payload.get("generation_policy"), dict) else {}
    policy_fp = str(policy.get("fingerprint") or "")
    execution_policy_fp = str(execution.generation_policy_fingerprint or "")
    prompt["current_version_id"] = getattr(version, "id", None)
    prompt["current_payload_hash"] = str(getattr(version, "payload_hash", "") or "")
    prompt["current_generation_policy_fingerprint"] = policy_fp
    prompt["pointer_payload_integrity_valid"] = bool(
        prompt["pointer_scope_valid"]
        and pointer.payload_hash == version.payload_hash
        and int(candidate.prompt_ir_version_id) == int(version.id)
        and str(candidate.prompt_ir_payload_hash) == str(version.payload_hash)
    )
    prompt["prompt_authority_valid"] = bool(validated.get("integrity_valid") and authority is not None)
    prompt["prompt_current_lineage_valid"] = bool(validated.get("current_lineage_valid"))
    if not prompt["prompt_current_lineage_valid"]:
        prompt["errors"] = list(validated.get("diagnostics") or [])
    prompt["generation_policy_matches"] = bool(policy_fp) and policy_fp == execution_policy_fp
    prompt["matches"] = bool(prompt["pointer_payload_integrity_valid"] and prompt["prompt_authority_valid"])
    prompt["currentness_valid"] = bool(
        prompt["pointer_present"]
        and prompt["pointer_scope_valid"]
        and prompt["pointer_payload_integrity_valid"]
        and prompt["prompt_authority_valid"]
        and prompt["prompt_current_lineage_valid"]
        and prompt["generation_policy_matches"]
    )
    prompt["_payload"] = payload
    return prompt


def _current_authority_snapshot(session: Any, *, candidate: MediaCandidateRecord, execution: GenerationExecutionRecord) -> dict[str, Any]:
    prompt = _prompt_ir_current_scope_snapshot(session, candidate=candidate, execution=execution)
    prompt_payload = prompt.pop("_payload", {})
    asset_authority = _asset_authority_snapshot(session, book_id=execution.book_id, prompt_payload=prompt_payload)
    request = _json(execution.request_snapshot_json, {})
    generation_policy = request.get("generation_policy") if isinstance(request, dict) else {}
    source_binding = request.get("image_to_video_source") if isinstance(request, dict) else None
    image_to_video_source = {"required": str(execution.target_media or "").strip() == "VIDEO" and isinstance(generation_policy, dict) and str(generation_policy.get("mode") or "").strip() == "IMAGE_TO_VIDEO", "valid": True, "binding": source_binding}
    if image_to_video_source["required"]:
        try:
            image_to_video_source = {"required": True, **validate_image_to_video_source_binding(session, execution=execution, binding=source_binding)}
        except MediaAuthorityError as exc:
            image_to_video_source = {"required": True, "valid": False, "code": exc.code, "diagnostics": exc.diagnostics, "binding": source_binding}
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
    production_asset_binding = _production_asset_binding_snapshot(session, storyboard_shot_id=int(execution.storyboard_shot_id))
    return {
        "schema_version": "media_authority_snapshot_v1",
        "prompt_ir": prompt,
        "asset": asset,
        "asset_authority": asset_authority,
        "reference": reference,
        "production_asset_binding": production_asset_binding,
        "generation_policy_fingerprint": str(execution.generation_policy_fingerprint or ""),
        "generation_policy_current_fingerprint": str(prompt.get("current_generation_policy_fingerprint") or ""),
        "generation_policy_matches": bool(prompt.get("generation_policy_matches")),
        "generation_policy_request": generation_policy if isinstance(generation_policy, dict) else {},
        "image_to_video_source": image_to_video_source,
        "reference_bindings_fingerprint": str(execution.reference_bindings_fingerprint or ""),
        "currentness_valid": bool(prompt.get("currentness_valid")) and bool(image_to_video_source.get("valid", True)) and all(item.get("pointer_matches", True) for item in asset.get("bindings", [])) and all(item.get("pointer_matches", True) for item in asset_authority.get("bindings", [])) and all(item.get("exists") and item.get("pointer_matches", True) and str(item.get("status") or "").upper() in {"LOCKED", "REFERENCE_LOCKED"} and str(item.get("stale_status") or "FRESH").upper() == "FRESH" for item in reference.get("bindings", [])) and bool(production_asset_binding.get("currentness_valid", True)),
    }


def _validation_fingerprint(record: MediaValidationRecord) -> str:
    return _fingerprint({"validation_id": record.validation_id, "candidate_fingerprint": record.candidate_fingerprint, "technical_validation_fingerprint": record.technical_validation_fingerprint, "authority_snapshot_fingerprint": record.authority_snapshot_fingerprint, "status": record.status})


def _promotion_review_fingerprint(*, candidate_id: str, validation_id: str, execution_id: str) -> str:
    return _fingerprint(
        {
            "schema_version": "media_promotion_review_v1",
            "candidate_id": candidate_id,
            "validation_id": validation_id,
            "execution_id": execution_id,
        }
    )


def _ensure_promotion_record(
    session: Any,
    *,
    candidate: MediaCandidateRecord,
    validation: MediaValidationRecord,
    execution: GenerationExecutionRecord,
) -> MediaPromotionRecord:
    """Create or reuse the review gate for one validated candidate."""
    existing = session.query(MediaPromotionRecord).filter_by(candidate_id=candidate.candidate_id).first()
    if existing is not None:
        if existing.validation_id != validation.validation_id or existing.execution_id != execution.execution_id:
            _fail("MEDIA_PROMOTION_REVIEW_TAMPERED", "Promotion review is bound to a different validation or execution.")
        return existing
    fingerprint = _promotion_review_fingerprint(
        candidate_id=str(candidate.candidate_id),
        validation_id=str(validation.validation_id),
        execution_id=str(execution.execution_id),
    )
    row = MediaPromotionRecord(
        promotion_id=f"mpr-{fingerprint[:40]}",
        candidate_id=str(candidate.candidate_id),
        validation_id=str(validation.validation_id),
        execution_id=str(execution.execution_id),
        review_status=PROMOTION_REVIEW_REQUIRED,
        decision=None,
        reviewer="",
        review_notes="",
        promotion_fingerprint=fingerprint,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    try:
        session.add(row)
        session.flush()
    except IntegrityError:
        session.rollback()
        existing = session.query(MediaPromotionRecord).filter_by(candidate_id=candidate.candidate_id).first()
        if existing is None:
            raise
        return existing
    return row


def get_promotion_record(session: Any, candidate_id: str) -> MediaPromotionRecord | None:
    """Return the review record for a candidate without mutating state."""
    return session.query(MediaPromotionRecord).filter_by(candidate_id=str(candidate_id)).first()


def validate_media_candidate(session: Any, candidate_id: str, *, validator_version: str = VALIDATION_VERSION) -> dict[str, Any]:
    """Create or reuse one deterministic validation record."""
    integrity = validate_media_candidate_integrity(session, candidate_id)
    candidate = integrity["candidate"]
    execution = integrity["execution"]
    try:
        technical = validate_media_candidate_technical(candidate)
    except MediaAuthorityError as exc:
        candidate.validation_status = "FAILED"
        session.commit()
        _fail(
            "MEDIA_VALIDATION_FAILED",
            "Candidate failed deterministic technical validation.",
            {"cause_code": exc.code, "cause_message": exc.message, "diagnostics": exc.diagnostics},
        )
    if not technical.get("valid"):
        candidate.validation_status = "FAILED"
        session.commit()
        _fail("MEDIA_VALIDATION_FAILED", "Candidate failed deterministic technical validation.", technical)
    snapshot = _current_authority_snapshot(session, candidate=candidate, execution=execution)
    if not snapshot.get("currentness_valid"):
        candidate.validation_status = "FAILED"
        session.commit()
        _fail(
            "MEDIA_CURRENT_PROMPT_IR_INVALID",
            "Candidate cannot be validated without a current exact-scope PromptIR authority.",
            snapshot,
        )
    snapshot_fp = _fingerprint(snapshot)
    existing = session.query(MediaValidationRecord).filter_by(candidate_fingerprint=integrity["candidate_fingerprint"], authority_snapshot_fingerprint=snapshot_fp, validator_version=validator_version).first()
    if existing is not None:
        candidate.validation_status = "REVIEW_REQUIRED"
        promotion = _ensure_promotion_record(session, candidate=candidate, validation=existing, execution=execution)
        session.commit()
        return {"validation": existing, "validation_id": existing.validation_id, "promotion": promotion, "reused": True, "provider_calls": 0, "llm_calls": 0, "image_calls": 0, "video_calls": 0}
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
        candidate.validation_status = "REVIEW_REQUIRED"
        promotion = _ensure_promotion_record(session, candidate=candidate, validation=row, execution=execution)
        session.commit()
        return {"validation": row, "validation_id": row.validation_id, "promotion": promotion, "reused": True, "provider_calls": 0, "llm_calls": 0, "image_calls": 0, "video_calls": 0}
    candidate.validation_status = "REVIEW_REQUIRED"
    promotion = _ensure_promotion_record(session, candidate=candidate, validation=row, execution=execution)
    session.commit()
    return {"validation": row, "validation_id": row.validation_id, "promotion": promotion, "reused": False, "provider_calls": 0, "llm_calls": 0, "image_calls": 0, "video_calls": 0}


def _load_validation(session: Any, validation_id: str) -> MediaValidationRecord:
    row = session.query(MediaValidationRecord).filter_by(validation_id=str(validation_id)).first()
    if row is None:
        _fail("MEDIA_VALIDATION_NOT_FOUND", "Validation record does not exist.", status_code=404)
    return row


def _validate_validation_integrity(row: MediaValidationRecord) -> None:
    technical = _json(row.technical_validation_payload_json, {})
    if not isinstance(technical, dict):
        _fail("MEDIA_VALIDATION_TAMPERED", "Validation technical payload is not an object.")
    technical_fp = technical.get("technical_validation_fingerprint")
    basis = dict(technical)
    basis.pop("technical_validation_fingerprint", None)
    if technical_fp != row.technical_validation_fingerprint or _fingerprint(basis) != str(row.technical_validation_fingerprint or ""):
        _fail("MEDIA_VALIDATION_TAMPERED", "Validation technical payload and fingerprint do not match.")
    snapshot = _json(row.authority_snapshot_json, {})
    if not isinstance(snapshot, dict) or _fingerprint(snapshot) != str(row.authority_snapshot_fingerprint or ""):
        _fail("MEDIA_VALIDATION_TAMPERED", "Validation authority snapshot and fingerprint do not match.")


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


def _promote_media_candidate(
    session: Any,
    candidate_id: str,
    validation_id: str,
    *,
    confirmation: bool | str,
    promotion_id: str | None = None,
    reviewer: str = "",
    decision: str | None = None,
    review_notes: str = "",
) -> dict[str, Any]:
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
    _validate_validation_integrity(validation)
    integrity = validate_media_candidate_integrity(session, candidate_id)
    candidate = integrity["candidate"]
    execution = integrity["execution"]
    if validation.candidate_id != candidate.candidate_id or validation.execution_id != execution.execution_id or validation.candidate_fingerprint != integrity["candidate_fingerprint"]:
        _fail("MEDIA_VALIDATION_TAMPERED", "Validation is not bound to the current Candidate and execution.")
    promotion = _ensure_promotion_record(session, candidate=candidate, validation=validation, execution=execution)
    if promotion_id and str(promotion.promotion_id) != str(promotion_id):
        _fail("MEDIA_PROMOTION_REVIEW_TAMPERED", "Promotion review id does not match the candidate.")
    normalized_decision = str(decision or "").strip().upper()
    if normalized_decision:
        if normalized_decision not in {"APPROVE", "REJECT", "REQUEST_CHANGE"}:
            _fail("MEDIA_PROMOTION_DECISION_INVALID", "Promotion decision must be APPROVE, REJECT, or REQUEST_CHANGE.", status_code=400)
        if not str(reviewer or "").strip():
            _fail("MEDIA_PROMOTION_REVIEWER_REQUIRED", "An explicit reviewer is required for a promotion decision.", status_code=400)
        promotion.decision = normalized_decision
        promotion.reviewer = str(reviewer).strip()
        promotion.review_notes = str(review_notes or "")[:4000]
        promotion.review_status = PROMOTION_APPROVED if normalized_decision == "APPROVE" else (PROMOTION_REJECTED if normalized_decision == "REJECT" else PROMOTION_REQUEST_CHANGE)
        promotion.updated_at = datetime.utcnow()
        session.flush()
    elif promotion.review_status == PROMOTION_REVIEW_REQUIRED:
        # Existing internal callers use explicit confirmation as the legacy
        # review boundary.  Record that approval durably as SYSTEM so the
        # candidate still crosses Review Required -> Approved before publish.
        promotion.decision = "APPROVE"
        promotion.reviewer = str(reviewer or "SYSTEM").strip() or "SYSTEM"
        promotion.review_notes = str(review_notes or "")[:4000]
        promotion.review_status = PROMOTION_APPROVED
        promotion.updated_at = datetime.utcnow()
        session.flush()
    if promotion.review_status != PROMOTION_APPROVED or promotion.decision != "APPROVE":
        _fail("MEDIA_PROMOTION_REVIEW_REQUIRED", "Candidate requires an approved promotion review before official publication.")
    technical = validate_media_candidate_technical(candidate)
    if not technical.get("valid") or technical.get("technical_validation_fingerprint") != validation.technical_validation_fingerprint:
        _fail("MEDIA_PROMOTION_STALE", "Candidate bytes or technical validation fingerprint changed.", technical)
    snapshot = _current_authority_snapshot(session, candidate=candidate, execution=execution)
    snapshot_fp = _fingerprint(snapshot)
    if not snapshot.get("currentness_valid") or snapshot_fp != validation.authority_snapshot_fingerprint:
        _mark_validation_stale(session, validation)
        _fail("MEDIA_PROMOTION_STALE", "Current PromptIR, Asset, Reference, or Generation Policy lineage changed.", snapshot)
    book_id, episode, shot_id, media_role = _promotion_scope(execution)
    from models import StoryboardShot

    storyboard_shot = session.query(StoryboardShot).filter_by(id=shot_id).first()
    production_asset_binding = snapshot.get("production_asset_binding") or {
        "schema_version": "phase_h2_2_binding_snapshot_v1",
        "declared": False,
        "currentness_valid": True,
        "bindings": [],
        "fingerprint": _fingerprint([]),
    }
    storyboard_fingerprint = _storyboard_shot_fingerprint(storyboard_shot) if storyboard_shot is not None else ""
    existing = session.query(OfficialMediaVersion).filter_by(candidate_id=candidate.candidate_id, validation_id=validation.validation_id).first()
    if existing is not None:
        authority = session.query(OfficialMediaAuthority).filter_by(official_media_version_id=existing.official_media_version_id).first()
        pointer = session.query(OfficialMediaPointer).filter_by(book_id=book_id, episode=episode, storyboard_shot_id=shot_id, media_role=media_role).first()
        if authority is not None and pointer is not None:
            promotion.official_media_version_id = existing.official_media_version_id
            promotion.authority_id = authority.authority_id
            promotion.updated_at = datetime.utcnow()
            candidate.validation_status = "TECHNICALLY_VALID"
            session.commit()
            return {"version": existing, "authority": authority, "pointer": pointer, "promotion": promotion, "reused": True, "provider_calls": 0, "llm_calls": 0, "image_calls": 0, "video_calls": 0}
    current_versions = session.query(OfficialMediaVersion).filter_by(book_id=book_id, episode=episode, storyboard_shot_id=shot_id, media_role=media_role).all()
    revision = max([int(item.revision or 0) for item in current_versions] or [0]) + 1
    lineage_hash = _lineage_hash(candidate, execution, validation)
    version_id = f"omv-{_fingerprint({'candidate': candidate.candidate_id, 'validation': validation.validation_id, 'scope': [book_id, episode, shot_id, media_role], 'revision': revision})[:40]}"
    promotion_fingerprint = _fingerprint({"candidate_fingerprint": validation.candidate_fingerprint, "validation_fingerprint": validation.technical_validation_fingerprint, "authority_snapshot_fingerprint": validation.authority_snapshot_fingerprint, "scope": [book_id, episode, shot_id, media_role], "revision": revision, "confirmation": bool(confirmation)})
    authority_id = f"oma-{promotion_fingerprint[:40]}"
    envelope = {
        "schema_version": "official_media_authority_v1",
        "official_media_version_id": version_id,
        "authority_id": authority_id,
        "candidate_id": candidate.candidate_id,
        "validation_id": validation.validation_id,
        "generation_execution_id": execution.execution_id,
        "storyboard_shot_id": shot_id,
        "storyboard_shot_fingerprint": storyboard_fingerprint,
        "plan_shot_id": str(execution.plan_shot_id or ""),
        "prompt_ir_version_id": int(candidate.prompt_ir_version_id),
        "prompt_ir_payload_hash": str(candidate.prompt_ir_payload_hash),
        "lineage_hash": lineage_hash,
        "validation_fingerprint": validation.technical_validation_fingerprint,
        "promotion_fingerprint": promotion_fingerprint,
        "media_role": media_role,
        "storage_identity": str(candidate.storage_identity),
        "checksum_sha256": str(candidate.checksum_sha256),
        "production_asset_binding": production_asset_binding,
        "explicit_confirmation": True,
    }
    payload_hash = _fingerprint({"version_id": version_id, "candidate_id": candidate.candidate_id, "storage_identity": candidate.storage_identity, "checksum_sha256": candidate.checksum_sha256, "validation_id": validation.validation_id})
    version = OfficialMediaVersion(official_media_version_id=version_id, book_id=book_id, episode=episode, storyboard_shot_id=shot_id, plan_shot_id=str(execution.plan_shot_id or ""), media_role=media_role, media_type=str(candidate.media_type), candidate_id=candidate.candidate_id, candidate_fingerprint=validation.candidate_fingerprint, storage_identity=str(candidate.storage_identity), checksum_sha256=str(candidate.checksum_sha256), mime_type=str(candidate.mime_type), byte_size=int(candidate.byte_size), width=candidate.width, height=candidate.height, duration_ms=candidate.duration_ms, prompt_ir_version_id=int(candidate.prompt_ir_version_id), prompt_ir_payload_hash=str(candidate.prompt_ir_payload_hash), generation_payload_fingerprint=str(candidate.generation_payload_fingerprint), provider_request_fingerprint=str(candidate.provider_request_fingerprint), provider_response_hash=str(candidate.provider_response_hash), validation_id=validation.validation_id, validation_fingerprint=validation.technical_validation_fingerprint, revision=revision, status="CURRENT", payload_hash=payload_hash, created_at=datetime.utcnow())
    authority = OfficialMediaAuthority(authority_id=authority_id, official_media_version_id=version_id, authority_envelope_json=_canonical(envelope), payload_hash=payload_hash, lineage_hash=lineage_hash, validation_fingerprint=validation.technical_validation_fingerprint, promotion_fingerprint=promotion_fingerprint, status="CURRENT", created_at=datetime.utcnow())
    pointer_values = {"book_id": book_id, "episode": episode, "storyboard_shot_id": shot_id, "media_role": media_role, "official_media_version_id": version_id, "authority_id": authority_id}
    pointer = session.query(OfficialMediaPointer).filter_by(book_id=book_id, episode=episode, storyboard_shot_id=shot_id, media_role=media_role).first()
    pointer_is_new = pointer is None
    if pointer is None:
        pointer = OfficialMediaPointer(**pointer_values, fingerprint=_pointer_fingerprint(pointer_values), created_at=datetime.utcnow(), updated_at=datetime.utcnow())
    else:
        pointer.official_media_version_id = version_id; pointer.authority_id = authority_id; pointer.fingerprint = _pointer_fingerprint(pointer_values); pointer.updated_at = datetime.utcnow()
    for old in current_versions:
        if old.official_media_version_id != version_id:
            old.status = "SUPERSEDED"
            old_authority = session.query(OfficialMediaAuthority).filter_by(official_media_version_id=old.official_media_version_id).first()
            if old_authority is not None:
                old_authority.status = "SUPERSEDED"
    # The migration has a database FK from authority -> version while the
    # legacy ORM model intentionally has no relationship. Flush in dependency
    # order so SQLite foreign-key enforcement cannot observe a transient
    # authority row before its official version exists.
    try:
        session.add(version)
        session.flush()
        session.add(authority)
        if pointer_is_new:
            session.add(pointer)
        promotion.official_media_version_id = version_id
        promotion.authority_id = authority_id
        promotion.updated_at = datetime.utcnow()
        candidate.validation_status = "TECHNICALLY_VALID"
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.query(OfficialMediaVersion).filter_by(candidate_id=candidate.candidate_id, validation_id=validation.validation_id).first()
        if existing is not None:
            authority = session.query(OfficialMediaAuthority).filter_by(official_media_version_id=existing.official_media_version_id).first()
            pointer = session.query(OfficialMediaPointer).filter_by(book_id=book_id, episode=episode, storyboard_shot_id=shot_id, media_role=media_role).first()
            if authority is not None and pointer is not None:
                promotion = session.query(MediaPromotionRecord).filter_by(candidate_id=candidate.candidate_id).first() or promotion
                promotion.official_media_version_id = existing.official_media_version_id
                promotion.authority_id = authority.authority_id
                session.commit()
                return {"version": existing, "authority": authority, "pointer": pointer, "promotion": promotion, "reused": True, "provider_calls": 0, "llm_calls": 0, "image_calls": 0, "video_calls": 0}
        _fail("MEDIA_PROMOTION_CONFLICT", "Concurrent promotion conflicted with another official revision.")
    return {"version": version, "authority": authority, "pointer": pointer, "promotion": promotion, "reused": False, "provider_calls": 0, "llm_calls": 0, "image_calls": 0, "video_calls": 0}


def promote_media_candidate(
    session: Any,
    candidate_id: str,
    validation_id: str,
    *,
    confirmation: bool | str,
    promotion_id: str | None = None,
    reviewer: str = "",
    decision: str | None = None,
    review_notes: str = "",
) -> dict[str, Any]:
    """Promote a validated candidate with an in-process atomicity guard."""
    with _PROMOTION_LOCK:
        return _promote_media_candidate(
            session,
            candidate_id,
            validation_id,
            confirmation=confirmation,
            promotion_id=promotion_id,
            reviewer=reviewer,
            decision=decision,
            review_notes=review_notes,
        )


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
    if not (
        str(execution.target_media or "").strip() in {"IMAGE", "VIDEO"}
        and str(candidate.media_type or "").strip() == str(execution.target_media or "").strip()
        and str(version.media_type or "").strip() == str(execution.target_media or "").strip()
    ):
        _fail("MEDIA_OFFICIAL_RESOLUTION_FAILED", "Execution, Candidate, and OfficialMedia media types disagree.")
    try:
        _validate_validation_integrity(validation)
    except MediaAuthorityError:
        _fail("MEDIA_OFFICIAL_RESOLUTION_FAILED", "MediaValidationRecord integrity is tampered.")
    envelope = _json(authority.authority_envelope_json, {})
    if not isinstance(envelope, dict) or envelope.get("official_media_version_id") != version.official_media_version_id or envelope.get("authority_id") != authority.authority_id or envelope.get("candidate_id") != candidate.candidate_id or envelope.get("validation_id") != validation.validation_id or envelope.get("lineage_hash") != authority.lineage_hash or envelope.get("validation_fingerprint") != validation.technical_validation_fingerprint or envelope.get("promotion_fingerprint") != authority.promotion_fingerprint or authority.payload_hash != version.payload_hash:
        _fail("MEDIA_OFFICIAL_RESOLUTION_FAILED", "OfficialMediaAuthority envelope or payload hash is tampered.")
    integrity = validate_media_candidate_integrity(session, candidate=candidate)
    if authority.lineage_hash != _lineage_hash(candidate, execution, validation):
        _fail("MEDIA_OFFICIAL_RESOLUTION_FAILED", "OfficialMediaAuthority lineage hash is tampered.")
    if integrity["candidate_fingerprint"] != version.candidate_fingerprint:
        _fail("MEDIA_OFFICIAL_RESOLUTION_FAILED", "Candidate lineage no longer matches OfficialMediaVersion.")
    expected_version_payload_hash = _fingerprint({"version_id": version.official_media_version_id, "candidate_id": candidate.candidate_id, "storage_identity": candidate.storage_identity, "checksum_sha256": candidate.checksum_sha256, "validation_id": validation.validation_id})
    version_fields_match = all(
        getattr(version, field) == expected
        for field, expected in {
            "book_id": book_id,
            "episode": episode,
            "storyboard_shot_id": storyboard_shot_id,
            "media_role": media_role,
            "media_type": candidate.media_type,
            "candidate_id": candidate.candidate_id,
            "candidate_fingerprint": validation.candidate_fingerprint,
            "storage_identity": candidate.storage_identity,
            "checksum_sha256": candidate.checksum_sha256,
            "mime_type": candidate.mime_type,
            "byte_size": candidate.byte_size,
            "width": candidate.width,
            "height": candidate.height,
            "duration_ms": candidate.duration_ms,
            "prompt_ir_version_id": candidate.prompt_ir_version_id,
            "prompt_ir_payload_hash": candidate.prompt_ir_payload_hash,
            "generation_payload_fingerprint": candidate.generation_payload_fingerprint,
            "provider_request_fingerprint": candidate.provider_request_fingerprint,
            "provider_response_hash": candidate.provider_response_hash,
            "validation_id": validation.validation_id,
            "validation_fingerprint": validation.technical_validation_fingerprint,
            "payload_hash": expected_version_payload_hash,
        }.items()
    )
    if not version_fields_match:
        _fail("MEDIA_OFFICIAL_RESOLUTION_FAILED", "OfficialMediaVersion fields no longer match Candidate and Validation.")
    technical = validate_media_candidate_technical(candidate)
    if not technical.get("valid") or technical.get("technical_validation_fingerprint") != version.validation_fingerprint:
        _fail("MEDIA_OFFICIAL_RESOLUTION_FAILED", "Canonical storage bytes no longer match the official record.")
    snapshot = _current_authority_snapshot(session, candidate=candidate, execution=execution)
    if not snapshot.get("currentness_valid") or _fingerprint(snapshot) != validation.authority_snapshot_fingerprint:
        _fail("MEDIA_OFFICIAL_RESOLUTION_FAILED", "Current upstream authority no longer matches the official record.")
    return {"pointer": pointer, "version": version, "authority": authority, "validation": validation, "candidate": candidate, "execution": execution, "technical_validation": technical, "provider_calls": 0, "llm_calls": 0, "image_calls": 0, "video_calls": 0}


def resolve_current_official_media_for_shot(
    session: Any,
    *,
    book_id: int,
    episode: int,
    storyboard_shot_id: int,
    media_role: str = MEDIA_ROLE_DEFAULT,
) -> dict[str, Any]:
    """Resolve OfficialMedia only when the complete Phase I lineage is exact.

    The legacy G2 resolver remains available for rows created before H2.2. This
    strict resolver requires the promotion envelope to carry the storyboard,
    PromptIR, GenerationExecution, storage and explicit H2.2 asset-binding
    snapshot. Every failure is exposed as the API-safe 409 contract requested
    by Phase I.
    """
    try:
        resolved = resolve_current_official_media(
            session,
            book_id=book_id,
            episode=episode,
            storyboard_shot_id=storyboard_shot_id,
            media_role=media_role,
        )
    except MediaAuthorityError as exc:
        _fail("OFFICIAL_MEDIA_BINDING_INVALID", exc.message, {"cause_code": exc.code, "cause_diagnostics": exc.diagnostics})

    from models import PromptIRPointer, PromptIRVersion, StoryboardShot

    shot = session.query(StoryboardShot).filter_by(id=storyboard_shot_id, book_id=book_id, episode=episode).first()
    version = resolved["version"]
    execution = resolved["execution"]
    authority = resolved["authority"]
    candidate = resolved["candidate"]
    envelope = _json(authority.authority_envelope_json, {})
    target_media = str(execution.target_media or "").strip()
    pointer = session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode, storyboard_shot_id=storyboard_shot_id, target_media=target_media).first()
    prompt = session.query(PromptIRVersion).filter_by(id=int(version.prompt_ir_version_id)).first()
    current_assets = _production_asset_binding_snapshot(session, storyboard_shot_id=storyboard_shot_id)
    expected_storyboard_fp = _storyboard_shot_fingerprint(shot) if shot is not None else ""
    expected = {
        "storyboard_shot": bool(shot and int(version.storyboard_shot_id) == int(storyboard_shot_id) and str(version.plan_shot_id or "") == str(getattr(shot, "plan_shot_id", "") or "")),
        "storyboard_fingerprint": bool(envelope.get("storyboard_shot_fingerprint") and envelope.get("storyboard_shot_fingerprint") == expected_storyboard_fp),
        "generation_execution": envelope.get("generation_execution_id") == execution.execution_id,
        "prompt_version": bool(prompt and pointer and int(pointer.prompt_ir_version_id) == int(prompt.id) == int(version.prompt_ir_version_id)),
        "prompt_fingerprint": bool(prompt and envelope.get("prompt_ir_payload_hash") == prompt.payload_hash == version.prompt_ir_payload_hash),
        "prompt_scope": bool(pointer and target_media in {"IMAGE", "VIDEO"} and str(pointer.target_media or "") == target_media and str((_json(prompt.payload_json, {}).get("generation_policy") or {}).get("target_media") or "") == target_media),
        "asset_binding_declared": bool((envelope.get("production_asset_binding") or {}).get("declared")),
        "asset_binding_current": bool(current_assets.get("declared") and current_assets.get("currentness_valid") and envelope.get("production_asset_binding", {}).get("fingerprint") == current_assets.get("fingerprint")),
        "storage_identity": envelope.get("storage_identity") == candidate.storage_identity == version.storage_identity,
        "checksum": envelope.get("checksum_sha256") == candidate.checksum_sha256 == version.checksum_sha256,
    }
    if not all(expected.values()):
        _fail("OFFICIAL_MEDIA_BINDING_INVALID", "OfficialMedia is not bound to the current Storyboard, PromptIR, Production Asset Authority, or storage identity.", {"checks": expected, "asset_binding": current_assets})
    return {
        **resolved,
        "status": "PASS",
        "binding_status": "PASS",
        "checks": expected,
        "production_asset_binding": current_assets,
        "prompt_ir": {"version_id": prompt.id, "payload_hash": prompt.payload_hash, "pointer_id": pointer.id},
        "generation_execution_id": execution.execution_id,
    }
