"""Versioned aggregate metrics for the Director Quality V2.4 pilot."""

from __future__ import annotations

import math
from collections import Counter
from statistics import mean
from typing import Any, Iterable


QUALITY_V24_METRICS_SCHEMA_VERSION = "director-quality-v2-4-metrics-v1"
QUALITY_BUCKETS = ("<60", "60-69", "70-79", "80-89", ">=90")


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _score(row: dict[str, Any]) -> float | None:
    for value in (row.get("director_quality_score"), _dict(row.get("quality")).get("director_quality_score"), _dict(row.get("quality")).get("score")):
        parsed = _number(value)
        if parsed is not None:
            return parsed
    return None


def _nearest(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(math.ceil(float(percentile) * len(ordered))) - 1))
    return round(ordered[index], 4)


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _stage_rate(funnel: dict[str, Any], stage: str) -> float | None:
    for row in _list(funnel.get("stages")):
        if isinstance(row, dict) and _text(row.get("stage")) == stage:
            value = row.get("rate_from_eligible")
            return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
    return None


def _bucket(score: float) -> str:
    if score < 60:
        return "<60"
    if score < 70:
        return "60-69"
    if score < 80:
        return "70-79"
    if score < 90:
        return "80-89"
    return ">=90"


def build_director_quality_v24_metrics(
    *,
    scenes: Iterable[dict[str, Any]],
    funnel: dict[str, Any] | None = None,
    contract_metrics: dict[str, Any] | None = None,
    creative_value_metrics: dict[str, Any] | None = None,
    tail_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows = [item for item in scenes if isinstance(item, dict)]
    scores = [value for row in rows if (value := _score(row)) is not None]
    funnel_obj = _dict(funnel)
    contract = _dict(contract_metrics)
    creative = _dict(creative_value_metrics)
    tail = _dict(tail_metrics)
    bucket_counts = Counter(_bucket(value) for value in scores)
    counts = _dict(funnel_obj.get("counts"))
    detected = int(funnel_obj.get("trace_record_count") or funnel_obj.get("detected_opportunity_count") or counts.get("eligible_opportunities") or 0)
    detected_scene_count = sum(1 for row in rows if int(row.get("opportunity_count") or len(_list(row.get("opportunities"))) or 0) > 0)
    eligible = int(counts.get("eligible_opportunities") or funnel_obj.get("eligible_opportunity_count") or 0)
    act = int(counts.get("act") or 0)
    produced = int(counts.get("intervention_produced") or 0)
    contract_passed = int(counts.get("contract_passed") or 0)
    applied = int(counts.get("applied") or 0)
    improved = int(counts.get("target_dimension_improved") or 0)
    useful = int(counts.get("useful_accepted") or creative.get("useful_accepted_count") or 0)
    valid_skip = int(funnel_obj.get("valid_skip_count") or creative.get("valid_skip_count") or 0)
    fallback = int(creative.get("fallback_baseline_count") or contract.get("fallback_patch_count") or 0)
    return {
        "schema_version": QUALITY_V24_METRICS_SCHEMA_VERSION,
        "scene_count": len(rows),
        "quality_distribution": {
            "min": min(scores) if scores else None,
            "p10": _nearest(scores, 0.10),
            "p25": _nearest(scores, 0.25),
            "median": _nearest(scores, 0.50),
            "p75": _nearest(scores, 0.75),
            "p90": _nearest(scores, 0.90),
            "max": max(scores) if scores else None,
            "mean": round(mean(scores), 4) if scores else None,
            "buckets": {bucket: int(bucket_counts.get(bucket, 0)) for bucket in QUALITY_BUCKETS},
        },
        "opportunity_detection_rate": funnel_obj.get("opportunity_detection_rate") if funnel_obj.get("opportunity_detection_rate") is not None else _rate(detected_scene_count, len(rows)),
        "eligibility_rate": _rate(eligible, detected),
        "act_rate": _rate(act, eligible),
        "intervention_produced_rate": _rate(produced, eligible),
        "patch_contract_first_pass_rate": contract.get("patch_contract_first_pass_rate"),
        "patch_contract_final_pass_rate": contract.get("patch_contract_final_pass_rate"),
        "patch_apply_rate": _rate(applied, produced),
        "target_dimension_improvement_rate": _rate(improved, applied),
        "act_realization_rate": _rate(useful, act),
        "opportunity_address_rate": _rate(useful + valid_skip, eligible),
        "uca_v2": creative.get("useful_creative_acceptance_rate"),
        "uca_v3": creative.get("useful_creative_acceptance_v3_rate") or creative.get("useful_creative_acceptance_v3"),
        "valid_skip_rate": _rate(valid_skip, eligible),
        "fallback_rate": _rate(fallback, eligible),
        "tail_repair": {
            "execution_coverage": tail.get("execution_coverage"),
            "success_rate": tail.get("success_rate"),
            "before_mean": tail.get("before_mean"),
            "after_mean": tail.get("after_mean"),
        },
    }


build_quality_v24_metrics = build_director_quality_v24_metrics


__all__ = ["QUALITY_V24_METRICS_SCHEMA_VERSION", "QUALITY_BUCKETS", "build_director_quality_v24_metrics", "build_quality_v24_metrics"]
