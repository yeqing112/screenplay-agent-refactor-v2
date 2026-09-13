"""Contract reliability and ten-dimension Director Quality metrics."""

from __future__ import annotations

import copy
from typing import Any

from core.director_quality_validator import DIRECTOR_DIMENSIONS, score_director_quality


def _rate(numerator: int, denominator: int) -> float | None:
    return round(float(numerator) / float(denominator), 4) if denominator else None


def build_director_quality_v22_metrics(
    *,
    stage_counts: dict[str, int] | None = None,
    repair_cost: dict[str, Any] | None = None,
    creative_patch_count: int = 0,
    retained_creative_patch_count: int = 0,
    fallback_free_scene_count: int = 0,
    scene_count: int = 0,
    creative_recoverable_patch_count: int | None = None,
    creative_recovered_patch_count: int = 0,
    safe_fallback_count: int | None = None,
    avoidable_fallback_count: int | None = None,
) -> dict[str, Any]:
    """Build the staged stability/repair-cost metrics required by V2.2.

    Counts are supplied by the runner; this helper performs no quality-rule
    relaxation and returns ``None`` rates when a denominator is unavailable.
    """

    counts = {str(key): int(value or 0) for key, value in (stage_counts or {}).items()}
    stages = {
        "raw_parse_pass": counts.get("raw_parse_pass", 0),
        "normalized_parse_pass": counts.get("normalized_parse_pass", 0),
        "first_pass_schema_pass": counts.get("first_pass_schema_pass", 0),
        "first_pass_contract_pass": counts.get("first_pass_contract_pass", 0),
        "post_normalization_contract_pass": counts.get("post_normalization_contract_pass", 0),
        "post_deterministic_repair_pass": counts.get("post_deterministic_repair_pass", 0),
        "post_llm_repair_pass": counts.get("post_llm_repair_pass", 0),
        "final_contract_pass": counts.get("final_contract_pass", 0),
    }
    denominator = counts.get("total_scenes", scene_count)
    stage_metrics = {
        key: {"count": value, "total": denominator, "rate": _rate(value, denominator)}
        for key, value in stages.items()
    }
    costs = {
        "normalization_events": 0,
        "deterministic_repair_events": 0,
        "llm_repair_calls": 0,
        "llm_repair_calls_per_scene": None,
        "llm_repair_calls_per_failed_patch": None,
        "average_repair_attempts": None,
        "repair_token_cost": 0,
        "repair_latency_ms": 0,
        "fallback_after_repair_count": 0,
    }
    if isinstance(repair_cost, dict):
        costs.update(copy.deepcopy(repair_cost))
    if costs.get("llm_repair_calls_per_scene") is None:
        costs["llm_repair_calls_per_scene"] = _rate(int(costs.get("llm_repair_calls") or 0), denominator)
    result = {
        "stages": stage_metrics,
        "stage_counts": stages | {"total_scenes": denominator},
        "repair_cost": costs,
        "fallback_patch_count": int(counts.get("fallback_patch_count", 0)),
        "fallback_patch_rate": _rate(int(counts.get("fallback_patch_count", 0)), int(counts.get("evaluated_patch_count", 0))),
        "creative_retention_rate": _rate(int(retained_creative_patch_count), int(creative_patch_count)),
        "full_creative_scene_success_rate": _rate(int(fallback_free_scene_count), int(scene_count)),
    }
    if creative_recoverable_patch_count is not None:
        recoverable = int(creative_recoverable_patch_count)
        recovered = int(creative_recovered_patch_count or 0)
        result["creative_recovery_rate"] = _rate(recovered, recoverable)
        result["creative_loss_rate"] = _rate(max(recoverable - recovered, 0), int(creative_patch_count))
    else:
        result["creative_recovery_rate"] = None
        result["creative_loss_rate"] = None
    if safe_fallback_count is not None or avoidable_fallback_count is not None:
        safe = int(safe_fallback_count or 0)
        avoidable = int(avoidable_fallback_count or 0)
        result["fallback_classification"] = {
            "safe_required_fallback_count": safe,
            "avoidable_technical_fallback_count": avoidable,
            "safe_required_fallback_rate": _rate(safe, int(counts.get("fallback_patch_count", 0))),
            "avoidable_technical_fallback_rate": _rate(avoidable, int(counts.get("fallback_patch_count", 0))),
        }
    else:
        result["fallback_classification"] = None
    successful_repairs = int(costs.get("successful_repairs") or 0)
    failed_repairs = int(costs.get("failed_repairs") or 0)
    total_repairs = successful_repairs + failed_repairs
    costs.setdefault("successful_repairs", successful_repairs)
    costs.setdefault("failed_repairs", failed_repairs)
    costs["repair_success_rate"] = _rate(successful_repairs, total_repairs)
    costs.setdefault("creative_patches_saved_by_llm_repair", successful_repairs)
    costs.setdefault("fallbacks_prevented_by_repair", successful_repairs)
    costs["tokens_per_successful_repair"] = _rate(int(costs.get("repair_token_cost") or 0), successful_repairs)
    costs["latency_per_successful_repair_ms"] = _rate(int(costs.get("repair_latency_ms") or 0), successful_repairs)
    return result


def _score(plan: dict[str, Any] | None, *, treatment: dict[str, Any] | None, blocking: dict[str, Any] | None) -> dict[str, Any]:
    return score_director_quality(plan if isinstance(plan, dict) else {}, treatment=treatment, blocking=blocking)


