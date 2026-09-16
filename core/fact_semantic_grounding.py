"""Provider-free semantic grounding guards for Fact Evidence Authority V2.

Evidence identity (``evidence_refs`` resolving to immutable anchors) and
semantic entailment are deliberately separate contracts.  This module only
implements deterministic ceilings and hard guards; it never claims to solve
arbitrary natural-language entailment.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any

SCHEMA_VERSION = "fact_semantic_grounding_v1"
SURFACE_ENUM = ("NARRATIVE_PROSE", "QUOTED_TEXT", "UNKNOWN_SURFACE")
SUPPORT_ROLES = (
    "WORLD_ASSERTION",
    "ACTION_OCCURRENCE",
    "SPEECH_ACT",
    "CLAIM_CONTENT",
    "TEXT_CONTENT",
    "CORROBORATION",
    "CONTEXT_ONLY",
)
SUPPORT_CLASSES = (
    "DIRECTLY_ENTAILED",
    "PARTIALLY_ENTAILED",
    "CLAIM_ONLY",
    "INFERENCE_ONLY",
    "CONTRADICTED",
    "AMBIGUOUS",
)
GROUNDING_STATES = (
    "EVIDENCE_VALIDATED",
    "MACHINE_GUARDS_PASS",
    "SEMANTIC_REVIEW_REQUIRED",
    "SEMANTICALLY_CONFIRMED",
    "SEMANTICALLY_REJECTED",
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def classify_anchor_surface(text: Any) -> str:
    """Classify only the presentation surface, conservatively.

    Quotation marks and a leading em-dash indicate quoted presentation, not
    dialogue truth. Empty/non-string values remain unknown. Everything else
    is narrative prose; no semantic claim is made by this function.
    """
    if not isinstance(text, str) or not text.strip():
        return "UNKNOWN_SURFACE"
    value = text.strip()
    if any(mark in value for mark in ("“", "”", "‘", "’")) or re.match(r"^—{1,2}\s*", value):
        return "QUOTED_TEXT"
    return "NARRATIVE_PROSE"


def annotate_source_evidence_index(index: dict[str, Any]) -> dict[str, Any]:
    """Return an index copy with deterministic surface classifications."""
    result = copy.deepcopy(index if isinstance(index, dict) else {})
    anchors = result.get("anchors") if isinstance(result.get("anchors"), list) else []
    for anchor in anchors:
        if isinstance(anchor, dict):
            anchor["anchor_surface_class"] = classify_anchor_surface(anchor.get("exact_text"))
    projection = [
        {"anchor_ref": a.get("anchor_ref"), "surface": a.get("anchor_surface_class")}
        for a in anchors
        if isinstance(a, dict)
    ]
    result["surface_schema_version"] = "source_anchor_surface_v1"
    result["surface_typing_deterministic"] = True
    result["surface_index_fingerprint"] = _sha({
        "evidence_index_fingerprint": result.get("evidence_index_fingerprint"),
        "anchors": projection,
    })
    return result


def semantic_contract() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "evidence_authority_independent": True,
        "surface_enum": list(SURFACE_ENUM),
        "support_roles": list(SUPPORT_ROLES),
        "support_classes": list(SUPPORT_CLASSES),
        "grounding_states": list(GROUNDING_STATES),
        "provider_calls": 0,
        "runtime_authority": False,
        "machine_capability": "hard_guards_only; arbitrary_natural_language_entailment_requires_review",
    }


def confirmation_ceiling(surface: str, role: str) -> dict[str, Any]:
    """Return the maximum deterministic authority for a surface/role pair."""
    surface = surface if surface in SURFACE_ENUM else "UNKNOWN_SURFACE"
    role = role if role in SUPPORT_ROLES else "WORLD_ASSERTION"
    if surface == "UNKNOWN_SURFACE":
        return {"allowed": False, "ceiling": "REVIEW_REQUIRED", "reason": "unknown_surface_cannot_auto_confirm"}
    if surface == "QUOTED_TEXT":
        if role in {"SPEECH_ACT", "CLAIM_CONTENT", "TEXT_CONTENT"}:
            return {"allowed": True, "ceiling": role, "reason": "quoted_text_supports_claim_or_speech_surface"}
        return {"allowed": False, "ceiling": "CLAIM_ONLY", "reason": "quoted_text_cannot_confirm_world_state_or_actor_causation_alone"}
    return {"allowed": role in SUPPORT_ROLES, "ceiling": "CANDIDATE_WORLD_EVIDENCE", "reason": "narrative_prose_still_requires_semantic_entailment"}


def infer_support_role(fact: dict[str, Any]) -> str:
    """Map a fact to a conservative support role from declared fields only."""
    epistemic = str(fact.get("epistemic_class") or "")
    predicate = str(fact.get("predicate") or "").lower()
    if epistemic == "SOURCE_SPEECH_ACT" or any(token in predicate for token in ("said", "stated", "claims", "recognized")):
        return "CLAIM_CONTENT"
    if any(token in predicate for token in ("found", "is moving", "escaped", "hid", "installed", "installed", "occurred")):
        return "ACTION_OCCURRENCE"
    return "WORLD_ASSERTION"


def is_composite_fact(fact: dict[str, Any]) -> bool:
    """Conservative composite detector; unknown atomicity requires review."""
    assertion = fact.get("assertion")
    if isinstance(assertion, dict) and assertion.get("atomic") is False:
        return True
    value = fact.get("value")
    predicate = str(fact.get("predicate") or "")
    if isinstance(value, (list, tuple, dict)):
        return True
    # Do not pretend conjunction parsing is complete; these markers only
    # identify a review candidate, never a rejection by themselves.
    return bool(re.search(r"\b(and|or|以及|并且|同时|之后|以前|six years)\b", predicate + " " + str(value)))


def evaluate_semantic_grounding_guards(
    fact: dict[str, Any],
    evidence: list[dict[str, Any]],
    *,
    provider_epistemic_class: str | None = None,
) -> dict[str, Any]:
    """Evaluate deterministic ceilings without asserting arbitrary entailment."""
    rows = evidence if isinstance(evidence, list) else []
    surfaces = [str(row.get("anchor_surface_class") or classify_anchor_surface(row.get("excerpt"))) for row in rows if isinstance(row, dict)]
    role = infer_support_role({**fact, "epistemic_class": provider_epistemic_class or fact.get("epistemic_class")})
    reasons: list[str] = []
    hard_blockers: list[str] = []
    if not surfaces:
        hard_blockers.append("MISSING_SUPPORT")
    if any(surface not in SURFACE_ENUM for surface in surfaces):
        hard_blockers.append("UNKNOWN_SURFACE")
    if "UNKNOWN_SURFACE" in surfaces:
        hard_blockers.append("UNKNOWN_SURFACE_CONFIRMATION_BLOCKED")
    if surfaces and all(surface == "QUOTED_TEXT" for surface in surfaces) and role not in {"SPEECH_ACT", "CLAIM_CONTENT", "TEXT_CONTENT"}:
        hard_blockers.append("QUOTED_TEXT_WORLD_FACT_CONFIRMATION_BLOCKED")
    if provider_epistemic_class == "MODEL_INFERENCE":
        hard_blockers.append("PROVIDER_EPISTEMIC_OVERREACH")
    if is_composite_fact(fact):
        hard_blockers.append("COMPOSITE_ATOMICITY_REVIEW_REQUIRED")
    ceilings = [confirmation_ceiling(surface, role) for surface in surfaces]
    reasons.extend(item["reason"] for item in ceilings)
    if hard_blockers:
        state = "SEMANTIC_REVIEW_REQUIRED"
        outcome = "HUMAN_OR_SEMANTIC_VERIFIER_REQUIRED"
    else:
        state = "SEMANTIC_REVIEW_REQUIRED"
        outcome = "HUMAN_OR_SEMANTIC_VERIFIER_REQUIRED"
        reasons.append("deterministic_guards_do_not_prove_arbitrary_natural_language_entailment")
    return {
        "state": state,
        "outcome": outcome,
        "runtime_authority": False,
        "support_role": role,
        "surfaces": surfaces,
        "confirmation_ceilings": ceilings,
        "hard_blockers": sorted(set(hard_blockers)),
        "reasons": sorted(set(reasons)),
        "composite_fact": is_composite_fact(fact),
    }


def script_ir_semantic_gate(*, fact_snapshot: dict[str, Any], semantic_grounding_status: str) -> dict[str, Any]:
    """Fail closed unless evidence and semantic grounding are both confirmed."""
    evidence_status = str((fact_snapshot or {}).get("validation", {}).get("status") or "")
    allowed = evidence_status in {"qualified", "PASS"} and semantic_grounding_status == "SEMANTICALLY_CONFIRMED"
    return {
        "allowed": allowed,
        "status": "PASS" if allowed else "BLOCKED_PENDING_SEMANTIC_GROUNDING",
        "evidence_authority_status": "PASS" if evidence_status in {"qualified", "PASS"} else evidence_status or "UNKNOWN",
        "semantic_grounding_status": semantic_grounding_status,
        "reason": "both evidence authority and semantic confirmation are required" if not allowed else "semantic prerequisites satisfied",
    }


__all__ = [
    "SCHEMA_VERSION",
    "SURFACE_ENUM",
    "SUPPORT_ROLES",
    "SUPPORT_CLASSES",
    "GROUNDING_STATES",
    "classify_anchor_surface",
    "annotate_source_evidence_index",
    "semantic_contract",
    "confirmation_ceiling",
    "infer_support_role",
    "is_composite_fact",
    "evaluate_semantic_grounding_guards",
    "script_ir_semantic_gate",
]
