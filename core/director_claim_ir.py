"""Typed, deterministic Director ClaimIR contracts for semantic shadow audits.

This module is intentionally independent from the V2 lexical semantic gate.  A
claim carries its semantic type, authority, polarity, modality and provenance;
support is resolved by :mod:`core.director_claim_grounding` rather than by
substring matching.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


CLAIM_IR_VERSION = "director_claim_ir_v1"
CLAIM_SET_VERSION = "director_source_claim_set_v1"
SHADOW_AUDIT_VERSION = "director_semantic_grounding_v3_shadow_audit_v1"

CLAIM_TYPES = (
    "SOURCE_EVENT", "CHARACTER_ACTION", "CHARACTER_KNOWLEDGE", "CHARACTER_INTENT",
    "CHARACTER_EMOTION", "CHARACTER_RELATIONSHIP", "CHARACTER_BACKSTORY",
    "OBJECT_EXISTENCE", "OBJECT_PROPERTY", "OBJECT_OWNERSHIP", "OBJECT_PROVENANCE",
    "OBJECT_POSSESSION", "ENVIRONMENT_STATE", "SENSORY_FACT", "SPATIAL_BLOCKING",
    "SHOT_EXECUTION", "PERFORMANCE_DIRECTION", "PERFORMANCE_OPTION", "AUDIENCE_EFFECT",
    "AUDIENCE_INTERPRETATION", "INFORMATION_REVEAL", "INFORMATION_WITHHOLD",
    "UNCERTAINTY", "CERTAINTY_ASSERTION", "AUTHORITY_DELEGATION", "META_COMPLIANCE",
    "PROHIBITION", "DRAMATIC_GROUPING", "DRAMATIC_OBJECTIVE", "DRAMATIC_QUESTION",
    "VISUAL_PRIORITY", "INFORMATION_STRATEGY", "RHYTHM_INTENT", "CHARACTER_STATE",
)
POLARITIES = ("POSITIVE", "NEGATED", "PROHIBITION", "META_COMPLIANCE", "DELEGATION")
MODALITIES = ("ASSERTED", "UNCERTAIN", "POSSIBLE", "HYPOTHETICAL", "PLAYABLE_OPTION", "DELEGATED", "PROHIBITED")
CANONICALITIES = ("CANONICAL_ASSERTION", "NON_CANONICAL_PERFORMANCE_OPTION", "META", "AUDIENCE_INTERPRETATION")
AUTHORITIES = ("SOURCE", "STAGE_A", "STAGE_B", "NONE")
SUPPORT_STATUSES = (
    "UNRESOLVED", "SUPPORTED_EXPLICIT", "SUPPORTED_ENTAILED", "SUPPORTED_AS_NON_CANONICAL_OPTION",
    "META_SAFE", "UNSUPPORTED", "UPSTREAM_UNSUPPORTED", "AMBIGUOUS_REVIEW_REQUIRED",
)
ORIGINS = ("SOURCE", "STAGE_A", "STAGE_B", "COMPILED")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _canonical_claim_payload(claim: Mapping[str, Any]) -> dict[str, Any]:
    """Return fingerprint material without path, timestamp or filesystem data."""
    return {
        "schema_version": claim.get("schema_version", CLAIM_IR_VERSION),
        "claim_type": claim.get("claim_type"),
        "subject": claim.get("subject") or {},
        "predicate": claim.get("predicate"),
        "object": claim.get("object") or {},
        "qualifiers": claim.get("qualifiers") or {},
        "polarity": claim.get("polarity"),
        "modality": claim.get("modality"),
        "canonicality": claim.get("canonicality"),
        "authority_required": claim.get("authority_required"),
        "source_refs": sorted(str(x) for x in (claim.get("source_refs") or [])),
        "upstream_claim_refs": sorted(str(x) for x in (claim.get("upstream_claim_refs") or [])),
        "origin": claim.get("origin"),
    }


def claim_fingerprint(claim: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(_canonical_claim_payload(claim)).encode("utf-8")).hexdigest()


def claim_set_fingerprint(claims: list[Mapping[str, Any]], *, version: str = CLAIM_SET_VERSION) -> str:
    payload = {"schema_version": version, "claims": sorted((dict(c) for c in claims), key=lambda x: str(x.get("claim_id", "")))}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def make_claim(
    *, claim_id: str, source_path: str, raw_text: str, claim_type: str,
    subject: Mapping[str, Any] | None = None, predicate: str = "", object_: Mapping[str, Any] | None = None,
    qualifiers: Mapping[str, Any] | None = None, polarity: str = "POSITIVE", modality: str = "ASSERTED",
    canonicality: str = "CANONICAL_ASSERTION", authority_required: str = "SOURCE",
    source_refs: list[str] | None = None, upstream_claim_refs: list[str] | None = None,
    origin: str = "STAGE_B", support_status: str = "UNRESOLVED", metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    claim = {
        "schema_version": CLAIM_IR_VERSION,
        "claim_id": _clean(claim_id),
        "source_path": _clean(source_path),
        "raw_text": _clean(raw_text),
        "claim_type": _clean(claim_type),
        "subject": dict(subject or {}),
        "predicate": _clean(predicate),
        "object": dict(object_ or {}),
        "qualifiers": dict(qualifiers or {}),
        "polarity": _clean(polarity),
        "modality": _clean(modality),
        "canonicality": _clean(canonicality),
        "authority_required": _clean(authority_required),
        "source_refs": sorted(set(str(x) for x in (source_refs or []) if str(x))),
        "upstream_claim_refs": sorted(set(str(x) for x in (upstream_claim_refs or []) if str(x))),
        "origin": _clean(origin),
        "support_status": _clean(support_status),
    }
    if metadata:
        claim["metadata"] = dict(metadata)
    claim["fingerprint"] = claim_fingerprint(claim)
    return claim


def validate_claim(claim: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    required = ("claim_id", "source_path", "raw_text", "claim_type", "subject", "predicate", "object", "qualifiers", "polarity", "modality", "canonicality", "authority_required", "source_refs", "upstream_claim_refs", "origin", "support_status", "fingerprint")
    for field in required:
        if field not in claim:
            errors.append(f"MISSING_{field}")
    if claim.get("schema_version") != CLAIM_IR_VERSION:
        errors.append("SCHEMA_VERSION_INVALID")
    for field, allowed in (("claim_type", CLAIM_TYPES), ("polarity", POLARITIES), ("modality", MODALITIES), ("canonicality", CANONICALITIES), ("authority_required", AUTHORITIES), ("origin", ORIGINS), ("support_status", SUPPORT_STATUSES)):
        if field in claim and claim.get(field) not in allowed:
            errors.append(f"{field.upper()}_INVALID")
    if claim.get("fingerprint") and claim.get("fingerprint") != claim_fingerprint(claim):
        errors.append("FINGERPRINT_MISMATCH")
    for field in ("subject", "object", "qualifiers"):
        if field in claim and not isinstance(claim[field], Mapping):
            errors.append(f"{field.upper()}_MUST_BE_OBJECT")
    for field in ("source_refs", "upstream_claim_refs"):
        if field in claim and not isinstance(claim[field], list):
            errors.append(f"{field.upper()}_MUST_BE_ARRAY")
    return {"status": "PASS" if not errors else "BLOCKED", "errors": errors}


def validate_claim_set(claims: list[Mapping[str, Any]], *, version: str = CLAIM_SET_VERSION) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, claim in enumerate(claims):
        report = validate_claim(claim)
        if report["status"] != "PASS":
            errors.append({"index": index, "errors": report["errors"]})
        claim_id = str(claim.get("claim_id") or "")
        if claim_id in ids:
            errors.append({"index": index, "errors": ["DUPLICATE_CLAIM_ID"]})
        ids.add(claim_id)
    return {"status": "PASS" if not errors else "BLOCKED", "errors": errors, "claim_count": len(claims), "fingerprint": claim_set_fingerprint(claims, version=version)}


def contract() -> dict[str, Any]:
    return {
        "schema_version": CLAIM_IR_VERSION,
        "fingerprint_excludes": ["claim_id", "source_path", "raw_text", "metadata", "timestamp", "filesystem_path"],
        "fields": {
            "claim_id": "string", "source_path": "string", "raw_text": "string", "claim_type": "enum",
            "subject": "object", "predicate": "string", "object": "object", "qualifiers": "object",
            "polarity": "enum", "modality": "enum", "canonicality": "enum", "authority_required": "enum",
            "source_refs": "array[string]", "upstream_claim_refs": "array[string]", "origin": "enum",
            "support_status": "enum", "fingerprint": "sha256",
        },
        "enums": {"claim_type": list(CLAIM_TYPES), "polarity": list(POLARITIES), "modality": list(MODALITIES), "canonicality": list(CANONICALITIES), "authority_required": list(AUTHORITIES), "origin": list(ORIGINS), "support_status": list(SUPPORT_STATUSES)},
    }


def shadow_audit_schema() -> dict[str, Any]:
    return {
        "schema_version": SHADOW_AUDIT_VERSION,
        "status": ["PASS", "BLOCKED", "AMBIGUOUS", "DIAGNOSTIC_ONLY"],
        "finding_fields": ["claim_id", "origin", "source_path", "claim_type", "subject", "predicate", "object", "polarity", "modality", "canonicality", "authority_required", "source_refs", "support_status", "reason", "production_blocking"],
    }


__all__ = ["CLAIM_IR_VERSION", "CLAIM_SET_VERSION", "SHADOW_AUDIT_VERSION", "CLAIM_TYPES", "POLARITIES", "MODALITIES", "CANONICALITIES", "AUTHORITIES", "SUPPORT_STATUSES", "ORIGINS", "canonical_json", "claim_fingerprint", "claim_set_fingerprint", "make_claim", "validate_claim", "validate_claim_set", "contract", "shadow_audit_schema"]
