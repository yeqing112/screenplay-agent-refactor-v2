"""Typed support resolver for claim-aware manifests.

This path never calls the legacy text extractor and never calls the legacy
special-case grounding function.  It compares typed claims and source claim
identifiers only.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from .director_claim_authority import authority_requirement
from .director_claim_entity_binding import validate_claim_entities
from .director_claim_relation_registry import relation_compatible
from .director_authoring_claim_contract import validate_manifest_claim


TYPED_SUPPORT_VERSION = "director_claim_aware_typed_support_v1"
NON_CANONICAL_AUTHORITY_TYPES = {
    "DRAMATIC_GROUPING", "DRAMATIC_OBJECTIVE", "DRAMATIC_QUESTION", "AUDIENCE_INTERPRETATION",
    "PERFORMANCE_DIRECTION", "AUDIENCE_EFFECT", "INFORMATION_STRATEGY", "RHYTHM_INTENT", "VISUAL_PRIORITY",
}


def _same_uncertainty(candidate: Mapping[str, Any], source: Mapping[str, Any]) -> bool:
    if str(candidate.get("claim_type") or "") != "CERTAINTY_ASSERTION" or str(source.get("claim_type") or "") != "UNCERTAINTY":
        return False
    return (candidate.get("subject") or {}) == (source.get("subject") or {}) and (candidate.get("object") or {}) == (source.get("object") or {})


def _source_candidates(claim: Mapping[str, Any], source_claims: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    ids = set(str(value) for value in (claim.get("source_claim_ids") or []))
    if not ids:
        return []
    return [source for source in source_claims if str(source.get("claim_id") or "") in ids]


def resolve_typed_claim_support(claim: Mapping[str, Any], *, source_claims: list[Mapping[str, Any]]) -> dict[str, Any]:
    schema = validate_manifest_claim(claim)
    if schema["status"] != "PASS":
        return {"status": "BLOCKED", "support_status": "INVALID_CLAIM", "reason": "Claim manifest schema failed", "errors": schema["errors"]}
    authority = authority_requirement(claim)
    if authority["status"] == "META_SAFE":
        return {"status": "PASS", "support_status": "META_SAFE", "reason": authority["reason"]}
    if authority["status"] == "NON_CANONICAL_OPTION":
        return {"status": "PASS", "support_status": "SUPPORTED_AS_NON_CANONICAL_OPTION", "reason": authority["reason"]}
    if authority["status"] in {"BLOCKED", "DOWNSTREAM_FORBIDDEN"}:
        return {"status": "BLOCKED", "support_status": "UNSUPPORTED", "reason": authority["reason"]}
    if authority["status"] in {"STAGE_A_AUTHORITY", "STAGE_B_AUTHORITY"} and str(claim.get("claim_type") or "") in NON_CANONICAL_AUTHORITY_TYPES:
        return {"status": "PASS", "support_status": "SUPPORTED_AS_NON_CANONICAL_OPTION", "reason": "Typed field is within the declared dramatic or creative authority and creates no canonical fact"}
    entities = validate_claim_entities(claim)
    if entities["status"] != "PASS":
        return {"status": "BLOCKED", "support_status": "UNSUPPORTED", "reason": "Entity binding failed", "errors": entities["errors"]}
    candidates = _source_candidates(claim, source_claims)
    if not candidates:
        return {"status": "BLOCKED", "support_status": "UNSUPPORTED", "reason": "Canonical claim has no bound SourceClaim IDs"}
    for source in candidates:
        if _same_uncertainty(claim, source):
            return {"status": "BLOCKED", "support_status": "UNSUPPORTED", "reason": "CERTAINTY_ASSERTION conflicts with typed UNCERTAINTY source claim"}
        if relation_compatible(claim, source):
            return {"status": "PASS", "support_status": "SUPPORTED_EXPLICIT", "reason": "Typed claim matches bound SourceClaim through the versioned relation registry"}
    return {"status": "BLOCKED", "support_status": "UNSUPPORTED", "reason": "Bound SourceClaim IDs do not match typed subject, predicate, object or qualifiers"}


def audit_typed_manifest(manifest: Mapping[str, Any], *, source_claims: list[Mapping[str, Any]]) -> dict[str, Any]:
    schema_errors = validate_manifest_claim(manifest) if False else []
    findings: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for claim in manifest.get("claims") or []:
        result = resolve_typed_claim_support(claim, source_claims=source_claims)
        status = result["support_status"]
        counts[status] = counts.get(status, 0) + 1
        findings.append({"claim_id": claim.get("claim_id"), "claim_type": claim.get("claim_type"), "support_status": status, "status": result["status"], "reason": result["reason"]})
    blocked = [item for item in findings if item["status"] != "PASS"]
    return {"schema_version": TYPED_SUPPORT_VERSION, "status": "BLOCKED" if blocked else "PASS", "claim_count": len(findings), "counts": counts, "blocking_finding_count": len(blocked), "findings": findings, "raw_text_consulted": False, "legacy_special_case_called": False}


__all__ = ["TYPED_SUPPORT_VERSION", "resolve_typed_claim_support", "audit_typed_manifest"]
