"""Compiler-neutral bridge from current OfficialMedia truth to FIRST_FRAME refs.

The compiler never reads the database.  This module is the small projection
boundary used after the canonical OfficialMedia resolver has validated the
current pointer, authority, validation, promotion, PromptIR and checksum.
"""
from __future__ import annotations

from typing import Any, Mapping


def _value(item: Any, key: str, default: Any = "") -> Any:
    if isinstance(item, Mapping):
        return item.get(key, default)
    return getattr(item, key, default)


def _text(item: Any, key: str) -> str:
    return str(_value(item, key, "") or "").strip()


def build_official_media_video_reference_bridge(
    *,
    source_binding: Mapping[str, Any],
    official_media_version: Any,
    official_media_authority: Any,
    official_media_pointer: Any,
    validation: Any,
    promotion: Any,
    candidate: Any,
    execution: Any,
) -> dict[str, Any]:
    """Project a validated OfficialMedia source binding for VideoIntentIR.

    This function intentionally refuses partial or fixture-shaped lineage. It
    does not create records and does not resolve a provider URL.
    """
    binding = dict(source_binding or {})
    required_binding = ("official_media_authority_id", "official_media_version_id", "media_role", "checksum_sha256", "source_prompt_ir_version_id", "source_prompt_ir_payload_hash")
    missing = [key for key in required_binding if not _text(binding, key)]
    if binding.get("authority_class") != "OFFICIAL_MEDIA" or missing:
        raise ValueError("OFFICIAL_MEDIA_SOURCE_BINDING_INCOMPLETE")
    version_id = _text(official_media_version, "official_media_version_id")
    authority_id = _text(official_media_authority, "authority_id")
    pointer_version_id = _text(official_media_pointer, "official_media_version_id")
    pointer_authority_id = _text(official_media_pointer, "authority_id")
    if version_id != _text(binding, "official_media_version_id") or authority_id != _text(binding, "official_media_authority_id"):
        raise ValueError("OFFICIAL_MEDIA_SOURCE_BINDING_MISMATCH")
    if pointer_version_id != version_id or pointer_authority_id != authority_id:
        raise ValueError("OFFICIAL_MEDIA_POINTER_MISMATCH")
    if _text(official_media_version, "status") != "CURRENT" or _text(official_media_authority, "status") != "CURRENT":
        raise ValueError("OFFICIAL_MEDIA_NOT_CURRENT")
    checksum = _text(official_media_version, "checksum_sha256")
    if checksum != _text(binding, "checksum_sha256") or checksum != _text(candidate, "checksum_sha256"):
        raise ValueError("OFFICIAL_MEDIA_CHECKSUM_MISMATCH")
    execution_id = _text(candidate, "execution_id")
    if not execution_id or execution_id != _text(execution, "execution_id"):
        raise ValueError("OFFICIAL_MEDIA_EXECUTION_LINEAGE_MISMATCH")
    validation_id = _text(validation, "validation_id")
    promotion_id = _text(promotion, "promotion_id")
    if not validation_id or not promotion_id:
        raise ValueError("OFFICIAL_MEDIA_REVIEW_LINEAGE_INCOMPLETE")
    lineage_hash = _text(official_media_authority, "lineage_hash") or _text(official_media_authority, "payload_hash")
    if not lineage_hash:
        raise ValueError("OFFICIAL_MEDIA_AUTHORITY_FINGERPRINT_MISSING")
    return {
        "role": "FIRST_FRAME",
        "asset_id": version_id,
        "authority_fingerprint": lineage_hash,
        "media_sha256": checksum,
        "generation_execution_id": execution_id,
        "official_lineage": {
            "official_media_version_id": version_id,
            "official_media_authority_id": authority_id,
            "official_media_pointer_fingerprint": _text(official_media_pointer, "fingerprint"),
            "validation_id": validation_id,
            "promotion_id": promotion_id,
            "candidate_id": _text(candidate, "candidate_id"),
            "generation_execution_id": execution_id,
            "source_prompt_ir_version_id": _text(binding, "source_prompt_ir_version_id"),
            "source_prompt_ir_payload_hash": _text(binding, "source_prompt_ir_payload_hash"),
            "media_role": _text(binding, "media_role"),
        },
        "source_binding": binding,
    }


def validate_official_media_video_reference_bridge(bridge: Mapping[str, Any]) -> dict[str, Any]:
    required = ("role", "asset_id", "authority_fingerprint", "media_sha256", "generation_execution_id", "official_lineage")
    missing = [key for key in required if not str(bridge.get(key) or "").strip()]
    lineage = bridge.get("official_lineage") if isinstance(bridge.get("official_lineage"), Mapping) else {}
    if not str(lineage.get("official_media_version_id") or "").strip() or not str(lineage.get("official_media_authority_id") or "").strip():
        missing.append("official_lineage.ids")
    return {"status": "PASS" if not missing and bridge.get("role") == "FIRST_FRAME" else "FAIL", "missing": missing, "asset_id_source": "OfficialMediaVersion.official_media_version_id", "authority_fingerprint_source": "OfficialMediaAuthority.lineage_hash", "generation_execution_id_source": "MediaCandidateRecord.execution_id"}


__all__ = ["build_official_media_video_reference_bridge", "validate_official_media_video_reference_bridge"]
