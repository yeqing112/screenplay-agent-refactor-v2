"""Append-only Stage B semantic revision contracts.

This module contains only deterministic state and identity helpers.  It does
not call a Provider and it never mutates a database row by itself.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping

from core.director_progressive_authoring import is_progressive_stage_validated


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def semantic_review_fingerprint(review: Mapping[str, Any] | None) -> str:
    """Fingerprint the complete deterministic review envelope."""
    return hashlib.sha256(_canonical(dict(review or {})).encode("utf-8")).hexdigest()


def proposal_fingerprint(proposal: Mapping[str, Any] | None) -> str:
    return hashlib.sha256(_canonical(dict(proposal or {})).encode("utf-8")).hexdigest()


def stage_b_revision_feedback(review: Mapping[str, Any] | None) -> dict[str, Any]:
    """Project semantic rejection into compact constraints, never repair text."""
    review = review if isinstance(review, Mapping) else {}
    items: list[dict[str, Any]] = []
    grounding = review.get("source_grounding") if isinstance(review.get("source_grounding"), Mapping) else {}
    for finding in grounding.get("findings", []) if isinstance(grounding.get("findings"), list) else []:
        if not isinstance(finding, Mapping) or finding.get("classification") in {"SAFE_CREATIVE_DIRECTION", "SOURCE_EXPLICIT"}:
            continue
        items.append({"category": str(finding.get("classification") or ""), "path": str(finding.get("path") or ""), "matched_term": str(finding.get("matched_term") or ""), "constraint": _constraint_for(str(finding.get("classification") or ""), str(finding.get("matched_term") or ""))})
    leakage = review.get("downstream_leakage") if isinstance(review.get("downstream_leakage"), Mapping) else {}
    for violation in leakage.get("violations", []) if isinstance(leakage.get("violations"), list) else []:
        if not isinstance(violation, Mapping):
            continue
        items.append({"category": "DOWNSTREAM_SCENEBLOCKING_LEAKAGE" if violation.get("category") == "SCENEBLOCKING" else "DOWNSTREAM_SHOTPLAN_LEAKAGE", "path": str(violation.get("path") or ""), "matched_term": str(violation.get("matched_term") or ""), "constraint": "Do not specify concrete shot, camera, frame, keyframe, or scene blocking execution."})
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        key = (item["category"], item["path"], item["matched_term"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return {"schema_version": "director_revision_feedback_v1", "semantic_review_fingerprint": semantic_review_fingerprint(review), "constraints": unique, "constraint_count": len(unique), "is_repair_instruction": False, "fresh_generation_required": True}


def _constraint_for(category: str, matched: str) -> str:
    if category == "UNSUPPORTED_FACT_ASSERTION":
        return f"Do not invent source fact: {matched or 'unsupported fact'}."
    if category == "UNSUPPORTED_CHARACTER_KNOWLEDGE":
        return f"Do not assert unsupported character knowledge or prior experience: {matched or 'unsupported knowledge'}."
    if category == "UNSUPPORTED_BACKSTORY":
        return f"Do not add unsupported backstory or hidden relationship: {matched or 'unsupported backstory'}."
    if category == "UNSUPPORTED_EMOTIONAL_FACT":
        return f"Do not canonize unsupported emotion; phrase it as playable performance tension: {matched or 'unsupported emotion'}."
    return "Use only source-grounded creative direction."


def evaluate_stage_b_semantic_revision_eligibility(
    info: Mapping[str, Any] | None,
    proposal: Mapping[str, Any] | None,
    *,
    packet_status: str = "draft",
) -> dict[str, Any]:
    info = info if isinstance(info, Mapping) else {}
    proposal = proposal if isinstance(proposal, Mapping) else {}
    progressive = info.get("progressive_director_authoring") if isinstance(info.get("progressive_director_authoring"), Mapping) else {}
    stage_a = progressive.get("stage_a") if isinstance(progressive, Mapping) else None
    stage_b = progressive.get("stage_b") if isinstance(progressive, Mapping) else None
    projection = proposal.get("creative_projection") if isinstance(proposal.get("creative_projection"), Mapping) else {}
    review = stage_b.get("semantic_review") if isinstance(stage_b, Mapping) and isinstance(stage_b.get("semantic_review"), Mapping) else info.get("semantic_review")
    checks = {
        "stage_a_validated": is_progressive_stage_validated(stage_a, authoring_stage="BEAT_PLAN"),
        "stage_b_structurally_validated": is_progressive_stage_validated(stage_b, authoring_stage="CREATIVE_ENRICHMENT"),
        "semantic_review_blocked": isinstance(review, Mapping) and str(review.get("status") or "").upper() == "BLOCKED",
        "merge_state_merged": isinstance(stage_b, Mapping) and str(stage_b.get("merge_state") or "") == "MERGED",
        "proposal_ready_for_review": proposal.get("decision") == "ready_for_review" and projection.get("status") == "PROPOSED",
        "production_not_confirmed": str(packet_status or "").lower() not in {"confirmed", "superseded"},
        "llm_draft_not_in_progress": not bool(info.get("llm_draft_in_progress")),
    }
    return {"status": "PASS" if all(checks.values()) else "BLOCKED", "eligible": all(checks.values()), "checks": checks, "stage_b_attempt_id": str(stage_b.get("attempt_id") or "") if isinstance(stage_b, Mapping) else "", "stage_b_ir_fingerprint": str(stage_b.get("ir_fingerprint") or stage_b.get("fingerprint") or "") if isinstance(stage_b, Mapping) else "", "semantic_review": copy.deepcopy(dict(review)) if isinstance(review, Mapping) else {}}


def is_stage_b_semantic_revision_required(info: Mapping[str, Any] | None, proposal: Mapping[str, Any] | None, *, packet_status: str = "draft") -> bool:
    return bool(evaluate_stage_b_semantic_revision_eligibility(info, proposal, packet_status=packet_status).get("eligible"))


def archive_stage_b_attempt(info: Mapping[str, Any] | None, *, proposal: Mapping[str, Any] | None = None, attempt_id: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Copy the active Stage B evidence into one immutable archive entry.

    Repeating the same byte-identical archive is a no-op.  Reusing an attempt
    ID with different content fails closed.
    """
    result = copy.deepcopy(dict(info or {}))
    progressive = result.get("progressive_director_authoring") if isinstance(result.get("progressive_director_authoring"), Mapping) else {}
    progressive = copy.deepcopy(dict(progressive))
    active = progressive.get("stage_b") if isinstance(progressive.get("stage_b"), Mapping) else {}
    active_id = str(attempt_id or active.get("attempt_id") or "")
    if not active_id:
        raise ValueError("DIRECTOR_STAGE_B_ARCHIVE_ATTEMPT_ID_REQUIRED")
    review = active.get("semantic_review") if isinstance(active.get("semantic_review"), Mapping) else result.get("semantic_review", {})
    entry = {
        "attempt_id": active_id,
        "authoring_stage": "CREATIVE_ENRICHMENT",
        "authorization_id": str(active.get("authorization_id") or ""),
        "ir": copy.deepcopy(active.get("ir")),
        "ir_fingerprint": str(active.get("ir_fingerprint") or active.get("fingerprint") or ""),
        "structural_status": str(active.get("status") or ""),
        "validation_state": str(active.get("validation_state") or ""),
        "merge_state": str(active.get("merge_state") or ""),
        "semantic_review": copy.deepcopy(dict(review)) if isinstance(review, Mapping) else {},
        "semantic_review_fingerprint": semantic_review_fingerprint(review if isinstance(review, Mapping) else {}),
        "stage_a_materialized_fingerprint": str(active.get("stage_a_materialized_fingerprint") or ""),
        "source_authoring_unit_fingerprint": str(active.get("source_authoring_unit_fingerprint") or result.get("source_authoring_unit_fingerprint") or ""),
        "source_authority_content_fingerprint": str(active.get("source_authority_content_fingerprint") or result.get("source_authority_content_fingerprint") or ""),
        "provider_provenance": copy.deepcopy(active.get("provider_provenance") or {}),
        "provider_request_identity": copy.deepcopy(result.get("stage_b_provider_request") or {}),
        "raw_forensic": copy.deepcopy(result.get("stage_b_raw_response_forensic") or {}),
        "validation": copy.deepcopy(result.get("stage_b_validation") or {}),
        "proposal": copy.deepcopy(dict(proposal or {})),
        "proposal_fingerprint": proposal_fingerprint(proposal if isinstance(proposal, Mapping) else {}),
    }
    archives = progressive.get("stage_b_attempts") if isinstance(progressive.get("stage_b_attempts"), list) else []
    archives = copy.deepcopy(archives)
    existing = next((item for item in archives if isinstance(item, Mapping) and str(item.get("attempt_id") or "") == active_id), None)
    if existing is not None:
        if _canonical(existing) != _canonical(entry):
            raise ValueError("DIRECTOR_STAGE_B_ARCHIVE_CONFLICT")
        return result, {"status": "PASS", "changed": False, "archived": False, "attempt_id": active_id, "archive_count": len(archives)}
    archives.append(entry)
    progressive["stage_b_attempts"] = archives
    result["progressive_director_authoring"] = progressive
    return result, {"status": "PASS", "changed": True, "archived": True, "attempt_id": active_id, "archive_count": len(archives)}