def build_director_quality_metrics(
    *,
    baseline: dict[str, Any],
    first_candidate: dict[str, Any] | None = None,
    final_candidate: dict[str, Any] | None = None,
    treatment: dict[str, Any] | None = None,
    blocking: dict[str, Any] | None = None,
    contract_reliability: dict[str, Any] | None = None,
    partial_acceptance: dict[str, Any] | None = None,
    telemetry: dict[str, Any] | None = None,
    v22_stage_counts: dict[str, int] | None = None,
    v22_repair_cost: dict[str, Any] | None = None,
    creative_patch_count: int = 0,
    retained_creative_patch_count: int = 0,
    fallback_free_scene_count: int = 0,
    scene_count: int = 0,
    creative_recoverable_patch_count: int | None = None,
    creative_recovered_patch_count: int = 0,
    safe_fallback_count: int | None = None,
    avoidable_fallback_count: int | None = None,
) -> dict[str, Any]:
    """Record Baseline / Before Repair / After Repair separately.

    Missing candidates intentionally fall back to baseline while preserving a
    stage marker, so reports never mistake an absent planner output for a
    successful creative call.
    """

    first = first_candidate if isinstance(first_candidate, dict) else baseline
    final = final_candidate if isinstance(final_candidate, dict) else first
    scored = {
        "baseline": _score(baseline, treatment=treatment, blocking=blocking),
        "before_repair": _score(first, treatment=treatment, blocking=blocking),
        "after_repair": _score(final, treatment=treatment, blocking=blocking),
    }
    dimensions = {
        stage: {name: float(scored[stage]["dimensions"].get(name, 0.0)) for name in DIRECTOR_DIMENSIONS}
        for stage in scored
    }
    overall = {stage: float(scored[stage]["director_quality_score"]) for stage in scored}
    reliability = {
        "schema_pass": None,
        "patch_path_pass": None,
        "fact_override_count": 0,
        "fact_override_attempt_count": 0,
        "forbidden_field_attempt": False,
        "forbidden_field_attempt_count": 0,
        "schema_rejection_count": 0,
        "schema_rejections": [],
        "auxiliary_binding_pass": None,
        "parse_success": None,
        "repair_success": None,
        "scene_planner_success": None,
    }
    if isinstance(contract_reliability, dict):
        reliability.update(copy.deepcopy(contract_reliability))
    schema_rejections = [item for item in (reliability.get("schema_rejections") or []) if isinstance(item, dict)]
    reliability["schema_rejections"] = schema_rejections
    reliability["schema_rejection_count"] = len(schema_rejections)
    reliability["forbidden_field_attempt_count"] = int(reliability.get("forbidden_field_attempt_count") or sum(
        1
        for item in schema_rejections
        if str(item.get("code") or item.get("issue_code") or "") in {
            "DIRECTOR_FACT_OVERRIDE",
            "DIRECTOR_PATCH_FIELD_FORBIDDEN",
            "DIRECTOR_PATCH_PATH_FORBIDDEN",
        }
    ))
    reliability["forbidden_field_attempt"] = bool(reliability.get("forbidden_field_attempt")) or reliability["forbidden_field_attempt_count"] > 0
    reliability["fact_override_attempt_count"] = int(reliability.get("fact_override_attempt_count") or sum(
        1 for item in schema_rejections if str(item.get("code") or item.get("issue_code") or "") == "DIRECTOR_FACT_OVERRIDE"
    ))
    partial = {
        "accepted_patch_count": 0,
        "rejected_patch_count": 0,
        "repaired_patch_count": 0,
        "fallback_patch_count": 0,
    }
    if isinstance(partial_acceptance, dict):
        partial.update({key: int(value or 0) for key, value in partial_acceptance.items() if key in partial})
    result = {
        "director_dimensions": list(DIRECTOR_DIMENSIONS),
        "scores": {
            "baseline": scored["baseline"],
            "before_repair": scored["before_repair"],
            "after_repair": scored["after_repair"],
        },
        "dimensions": dimensions,
        "overall_director_quality": overall,
        "director_quality_delta": round(overall["after_repair"] - overall["baseline"], 2),
        "contract_reliability": reliability,
        "partial_acceptance": partial,
    }
    if isinstance(telemetry, dict):
        result["telemetry"] = copy.deepcopy(telemetry)
    if any(value is not None for value in (v22_stage_counts, v22_repair_cost)) or creative_patch_count or retained_creative_patch_count or fallback_free_scene_count or scene_count:
        result["v22"] = build_director_quality_v22_metrics(
            stage_counts=v22_stage_counts,
            repair_cost=v22_repair_cost,
            creative_patch_count=creative_patch_count,
            retained_creative_patch_count=retained_creative_patch_count,
            fallback_free_scene_count=fallback_free_scene_count,
            scene_count=scene_count,
            creative_recoverable_patch_count=creative_recoverable_patch_count,
            creative_recovered_patch_count=creative_recovered_patch_count,
            safe_fallback_count=safe_fallback_count,
            avoidable_fallback_count=avoidable_fallback_count,
        )
    return result


record_director_quality_metrics = build_director_quality_metrics
build_quality_metrics = build_director_quality_metrics


__all__ = ["build_director_quality_metrics", "record_director_quality_metrics", "build_quality_metrics", "build_director_quality_v22_metrics"]
