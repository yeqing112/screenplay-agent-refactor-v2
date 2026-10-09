"""Append-only Stage B semantic revision contracts.

This module contains only deterministic state and identity helpers.  It does
not call a Provider and it never mutates a database row by itself.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping

from core.director_progressive_authoring import is_progressive_stage_validated, render_stage_b_schema_contract
from core.director_semantic_grounding import (
    SEMANTIC_REVIEW_POLICY_V1,
    SEMANTIC_REVIEW_POLICY_V2,
    resolve_required_semantic_review_policy,
    semantic_policy_v2_fingerprint,
)


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


def stage_b_revision_feedback_v2(review: Mapping[str, Any] | None) -> dict[str, Any]:
    """Project only V2 production-blocking findings into fresh-generation constraints."""
    review = review if isinstance(review, Mapping) else {}
    items: list[dict[str, Any]] = []
    grounding = review.get("source_grounding") if isinstance(review.get("source_grounding"), Mapping) else {}
    for finding in grounding.get("findings", []) if isinstance(grounding.get("findings"), list) else []:
        if not isinstance(finding, Mapping):
            continue
        category = str(finding.get("classification") or "")
        if category in {"SAFE_CREATIVE_DIRECTION", "SOURCE_EXPLICIT", "SAFE_PROHIBITION", "META_COMPLIANCE", "SOURCE_SUPPORTED_ACTION"}:
            continue
        items.append({"category": category, "path": str(finding.get("path") or ""), "matched_term": str(finding.get("matched_term") or ""), "constraint": _v2_constraint_for(category, str(finding.get("matched_term") or ""))})
    physical = review.get("physical_action_authority") if isinstance(review.get("physical_action_authority"), Mapping) else {}
    for finding in physical.get("findings", []) if isinstance(physical.get("findings"), list) else []:
        if not isinstance(finding, Mapping):
            continue
        category = str(finding.get("classification") or "")
        if category in {"SOURCE_SUPPORTED_ACTION", "SAFE_CREATIVE_DIRECTION", "SAFE_PROHIBITION", "META_COMPLIANCE"}:
            continue
        items.append({"category": category, "path": str(finding.get("path") or ""), "matched_term": str(finding.get("matched_term") or ""), "constraint": _v2_constraint_for(category, str(finding.get("matched_term") or ""))})
    leakage = review.get("downstream_leakage") if isinstance(review.get("downstream_leakage"), Mapping) else {}
    for violation in leakage.get("violations", []) if isinstance(leakage.get("violations"), list) else []:
        if not isinstance(violation, Mapping):
            continue
        category = str(violation.get("category") or "")
        items.append({"category": "DOWNSTREAM_SHOTPLAN_LEAKAGE", "path": str(violation.get("path") or ""), "matched_term": str(violation.get("matched_term") or ""), "constraint": _v2_constraint_for("DOWNSTREAM_SHOTPLAN_LEAKAGE", str(violation.get("matched_term") or ""))})
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        key = (item["category"], item["path"], item["matched_term"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return {
        "schema_version": "director_revision_feedback_v2",
        "semantic_review_policy": SEMANTIC_REVIEW_POLICY_V2,
        "semantic_policy_fingerprint": semantic_policy_v2_fingerprint(),
        "semantic_review_fingerprint": semantic_review_fingerprint(review),
        "constraints": unique,
        "constraint_count": len(unique),
        "is_repair_instruction": False,
        "fresh_generation_required": True,
    }


STRUCTURAL_REVISION_FEEDBACK_VERSION = "director_revision_structural_feedback_v1"
_STRUCTURAL_FAILURE_CODES = {
    "SCHEMA_REQUIRED_FIELD_MISSING",
    "SCHEMA_TYPE_INVALID",
    "SCHEMA_ADDITIONAL_PROPERTY",
    "SCHEMA_CONST_INVALID",
    "DUPLICATE_JSON_KEY",
}


def structural_revision_feedback_fingerprint(feedback: Mapping[str, Any] | None) -> str:
    """Hash the deterministic failure identity and normalized constraints."""
    value = feedback if isinstance(feedback, Mapping) else {}
    bound = {
        "schema_version": value.get("schema_version"),
        "failed_attempt_id": value.get("failed_attempt_id"),
        "failed_attempt_status": value.get("failed_attempt_status"),
        "constraints": value.get("constraints") if isinstance(value.get("constraints"), list) else [],
        "failed_attempt_raw_sha256": value.get("failed_attempt_raw_sha256"),
        "provider_request_fingerprint": value.get("provider_request_fingerprint"),
    }
    return hashlib.sha256(_canonical(bound).encode("utf-8")).hexdigest()


def _structural_expected_type(field: str, path: str) -> str:
    contract = render_stage_b_schema_contract()
    if path == "$" and field:
        return str(contract.get("field_types", {}).get(field) or "unknown")
    return str(contract.get("field_types", {}).get(path.lstrip("$.") or field) or "unknown")


def _structural_constraint(error: Mapping[str, Any]) -> dict[str, Any] | None:
    code = str(error.get("code") or error.get("error_code") or "").strip()
    if code in {"DIRECTOR_CREATIVE_ENRICHMENT_DUPLICATE_JSON_KEY", "DIRECTOR_BEAT_PLAN_DUPLICATE_JSON_KEY"}:
        code = "DUPLICATE_JSON_KEY"
    if code not in _STRUCTURAL_FAILURE_CODES:
        return None
    path = str(error.get("path") or "$")
    field = str(error.get("field") or error.get("key") or "")
    if code == "SCHEMA_REQUIRED_FIELD_MISSING" and path == "$":
        category = "REQUIRED_TOP_LEVEL_FIELD_MISSING"
        expected_type = _structural_expected_type(field, path)
        constraint = f"The required top-level property {field} must be present and must satisfy the source-grounded Stage B schema ({expected_type})."
    elif code == "SCHEMA_TYPE_INVALID":
        category = "SCHEMA_TYPE_INVALID"
        expected_type = str(error.get("expected") or _structural_expected_type(field, path))
        constraint = f"The value at {path} must satisfy the formal Stage B schema type {expected_type}."
    elif code == "SCHEMA_ADDITIONAL_PROPERTY":
        category = "SCHEMA_ADDITIONAL_PROPERTY"
        expected_type = "no additional property"
        constraint = f"Do not emit unknown property {field or path}; use only the formal Stage B schema keys."
    elif code == "SCHEMA_CONST_INVALID":
        category = "SCHEMA_CONST_INVALID"
        expected_type = "const"
        constraint = f"The value at {path} must equal the formal schema constant {error.get('expected')}."
    else:
        category = "DUPLICATE_JSON_KEY"
        expected_type = "unique JSON property names"
        constraint = f"Emit each JSON property name once; duplicate key {field or path} is invalid."
    return {
        "category": category,
        "path": path,
        "field": field,
        "expected_type": expected_type,
        "constraint": constraint,
        "source": "persisted_attempt_failure_validation",
    }


def derive_structural_revision_feedback(
    info: Mapping[str, Any] | None,
    *,
    active_attempt_id: str | None = None,
) -> dict[str, Any]:
    """Derive eligible structural feedback from the latest persisted failure.

    The function is read-only and intentionally ignores report documents.  It
    only accepts a deterministic structural failure that is later than the
    active Stage B parent and belongs to the same revision chain.
    """
    info = info if isinstance(info, Mapping) else {}
    progressive = info.get("progressive_director_authoring") if isinstance(info.get("progressive_director_authoring"), Mapping) else {}
    stage_b = progressive.get("stage_b") if isinstance(progressive, Mapping) and isinstance(progressive.get("stage_b"), Mapping) else {}
    parent_id = str(active_attempt_id or stage_b.get("attempt_id") or "")
    parent_fp = str(stage_b.get("ir_fingerprint") or stage_b.get("fingerprint") or "")
    history = info.get("director_llm_attempts") if isinstance(info.get("director_llm_attempts"), list) else []
    latest = history[-1] if history and isinstance(history[-1], Mapping) else {}
    failed_id = str(latest.get("attempt_id") or "")
    if not failed_id or failed_id == parent_id or not failed_id.startswith("attempt-"):
        return {"status": "NOT_ELIGIBLE", "reason": "LATEST_ATTEMPT_NOT_LATER_THAN_ACTIVE_PARENT"}
    try:
        failed_ordinal = int(failed_id.split("-", 1)[1])
        parent_ordinal = int(parent_id.split("-", 1)[1]) if parent_id.startswith("attempt-") else -1
    except (TypeError, ValueError):
        return {"status": "NOT_ELIGIBLE", "reason": "ATTEMPT_ORDINAL_UNRESOLVED"}
    if failed_ordinal <= parent_ordinal:
        return {"status": "NOT_ELIGIBLE", "reason": "FAILED_ATTEMPT_NOT_NEWER_THAN_ACTIVE_PARENT"}
    archives = progressive.get("stage_b_attempts") if isinstance(progressive, Mapping) and isinstance(progressive.get("stage_b_attempts"), list) else []
    archive = next((item for item in archives if isinstance(item, Mapping) and str(item.get("attempt_id") or "") == failed_id), None)
    if not isinstance(archive, Mapping) or str(archive.get("authoring_stage") or "").upper() != "CREATIVE_ENRICHMENT":
        return {"status": "NOT_ELIGIBLE", "reason": "FAILED_ATTEMPT_ARCHIVE_MISSING"}
    status = str(archive.get("structural_status") or archive.get("status") or latest.get("status") or "")
    if "SCHEMA_INVALID" not in status and "IR_INVALID" not in status and "PARSE_FAILED" not in status:
        return {"status": "NOT_ELIGIBLE", "reason": "LATEST_ATTEMPT_NOT_DETERMINISTIC_STRUCTURAL_FAILURE"}
    revision_parent = archive.get("revision_parent") if isinstance(archive.get("revision_parent"), Mapping) else {}
    if str(revision_parent.get("revision_parent_attempt_id") or "") != parent_id:
        return {"status": "NOT_ELIGIBLE", "reason": "REVISION_CHAIN_PARENT_MISMATCH"}
    if parent_fp and str(revision_parent.get("revision_parent_stage_b_ir_fingerprint") or "") != parent_fp:
        return {"status": "NOT_ELIGIBLE", "reason": "REVISION_CHAIN_IR_FINGERPRINT_MISMATCH"}
    validation = archive.get("validation") if isinstance(archive.get("validation"), Mapping) else {}
    schema_report = validation.get("schema") if isinstance(validation.get("schema"), Mapping) else validation
    errors = schema_report.get("errors") if isinstance(schema_report, Mapping) and isinstance(schema_report.get("errors"), list) else []
    constraints: list[dict[str, Any]] = []
    for error in errors:
        if isinstance(error, Mapping):
            item = _structural_constraint(error)
            if item and item not in constraints:
                constraints.append(item)
    raw_forensic = archive.get("raw_forensic") if isinstance(archive.get("raw_forensic"), Mapping) else {}
    provider_identity = archive.get("provider_request_identity") if isinstance(archive.get("provider_request_identity"), Mapping) else {}
    provider_fp = str(provider_identity.get("provider_request_fingerprint_v2") or "")
    if not constraints:
        return {"status": "NOT_ELIGIBLE", "reason": "NO_SUPPORTED_STRUCTURAL_FAILURE"}
    feedback: dict[str, Any] = {
        "schema_version": STRUCTURAL_REVISION_FEEDBACK_VERSION,
        "failed_attempt_id": failed_id,
        "failed_attempt_status": status,
        "failed_attempt_raw_sha256": str(raw_forensic.get("raw_response_sha256") or ""),
        "provider_request_fingerprint": provider_fp,
        "parent_attempt_id": parent_id,
        "parent_ir_fingerprint": parent_fp,
        "constraints": constraints,
        "constraint_count": len(constraints),
        "is_repair_instruction": False,
        "fresh_generation_required": True,
        "eligibility": {
            "latest_failed_attempt": True,
            "failed_attempt_ordinal": failed_ordinal,
            "active_parent_ordinal": parent_ordinal,
            "authoring_stage": "CREATIVE_ENRICHMENT",
            "same_revision_chain": True,
            "deterministic_structural_failure": True,
        },
    }
    feedback["structural_feedback_fingerprint"] = structural_revision_feedback_fingerprint(feedback)
    feedback["status"] = "ELIGIBLE"
    return feedback


def _v2_constraint_for(category: str, matched: str) -> str:
    if category == "UNSUPPORTED_CERTAINTY_COLLAPSE":
        return "Preserve source uncertainty. Do not turn 是否、可能、想不起、无法确认 or unknown into 首次、从未、一定、确认 or 必然."
    if category == "UNSUPPORTED_STORY_ACTION":
        return "Do not invent canonical story actions involving key props, such as opening a box, picking up a prop, taking film, or handing over a key, unless SourceAuthoringUnits explicitly support them."
    if category == "DOWNSTREAM_SCENEBLOCKING_LEAKAGE":
        return "Do not specify concrete spatial blocking, paths, placement, or movement such as walking to or bringing someone to a prop; leave SceneBlocking to its downstream authority."
    if category in {"DOWNSTREAM_SHOTPLAN_LEAKAGE", "SHOT_EXECUTION"}:
        return "Do not specify shot size, camera, lens, movement, frame, keyframe, or concrete shot execution."
    return "Use only source-grounded creative direction and preserve the Stage A boundary."


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
    required_policy: str | None = None,
    resolved_review: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    info = info if isinstance(info, Mapping) else {}
    proposal = proposal if isinstance(proposal, Mapping) else {}
    progressive = info.get("progressive_director_authoring") if isinstance(info.get("progressive_director_authoring"), Mapping) else {}
    stage_a = progressive.get("stage_a") if isinstance(progressive, Mapping) else None
    stage_b = progressive.get("stage_b") if isinstance(progressive, Mapping) else None
    projection = proposal.get("creative_projection") if isinstance(proposal.get("creative_projection"), Mapping) else {}
    stage_b_attempt_id = str(stage_b.get("attempt_id") or "") if isinstance(stage_b, Mapping) else ""
    review = resolved_review if isinstance(resolved_review, Mapping) else (
        stage_b.get("semantic_review_v2") if isinstance(stage_b, Mapping) and isinstance(stage_b.get("semantic_review_v2"), Mapping) else
        stage_b.get("semantic_review") if isinstance(stage_b, Mapping) and isinstance(stage_b.get("semantic_review"), Mapping) else info.get("semantic_review")
    )
    policy = required_policy or resolve_required_semantic_review_policy(authoring_stage="CREATIVE_ENRICHMENT", attempt_id=stage_b_attempt_id, revision_context=bool(required_policy))
    policy_checks = {
        "required_policy_bound": bool(policy),
        "semantic_review_policy": policy == SEMANTIC_REVIEW_POLICY_V1 or (isinstance(review, Mapping) and review.get("policy_version") == SEMANTIC_REVIEW_POLICY_V2),
        "semantic_policy_fingerprint": policy == SEMANTIC_REVIEW_POLICY_V1 or (isinstance(review, Mapping) and review.get("semantic_policy_fingerprint") == semantic_policy_v2_fingerprint()),
    }
    checks = {
        "stage_a_validated": is_progressive_stage_validated(stage_a, authoring_stage="BEAT_PLAN"),
        "stage_b_structurally_validated": is_progressive_stage_validated(stage_b, authoring_stage="CREATIVE_ENRICHMENT"),
        "semantic_review_blocked": isinstance(review, Mapping) and str(review.get("status") or "").upper() == "BLOCKED",
        "merge_state_merged": isinstance(stage_b, Mapping) and str(stage_b.get("merge_state") or "") == "MERGED",
        "proposal_ready_for_review": proposal.get("decision") == "ready_for_review" and projection.get("status") == "PROPOSED",
        "production_not_confirmed": str(packet_status or "").lower() not in {"confirmed", "superseded"},
        "llm_draft_not_in_progress": not bool(info.get("llm_draft_in_progress")),
    }
    if policy == SEMANTIC_REVIEW_POLICY_V2:
        checks.update(policy_checks)
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
    if isinstance(active.get("semantic_review_v2"), Mapping):
        entry.update({
            "semantic_review_policy": str(active.get("semantic_review_policy") or SEMANTIC_REVIEW_POLICY_V2),
            "semantic_policy_fingerprint": str(active.get("semantic_policy_fingerprint") or semantic_policy_v2_fingerprint()),
            "semantic_review_v2": copy.deepcopy(dict(active.get("semantic_review_v2") or {})),
        })
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


def build_revision_parent_identity_v2(*, parent_attempt_id: str, parent_ir_fingerprint: str, semantic_review: Mapping[str, Any], stage_a_attempt_id: str, stage_a_materialized_fingerprint: str, source_authoring_unit_fingerprint: str, source_authority_content_fingerprint: str) -> dict[str, Any]:
    """Build a V2 parent identity whose hash binds policy and review version."""
    review_fp = semantic_review_fingerprint(semantic_review)
    policy_fp = semantic_policy_v2_fingerprint()
    payload = {
        "attempt_id": str(parent_attempt_id),
        "ir_fingerprint": str(parent_ir_fingerprint),
        "semantic_review_policy": SEMANTIC_REVIEW_POLICY_V2,
        "semantic_policy_fingerprint": policy_fp,
        "semantic_review_fingerprint": review_fp,
        "source_authoring_unit_fingerprint": str(source_authoring_unit_fingerprint),
        "source_authority_content_fingerprint": str(source_authority_content_fingerprint),
    }
    parent_fp = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return {
        "revision_parent_identity_version": "revision_parent_identity_v2",
        "revision_parent_attempt_id": str(parent_attempt_id),
        "revision_parent_stage_b_ir_fingerprint": str(parent_ir_fingerprint),
        "revision_parent_semantic_review_policy": SEMANTIC_REVIEW_POLICY_V2,
        "revision_parent_semantic_policy_fingerprint": policy_fp,
        "revision_parent_semantic_review_fingerprint": review_fp,
        "revision_parent_fingerprint": parent_fp,
        "stage_a_attempt_id": str(stage_a_attempt_id),
        "stage_a_materialized_fingerprint": str(stage_a_materialized_fingerprint),
        "source_authoring_unit_fingerprint": str(source_authoring_unit_fingerprint),
        "source_authority_content_fingerprint": str(source_authority_content_fingerprint),
    }


__all__ = ["semantic_review_fingerprint", "proposal_fingerprint", "stage_b_revision_feedback", "stage_b_revision_feedback_v2", "STRUCTURAL_REVISION_FEEDBACK_VERSION", "structural_revision_feedback_fingerprint", "derive_structural_revision_feedback", "evaluate_stage_b_semantic_revision_eligibility", "is_stage_b_semantic_revision_required", "archive_stage_b_attempt", "build_revision_parent_identity", "build_revision_parent_identity_v2"]