def build_revision_parent_identity(*, parent_attempt_id: str, parent_ir_fingerprint: str, semantic_review: Mapping[str, Any], stage_a_attempt_id: str, stage_a_materialized_fingerprint: str, source_authoring_unit_fingerprint: str, source_authority_content_fingerprint: str) -> dict[str, Any]:
    review_fp = semantic_review_fingerprint(semantic_review)
    parent_fp = hashlib.sha256(_canonical({"attempt_id": parent_attempt_id, "ir_fingerprint": parent_ir_fingerprint, "semantic_review_fingerprint": review_fp}).encode("utf-8")).hexdigest()
    return {
        "revision_parent_attempt_id": str(parent_attempt_id), "revision_parent_stage_b_ir_fingerprint": str(parent_ir_fingerprint), "revision_parent_semantic_review_fingerprint": review_fp, "revision_parent_fingerprint": parent_fp,
        "stage_a_attempt_id": str(stage_a_attempt_id), "stage_a_materialized_fingerprint": str(stage_a_materialized_fingerprint), "source_authoring_unit_fingerprint": str(source_authoring_unit_fingerprint), "source_authority_content_fingerprint": str(source_authority_content_fingerprint),
    }


__all__ = ["semantic_review_fingerprint", "proposal_fingerprint", "stage_b_revision_feedback", "evaluate_stage_b_semantic_revision_eligibility", "is_stage_b_semantic_revision_required", "archive_stage_b_attempt", "build_revision_parent_identity"]
