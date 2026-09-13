"""Contract reliability and ten-dimension Director Quality metrics."""

from __future__ import annotations

import copy
from typing import Any

from core.director_quality_validator import DIRECTOR_DIMENSIONS, score_director_quality


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
    return result


record_director_quality_metrics = build_director_quality_metrics
build_quality_metrics = build_director_quality_metrics


__all__ = ["build_director_quality_metrics", "record_director_quality_metrics", "build_quality_metrics"]
