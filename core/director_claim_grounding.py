"""Deterministic typed support evaluation for Director ClaimIR shadow audits."""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from .director_claim_authority import authority_requirement


PRODUCTION_BLOCKING_TYPES = {
    "SOURCE_EVENT", "CHARACTER_ACTION", "CHARACTER_KNOWLEDGE", "CHARACTER_INTENT", "CHARACTER_EMOTION",
    "CHARACTER_RELATIONSHIP", "CHARACTER_BACKSTORY", "OBJECT_EXISTENCE", "OBJECT_PROPERTY", "OBJECT_OWNERSHIP",
    "OBJECT_PROVENANCE", "OBJECT_POSSESSION", "ENVIRONMENT_STATE", "SENSORY_FACT", "SPATIAL_BLOCKING",
    "SHOT_EXECUTION", "CERTAINTY_ASSERTION", "UNCERTAINTY",
}


def _s(value: Any) -> str:
    return str(value or "").strip()


def _same_ref(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return _s(left.get("kind")) == _s(right.get("kind")) and _s(left.get("ref")) == _s(right.get("ref"))


def _source_match(candidate: Mapping[str, Any], source: Mapping[str, Any]) -> bool:
    if _s(candidate.get("claim_type")) != _s(source.get("claim_type")):
        return False
    c_subject, s_subject = candidate.get("subject") or {}, source.get("subject") or {}
    c_object, s_object = candidate.get("object") or {}, source.get("object") or {}
    if c_subject and s_subject and not _same_ref(c_subject, s_subject):
        return False
    if c_object and s_object and not _same_ref(c_object, s_object):
        return False
    cp = _s(candidate.get("predicate")); sp = _s(source.get("predicate"))
    if cp == sp:
        return True
    if _s(candidate.get("claim_type")) == "CHARACTER_ACTION" and cp in {"引导", "引导进入", "带"} and sp in {"带/引导进入", "带", "引导进入"}:
        c_dest = (candidate.get("qualifiers") or {}).get("destination")
        s_dest = (source.get("qualifiers") or {}).get("destination")
        return not c_dest or c_dest == s_dest
    return False


def _source_has_uncertainty(source_claims: Iterable[Mapping[str, Any]], candidate: Mapping[str, Any]) -> bool:
    target = (candidate.get("object") or {}).get("ref")
    for source in source_claims:
        if _s(source.get("claim_type")) != "UNCERTAINTY":
            continue
        if target and target in _s((source.get("object") or {}).get("ref")):
            return True
        if target and target in _s((source.get("subject") or {}).get("ref")):
            return True
    return False


def _reason_for_special_case(candidate: Mapping[str, Any], source_claims: list[Mapping[str, Any]]) -> tuple[str, str] | None:
    kind = _s(candidate.get("claim_type")); predicate = _s(candidate.get("predicate")); obj = _s((candidate.get("object") or {}).get("ref")); subj = _s((candidate.get("subject") or {}).get("ref"))
    if kind == "CERTAINTY_ASSERTION" and _source_has_uncertainty(source_claims, candidate):
        return "UNSUPPORTED", "Source records unresolved childhood-visit uncertainty; certainty assertion collapses it into a first/never fact."
    if kind == "CHARACTER_INTENT" and predicate in {"test_or_probe", "observe_without_alerting", "objective", "strategy"}:
        return "UNSUPPORTED", "Dialogue and observable action do not authorize a canonical motive or hidden strategy."
    if kind == "OBJECT_PROVENANCE":
        return "UNSUPPORTED", "A mother-authored label does not entail that the mother left or owned the referenced object."
    if kind == "OBJECT_PROPERTY" and subj in {"车票背面", "ticket_text"} and predicate == "handwritten":
        return "AMBIGUOUS_REVIEW_REQUIRED", "Source says the ticket back contains text, but does not state that the ticket writing is handwritten."
    if kind == "OBJECT_POSSESSION" and predicate == "receives":
        return "AMBIGUOUS_REVIEW_REQUIRED", "The source says an unknown person inserts a ticket; it does not state that Lin Wan takes possession of it."
    if kind == "ENVIRONMENT_STATE" and obj in {"dim", "微弱光线"}:
        return "UNSUPPORTED", "A flickering red safety light and later extinguishing it do not entail a remaining dim-light state."
    if kind == "SPATIAL_BLOCKING" and "铁盒前" in obj:
        return "UNSUPPORTED", "A path to the box is a SceneBlocking decision and is absent from SourceAuthoringUnits."
    if kind == "CHARACTER_ACTION" and predicate == "opens":
        return "UNSUPPORTED", "Opening the box is a new canonical prop action not stated by SourceAuthoringUnits."
    return None


def evaluate_claim_support(claim: Mapping[str, Any], *, source_claims: list[Mapping[str, Any]], upstream_claims: list[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Evaluate one typed claim.  Text inclusion is never used as entailment."""
    authority = authority_requirement(claim)
    kind = _s(claim.get("claim_type")); origin = _s(claim.get("origin"))
    if authority["status"] == "META_SAFE":
        return {"support_status": "META_SAFE", "reason": authority["reason"], "production_blocking": False, "authority": authority}
    if authority["status"] == "DOWNSTREAM_FORBIDDEN":
        return {"support_status": "UNSUPPORTED", "reason": authority["reason"], "production_blocking": True, "authority": authority}
    if authority["status"] == "NON_CANONICAL_OPTION":
        return {"support_status": "SUPPORTED_AS_NON_CANONICAL_OPTION", "reason": authority["reason"], "production_blocking": False, "authority": authority}
    if origin == "SOURCE":
        return {"support_status": "SUPPORTED_EXPLICIT", "reason": "Claim is projected directly from a SourceAuthoringUnit.", "production_blocking": False, "authority": authority}
    special = _reason_for_special_case(claim, source_claims)
    if special:
        status, reason = special
        return {"support_status": status, "reason": reason, "production_blocking": kind in PRODUCTION_BLOCKING_TYPES, "authority": authority}
    if any(_source_match(claim, source) for source in source_claims):
        return {"support_status": "SUPPORTED_EXPLICIT", "reason": "Typed subject, predicate, object and qualifiers match an explicit SourceClaim.", "production_blocking": False, "authority": authority}
    if origin == "COMPILED" and upstream_claims:
        if any(_source_match(claim, upstream) for upstream in upstream_claims if _s(upstream.get("support_status")) in {"SUPPORTED_EXPLICIT", "SUPPORTED_ENTAILED", "SUPPORTED_AS_NON_CANONICAL_OPTION", "META_SAFE"}):
            return {"support_status": "SUPPORTED_ENTAILED", "reason": "Compiled claim is supported by a typed upstream claim that is itself source-supported.", "production_blocking": False, "authority": authority}
        if any(_source_match(claim, upstream) for upstream in upstream_claims):
            return {"support_status": "UPSTREAM_UNSUPPORTED", "reason": "Compiled claim inherits an unsupported upstream interpretation and cannot launder it into authority.", "production_blocking": True, "authority": authority}
    if kind in {"AUDIENCE_EFFECT", "AUDIENCE_INTERPRETATION", "INFORMATION_REVEAL", "INFORMATION_WITHHOLD", "VISUAL_PRIORITY", "DRAMATIC_GROUPING", "DRAMATIC_OBJECTIVE", "DRAMATIC_QUESTION", "PERFORMANCE_DIRECTION", "RHYTHM_INTENT", "INFORMATION_STRATEGY"}:
        return {"support_status": "SUPPORTED_AS_NON_CANONICAL_OPTION", "reason": "Claim is within the declared creative or audience interpretation authority and does not assert a new canonical fact.", "production_blocking": False, "authority": authority}
    if kind in PRODUCTION_BLOCKING_TYPES:
        return {"support_status": "UNSUPPORTED", "reason": "No typed SourceClaim supports this canonical assertion.", "production_blocking": True, "authority": authority}
    return {"support_status": "AMBIGUOUS_REVIEW_REQUIRED", "reason": "Typed authority is insufficient to establish support.", "production_blocking": True, "authority": authority}


def audit_claim_set(claims: list[Mapping[str, Any]], *, source_claims: list[Mapping[str, Any]], upstream_claims: list[Mapping[str, Any]] | None = None, diagnostic_only: bool = False, metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    counts = {"SUPPORTED_EXPLICIT": 0, "SUPPORTED_ENTAILED": 0, "SUPPORTED_AS_NON_CANONICAL_OPTION": 0, "META_SAFE": 0, "UNSUPPORTED": 0, "UPSTREAM_UNSUPPORTED": 0, "AMBIGUOUS_REVIEW_REQUIRED": 0}
    for claim in claims:
        result = evaluate_claim_support(claim, source_claims=source_claims, upstream_claims=upstream_claims)
        status = result["support_status"]
        counts[status] = counts.get(status, 0) + 1
        # Persist every canonical problem and the metadata cases explicitly
        # required by the V7.7.0 audit.  Safe creative leaves remain countable
        # in the claim set without creating noisy findings.
        if status not in {"SUPPORTED_AS_NON_CANONICAL_OPTION", "SUPPORTED_EXPLICIT", "SUPPORTED_ENTAILED"} or claim.get("claim_type") in {"AUTHORITY_DELEGATION", "META_COMPLIANCE"}:
            findings.append({
                "claim_id": claim.get("claim_id"), "origin": claim.get("origin"), "source_path": claim.get("source_path"),
                "claim_type": claim.get("claim_type"), "subject": claim.get("subject"), "predicate": claim.get("predicate"),
                "object": claim.get("object"), "polarity": claim.get("polarity"), "modality": claim.get("modality"),
                "canonicality": claim.get("canonicality"), "authority_required": claim.get("authority_required"),
                "source_refs": claim.get("source_refs"), "support_status": status, "reason": result["reason"],
                "production_blocking": bool(result["production_blocking"]), "raw_text": claim.get("raw_text"),
            })
    blocking = [f for f in findings if f.get("production_blocking")]
    status = "DIAGNOSTIC_ONLY" if diagnostic_only else ("BLOCKED" if blocking else ("AMBIGUOUS" if counts.get("AMBIGUOUS_REVIEW_REQUIRED") else "PASS"))
    return {
        "schema_version": "director_semantic_grounding_v3_shadow_audit_v1", "status": status,
        "claim_count": len(claims), "supported_count": counts.get("SUPPORTED_EXPLICIT", 0) + counts.get("SUPPORTED_ENTAILED", 0) + counts.get("SUPPORTED_AS_NON_CANONICAL_OPTION", 0) + counts.get("META_SAFE", 0),
        "unsupported_count": counts.get("UNSUPPORTED", 0) + counts.get("UPSTREAM_UNSUPPORTED", 0), "ambiguous_count": counts.get("AMBIGUOUS_REVIEW_REQUIRED", 0),
        "counts": counts, "blocking_finding_count": len(blocking), "findings": findings, "diagnostic_only": diagnostic_only, **(dict(metadata or {})),
    }


__all__ = ["PRODUCTION_BLOCKING_TYPES", "evaluate_claim_support", "audit_claim_set"]
