"""Pure Director Quality V2.2 repair pipeline.

This module is the provider-neutral orchestration boundary used by offline
tests and the future benchmark runner.  It intentionally has no persistence
or media side effects: callers provide an optional Level 2 repair callable,
and only explicitly routed creative issues may invoke it.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Callable

from core.director_patch_deterministic_repair import DeterministicRepairError, deterministic_repair_document
from core.director_patch_repair import repair_failed_patch
from core.director_patch_schema import CreativePatchSchemaError, parse_creative_patch, parse_creative_patch_partial
from core.director_partial_acceptance import apply_partial_acceptance
from core.director_patch_validator import validate_compiled_patch_result
from core.director_quality_metrics import build_director_quality_v22_metrics
from core.issue_router import route_director_repair


FALLBACK_ROOT_CAUSES = {
    "SCHEMA_PARSE_FAILURE",
    "FORBIDDEN_PATH",
    "FACT_OVERRIDE",
    "INVALID_VALUE",
    "CROSS_PATCH_CONFLICT",
    "STRATEGY_CONFLICT",
    "AUXILIARY_BINDING_FAILURE",
    "QUALITY_REPAIR_EXHAUSTED",
    "LLM_REPAIR_PARSE_FAILURE",
    "LLM_REPAIR_CONTRACT_FAILURE",
    "UNKNOWN",
}

_AVOIDABLE_TRACE_CLASSIFICATIONS = {
    "SAFE_ALIAS",
    "SAFE_ENVELOPE_VARIANT",
    "CONTRACT_MISMATCH",
    "COMPILER_BUG",
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _shots(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in plan.get("shots", []) if isinstance(item, dict)] if isinstance(plan.get("shots"), list) else []


def _item_for_target(document: dict[str, Any], target: str) -> dict[str, Any] | None:
    for item in document.get("patches", []) if isinstance(document.get("patches"), list) else []:
        if isinstance(item, dict) and _text(item.get("plan_shot_id")) == _text(target):
            return copy.deepcopy(item)
    return None


def _fallback_reason(code: str) -> str:
    value = _text(code).upper()
    if value in {"DIRECTOR_FACT_OVERRIDE", "IMMUTABLE_VIOLATION"}:
        return "FACT_OVERRIDE"
    if value in {"DIRECTOR_PATCH_PATH_FORBIDDEN", "DIRECTOR_PATCH_FIELD_FORBIDDEN", "FORBIDDEN_PATH"}:
        return "FORBIDDEN_PATH"
    if value in {"UNKNOWN_PLAN_SHOT_ID", "DIRECTOR_PATCH_TARGET_MISMATCH"}:
        return "UNKNOWN"
    if value in {"CROSS_PATCH_CONFLICT", "DIRECTOR_PATCH_DUPLICATE_TARGET"}:
        return "CROSS_PATCH_CONFLICT"
    if value in {"INVALID_AUXILIARY_TYPE", "AUXILIARY_BINDING_FAILURE", "INVALID_SOURCE_BEAT"}:
        return "AUXILIARY_BINDING_FAILURE"
    if value in {"INVALID_PATCH_VALUE", "INVALID_CREATIVE_VALUE"}:
        return "INVALID_VALUE"
    if value in {"DIRECTOR_PATCH_SCHEMA_INVALID", "DIRECTOR_PATCH_SCHEMA_VERSION_INVALID"}:
        return "SCHEMA_PARSE_FAILURE"
    if value.startswith("LLM_REPAIR_PARSE"):
        return "LLM_REPAIR_PARSE_FAILURE"
    if value.startswith("LLM_REPAIR_CONTRACT"):
        return "LLM_REPAIR_CONTRACT_FAILURE"
    return "UNKNOWN"


def _is_safe_fallback(code: str, root_cause: str = "") -> bool:
    value = _text(code).upper()
    cause = _text(root_cause).upper()
    return value in {
        "DIRECTOR_FACT_OVERRIDE", "IMMUTABLE_VIOLATION", "UNKNOWN_PLAN_SHOT_ID",
        "INVALID_SOURCE_BEAT", "AUXILIARY_BINDING_FAILURE", "INVALID_ASSET_REFERENCE",
    } or cause in {"FACT_OVERRIDE", "UNKNOWN_PLAN_SHOT_ID", "AUXILIARY_BINDING_FAILURE"}


def process_patch_pipeline(
    *,
    structural_shot_plan: dict[str, Any],
    contract: dict[str, Any],
    strategy: dict[str, Any],
    raw_output: Any,
    treatment: dict[str, Any] | None = None,
    blocking: dict[str, Any] | None = None,
    llm_repair_callable: Callable[[dict[str, Any]], Any] | None = None,
    max_llm_attempts: int = 2,
    scene_id: str = "",
    episode: int | str | None = None,
) -> dict[str, Any]:
    """Run Raw → Level 0 → Level 1 → Contract → optional Level 2 locally.

    The returned ``fallbacks`` list is patch/proposal scoped.  A reject-only
    issue never invokes ``llm_repair_callable``; a Level 2 call receives only
    the failed item through :func:`repair_failed_patch`.
    """

    from core.director_rejection_trace import (
        capture_raw_patch_trace,
        capture_raw_patch_traces,
        finalize_rejection_trace,
        find_trace_for_rejection,
    )

    baseline = copy.deepcopy(structural_shot_plan)
    known_ids = [_text(item.get("plan_shot_id")) for item in _shots(baseline) if _text(item.get("plan_shot_id"))]
    trace_scene_id = _text(scene_id) or _text(baseline.get("scene_id"))
    raw_traces = capture_raw_patch_traces(
        raw_output,
        scene_id=trace_scene_id,
        episode=episode,
        known_plan_shot_ids=known_ids,
        allowed_patch_paths=_dict(contract).get("allowed_patch_paths") or None,
    )
    rejection_traces: dict[str, dict[str, Any]] = {}
    stage_counts = {key: 0 for key in (
        "raw_parse_pass", "normalized_parse_pass", "first_pass_schema_pass",
        "first_pass_contract_pass", "post_normalization_contract_pass",
        "post_deterministic_repair_pass", "post_llm_repair_pass", "final_contract_pass",
    )}
    fallbacks: list[dict[str, Any]] = []
    repair_attempts: list[dict[str, Any]] = []
    normalization_events: list[dict[str, Any]] = []
    deterministic_events: list[dict[str, Any]] = []
    path_resolution_metrics: dict[str, Any] = {}
    creative_recoverable_patch_count = 0
    creative_recovered_patch_count = 0
    safe_fallback_count = 0
    avoidable_fallback_count = 0
    successful_repairs = 0
    failed_repairs = 0
    level01: dict[str, Any] = {"rejected": []}

    def _fallback_bucket(classification: str) -> tuple[str, bool]:
        """Map evidence classification to the legacy two-bucket metrics."""

        if _text(classification).upper() in _AVOIDABLE_TRACE_CLASSIFICATIONS:
            return "AVOIDABLE_TECHNICAL_FALLBACK", False
        # Forbidden, ambiguous, fact-override, unknown-shot, and invalid
        # values are all required fail-closed outcomes once repair is
        # exhausted; none is an avoidable technical fallback.
        return "SAFE_REQUIRED_FALLBACK", True

    def _stage_for_issue(code: str, *, final: bool = False, repair: bool = False) -> str:
        if final:
            return "FINAL_FALLBACK"
        if repair:
            return "LLM_REPAIR"
        value = _text(code).upper()
        if value in {"DIRECTOR_PATCH_PATH_FORBIDDEN", "DIRECTOR_PATCH_PATH_MISSING", "AMBIGUOUS_PATCH_PATH"}:
            return "PATH_RESOLUTION"
        if value in {"DIRECTOR_PATCH_FIELD_FORBIDDEN", "DIRECTOR_FACT_OVERRIDE", "IMMUTABLE_VIOLATION", "UNKNOWN_PLAN_SHOT_ID"}:
            return "CONTRACT_VALIDATION"
        if value in {"DIRECTOR_PATCH_NORMALIZATION_CONFLICT", "DIRECTOR_PATCH_DUPLICATE_TARGET", "CROSS_PATCH_CONFLICT"}:
            return "PATCH_MERGE"
        if value in {"INVALID_PATCH_VALUE", "DIRECTOR_PATCH_SCHEMA_INVALID", "DIRECTOR_PATCH_ID_MISSING"}:
            return "VALUE_SCHEMA"
        return "CONTRACT_VALIDATION"

    def _trace_for_issue(item: dict[str, Any], failed_patch: dict[str, Any] | None = None) -> dict[str, Any]:
        target = _text(item.get("plan_shot_id") or item.get("target_id"))
        raw_path = _text(item.get("raw_path") or item.get("path"))
        provider_index = item.get("provider_patch_index")
        trace = find_trace_for_rejection(
            raw_traces,
            plan_shot_id=target,
            raw_path=raw_path,
            provider_patch_index=provider_index if isinstance(provider_index, int) else None,
        )
        if trace is None:
            # A malformed document may not contain an addressable raw item.
            # Keep the gap explicit instead of fabricating a raw provider
            # shape; this trace is still useful for stage/classification audit.
            trace = capture_raw_patch_trace(
                failed_patch if isinstance(failed_patch, dict) else item,
                scene_id=trace_scene_id,
                episode=episode,
                provider_patch_index=int(provider_index or -1),
                known_plan_shot_ids=known_ids,
                allowed_patch_paths=_dict(contract).get("allowed_patch_paths") or None,
            )
            trace["raw_capture_status"] = "synthetic_unaddressable_item"
        # Auxiliary schema errors report the proposal container path plus the
        # forbidden field in the error message.  Preserve that exact raw JSON
        # location instead of presenting the first camera field as if it were
        # the rejected path.
        if trace.get("raw_item_type") == "auxiliary_shot_proposal":
            message = _text(item.get("message") or item.get("reason"))
            issue_path = _text(item.get("path")) or _text(trace.get("raw_item_path"))
            match = re.search(r"forbidden fields?:\s*(.+)$", message, flags=re.IGNORECASE)
            if issue_path and match:
                field = _text(match.group(1).split(",", 1)[0])
                if field:
                    rejected_path = f"{issue_path}.{field}"
                    trace["raw_path"] = rejected_path
                    trace["raw_paths"] = list(dict.fromkeys([rejected_path, *list(trace.get("raw_paths") or [])]))[:32]
                    trace["raw_value_type"] = "forbidden_field"
                    anchor = _text(trace.get("raw_anchor_plan_shot_id"))
                    trace["parsed"] = {"plan_shot_id": anchor, "path": rejected_path}
                    # Auxiliary proposals do not pass through the shot-path
                    # resolver, but the rejected JSON location is still a
                    # stable canonical evidence path for audit purposes.
                    trace["canonical"] = {"plan_shot_id": anchor, "path": rejected_path}
                    trace["canonical_path"] = rejected_path
                    trace["path_resolution_rule"] = "auxiliary_schema"
                    trace["path_source_format"] = "auxiliary"
                    trace["path_alias_hit"] = False
                    trace["allowed_path_match"] = False
        return trace

    def _save_trace(
        item: dict[str, Any],
        *,
        failed_patch: dict[str, Any] | None = None,
        stage: str,
        final_action: str,
        repair_attempts_for_trace: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        trace = _trace_for_issue(item, failed_patch)
        completed = finalize_rejection_trace(
            trace,
            issue_code=_text(item.get("code") or item.get("issue_code")) or "UNKNOWN",
            rejection_stage=stage,
            rejection_reason=_text(item.get("message") or item.get("reason")),
            final_action=final_action,
            repair_attempts=repair_attempts_for_trace,
            normalization_rules=trace.get("normalization", {}).get("rules") if isinstance(trace.get("normalization"), dict) else None,
        )
        rejection_traces[completed["trace_id"]] = completed
        return completed

    level01_rejected: list[dict[str, Any]] = []
    try:
        parse_creative_patch(raw_output)
        stage_counts["raw_parse_pass"] = 1
    except CreativePatchSchemaError:
        pass

    try:
        level01 = deterministic_repair_document(
            raw_output,
            known_plan_shot_ids=known_ids,
            allowed_patch_paths=_dict(contract).get("allowed_patch_paths") or None,
        )
        normalization_events = copy.deepcopy(level01.get("events") or [])
        deterministic_events = [event for event in normalization_events if "kind" in event]
        path_resolution_metrics = copy.deepcopy((level01.get("document") or {}).get("normalization_metadata", {}).get("path_resolution") or {})
        normalized_document = parse_creative_patch(level01["schema_document"])
        stage_counts["normalized_parse_pass"] = 1
        stage_counts["first_pass_schema_pass"] = 1
    except (DeterministicRepairError, CreativePatchSchemaError) as exc:
        code = getattr(exc, "code", "DIRECTOR_PATCH_SCHEMA_INVALID")
        path_resolution_metrics = copy.deepcopy(getattr(exc, "path_metrics", {}) or {})
        # Recover independent valid items for partial acceptance.  This path
        # is still fail-closed for fatal protocol/fingerprint errors, but a
        # malformed sibling must not erase an otherwise valid patch.
        partial = parse_creative_patch_partial(raw_output)
        if partial.get("fatal") or not isinstance(partial.get("document"), dict):
            fallback_root = _fallback_reason(code)
            fallback_safe = _is_safe_fallback(code, fallback_root)
            safe_fallback_count += int(fallback_safe)
            avoidable_fallback_count += int(not fallback_safe)
            fallbacks.append({
                "scene_id": _text(baseline.get("scene_id")),
                "plan_shot_id": "",
                "proposal_id": "",
                "root_cause": fallback_root,
                "repair_level_attempted": 0,
                "attempt_count": 0,
                "final_action": "REJECT_DOCUMENT",
                "code": code,
                "message": str(exc),
                "fallback_class": "SAFE_REQUIRED_FALLBACK" if fallback_safe else "AVOIDABLE_TECHNICAL_FALLBACK",
            })
            return {
                "status": "fallback",
                "candidate": baseline,
                "baseline": baseline,
                "normalized_document": None,
                "validation": {"status": "invalid", "contract_pass": False, "errors": [{"code": code, "message": str(exc)}], "warnings": []},
                "stage_counts": stage_counts,
                "normalization_events": normalization_events,
                "path_resolution": path_resolution_metrics,
                "creative_recoverable_patch_count": creative_recoverable_patch_count,
                "creative_recovered_patch_count": creative_recovered_patch_count,
                "safe_fallback_count": safe_fallback_count,
                "avoidable_fallback_count": avoidable_fallback_count,
                "successful_repairs": successful_repairs,
                "failed_repairs": failed_repairs,
                "deterministic_repair_events": deterministic_events,
                "repair_attempts": repair_attempts,
                "fallbacks": fallbacks,
                "rejection_traces": list(rejection_traces.values()),
                "metrics": build_director_quality_v22_metrics(
                    stage_counts=stage_counts,
                    repair_cost={"normalization_events": len(normalization_events), "deterministic_repair_events": len(deterministic_events)},
                    creative_patch_count=len(fallbacks),
                    retained_creative_patch_count=0,
                    fallback_free_scene_count=0,
                    scene_count=1,
                    creative_recoverable_patch_count=0,
                    safe_fallback_count=safe_fallback_count,
                    avoidable_fallback_count=avoidable_fallback_count,
                ),
                "side_effects": {"production_rows_written": 0, "storyboard_shots_created": 0, "media_calls": 0, "object_storage_calls": 0},
            }
        normalized_document = partial["document"]
        level01_rejected = [item for item in (partial.get("errors") or []) if isinstance(item, dict)]
        stage_counts["normalized_parse_pass"] = 1
        stage_counts["first_pass_schema_pass"] = int(not level01_rejected)

    accepted = apply_partial_acceptance(baseline, normalized_document, contract, treatment=treatment, blocking=blocking)
    validation = accepted.get("validation") if isinstance(accepted.get("validation"), dict) else {}
    stage_counts["post_normalization_contract_pass"] = int(bool(validation.get("contract_pass")))
    stage_counts["first_pass_contract_pass"] = int(bool(validation.get("contract_pass")) and not accepted.get("rejected_patches"))
    stage_counts["post_deterministic_repair_pass"] = stage_counts["post_normalization_contract_pass"]

    # Conflicts and compiler rejects are recorded without sending them to an
    # LLM unless the explicit routing table says they are creative Level 2.
    for rejected in list(accepted.get("rejected_patches") or []) + list(level01.get("rejected") or []) + level01_rejected:
        item = _dict(rejected)
        code = _text(item.get("code") or item.get("issue_code")) or "UNKNOWN"
        route = route_director_repair(code)
        target = _text(item.get("plan_shot_id") or item.get("target_id"))
        failed_patch = _item_for_target(normalized_document, target)
        if route.get("llm_allowed") and failed_patch and llm_repair_callable:
            creative_recoverable_patch_count += 1
            repaired = repair_failed_patch(
                structural_shot_plan=baseline,
                failed_patch=failed_patch,
                issue=item,
                contract=contract,
                strategy=strategy,
                repair_callable=llm_repair_callable,
                max_attempts=max_llm_attempts,
                repair_level=2,
                repair_engine="llm",
                stop_on_same_error=True,
            )
            repair_attempts.append({"kind": "patch", "identity": target, **{key: repaired.get(key) for key in ("status", "attempt_count", "attempts", "fallback_to_baseline")}})
            if repaired.get("status") == "repaired" and isinstance(repaired.get("accepted_patch"), dict):
                _save_trace(
                    item,
                    failed_patch=failed_patch,
                    stage=_stage_for_issue(code, repair=True),
                    final_action="REPAIR",
                    repair_attempts_for_trace=repaired.get("attempts") or [],
                )
                successful_repairs += 1
                creative_recovered_patch_count += 1
                normalized_document = copy.deepcopy(normalized_document)
                normalized_document["patches"] = [patch for patch in normalized_document["patches"] if _text(patch.get("plan_shot_id")) != target]
                normalized_document["patches"].append(copy.deepcopy(repaired["accepted_patch"]))
                # The strict parser/compiler recompute document metadata after
                # an accepted Level 2 item is merged.
                normalized_document.pop("patch_fingerprint", None)
                normalized_document.pop("normalization_metadata", None)
                accepted = apply_partial_acceptance(baseline, normalized_document, contract, treatment=treatment, blocking=blocking)
                validation = accepted.get("validation") if isinstance(accepted.get("validation"), dict) else validation
                stage_counts["post_llm_repair_pass"] = int(bool(validation.get("contract_pass")))
                continue
            failed_repairs += 1
            completed_trace = _save_trace(
                item,
                failed_patch=failed_patch,
                stage=_stage_for_issue(code, repair=True),
                final_action="FALLBACK",
                repair_attempts_for_trace=repaired.get("attempts") or [],
            )
            fallback_class, is_safe_required = _fallback_bucket(completed_trace.get("fallback_classification"))
            safe_fallback_count += int(is_safe_required)
            avoidable_fallback_count += int(not is_safe_required)
            fallbacks.append({
                "scene_id": trace_scene_id, "plan_shot_id": target, "proposal_id": "",
                "root_cause": "LLM_REPAIR_CONTRACT_FAILURE", "repair_level_attempted": 2,
                "attempt_count": int(repaired.get("attempt_count") or 0), "final_action": "FALLBACK_BASELINE_PATCH", "code": code,
                "fallback_class": fallback_class,
                "trace_id": completed_trace["trace_id"],
            })
            continue
        fallback_root = "QUALITY_REPAIR_EXHAUSTED" if route.get("llm_allowed") else _fallback_reason(code)
        completed_trace = _save_trace(
            item,
            failed_patch=failed_patch,
            stage=_stage_for_issue(code),
            final_action="FALLBACK",
        )
        fallback_class, is_safe_required = _fallback_bucket(completed_trace.get("fallback_classification"))
        safe_fallback_count += int(is_safe_required)
        avoidable_fallback_count += int(not is_safe_required)
        fallbacks.append({
            "scene_id": trace_scene_id, "plan_shot_id": target, "proposal_id": _text(item.get("proposal_id")),
            "root_cause": "QUALITY_REPAIR_EXHAUSTED" if route.get("llm_allowed") else _fallback_reason(code),
            "repair_level_attempted": route.get("repair_level"),
            "attempt_count": 0, "final_action": "REJECT_PATCH", "code": code,
            "fallback_class": fallback_class,
            "trace_id": completed_trace["trace_id"],
        })

    final_candidate = accepted.get("candidate") if isinstance(accepted.get("candidate"), dict) else baseline
    final_validation = accepted.get("validation") if isinstance(accepted.get("validation"), dict) else validation
    stage_counts["final_contract_pass"] = int(bool(final_validation.get("contract_pass")))
    evaluated = len(normalized_document.get("patches") or []) + len(fallbacks)
    retained = int(accepted.get("partial_acceptance", {}).get("accepted_patch_count") or 0)
    llm_calls = sum(int(item.get("attempt_count") or 0) for item in repair_attempts)
    repair_cost = {
        "normalization_events": len(normalization_events),
        "deterministic_repair_events": len(deterministic_events),
        "llm_repair_calls": llm_calls,
        "fallback_after_repair_count": sum(1 for item in fallbacks if int(item.get("repair_level_attempted") or -1) == 2),
        "successful_repairs": successful_repairs,
        "failed_repairs": failed_repairs,
        "creative_patches_saved_by_llm_repair": creative_recovered_patch_count,
        "fallbacks_prevented_by_repair": creative_recovered_patch_count,
    }
    metrics = build_director_quality_v22_metrics(
        stage_counts={**stage_counts, "total_scenes": 1, "evaluated_patch_count": evaluated, "fallback_patch_count": len(fallbacks)},
        repair_cost=repair_cost,
        creative_patch_count=evaluated,
        retained_creative_patch_count=retained,
        fallback_free_scene_count=int(not fallbacks),
        scene_count=1,
        creative_recoverable_patch_count=creative_recoverable_patch_count,
        creative_recovered_patch_count=creative_recovered_patch_count,
        safe_fallback_count=safe_fallback_count,
        avoidable_fallback_count=avoidable_fallback_count,
    )
    return {
        "status": "valid" if not fallbacks else "partial",
        "candidate": final_candidate,
        "baseline": baseline,
        "normalized_document": normalized_document,
        "partial_acceptance": copy.deepcopy(accepted.get("partial_acceptance") or {}),
        "validation": final_validation,
        "stage_counts": stage_counts,
        "normalization_events": normalization_events,
        "path_resolution": path_resolution_metrics,
        "creative_recoverable_patch_count": creative_recoverable_patch_count,
        "creative_recovered_patch_count": creative_recovered_patch_count,
        "safe_fallback_count": safe_fallback_count,
        "avoidable_fallback_count": avoidable_fallback_count,
        "successful_repairs": successful_repairs,
        "failed_repairs": failed_repairs,
        "deterministic_repair_events": deterministic_events,
        "repair_attempts": repair_attempts,
        "fallbacks": fallbacks,
        "rejection_traces": list(rejection_traces.values()),
        "metrics": metrics,
        "side_effects": {"production_rows_written": 0, "storyboard_shots_created": 0, "media_calls": 0, "object_storage_calls": 0},
    }


__all__ = ["FALLBACK_ROOT_CAUSES", "process_patch_pipeline"]
