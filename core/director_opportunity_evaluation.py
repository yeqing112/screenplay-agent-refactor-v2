"""Opportunity eligibility and planner-outcome accounting.

This module keeps denominators explicit.  A strategy that is not applicable
to a scene is not a missed opportunity, while an emitted eligible opportunity
must eventually receive an explicit planner decision.
"""

from __future__ import annotations

import copy
from collections import defaultdict
from typing import Any, Iterable

from core.director_opportunity_model import (
    DIRECTING_DIMENSIONS,
    OpportunityModelError,
    normalize_opportunity,
    normalize_opportunity_outcome,
)


ELIGIBILITY_SCHEMA_VERSION = "director_opportunity_eligibility_v1"


def _rate(numerator: int, denominator: int) -> float | None:
    return round(float(numerator) / float(denominator), 4) if denominator else None


def _normalized_opportunities(opportunities: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(opportunities):
        try:
            item = normalize_opportunity(raw)
        except OpportunityModelError as exc:
            raise OpportunityModelError(f"opportunities[{index}] is invalid: {exc}", code=exc.code, path=f"opportunities[{index}].{exc.path}") from exc
        if item["opportunity_id"] in seen:
            raise OpportunityModelError("duplicate opportunity_id", code="OPPORTUNITY_DUPLICATE_ID", path=f"opportunities[{index}].opportunity_id")
        seen.add(item["opportunity_id"])
        result.append(item)
    return result


def build_eligibility_metrics(opportunities: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Build explicit eligible/non-applicable denominators without scoring."""

    normalized = _normalized_opportunities(opportunities)
    eligible = [item for item in normalized if item["eligible"]]
    non_applicable = [item for item in normalized if not item["eligible"]]
    by_type: dict[str, dict[str, int | float | None]] = defaultdict(lambda: {"eligible_count": 0, "non_applicable_count": 0, "eligible_rate": None})
    by_dimension: dict[str, dict[str, int | float | None]] = defaultdict(lambda: {"eligible_count": 0, "non_applicable_count": 0, "eligible_rate": None})
    for item in normalized:
        bucket = by_type[item["type"]]
        bucket["eligible_count" if item["eligible"] else "non_applicable_count"] += 1
        for dimension in item["recommended_directing_dimensions"]:
            dim_bucket = by_dimension[dimension]
            dim_bucket["eligible_count" if item["eligible"] else "non_applicable_count"] += 1
    for bucket in list(by_type.values()) + list(by_dimension.values()):
        denominator = int(bucket["eligible_count"]) + int(bucket["non_applicable_count"])
        bucket["eligible_rate"] = _rate(int(bucket["eligible_count"]), denominator)
    return {
        "schema_version": ELIGIBILITY_SCHEMA_VERSION,
        "total_opportunity_records": len(normalized),
        "eligible_opportunity_count": len(eligible),
        "non_applicable_opportunity_count": len(non_applicable),
        "eligible_rate": _rate(len(eligible), len(normalized)),
        "eligible_opportunity_ids": [item["opportunity_id"] for item in eligible],
        "non_applicable_opportunity_ids": [item["opportunity_id"] for item in non_applicable],
        "by_type": dict(sorted(by_type.items())),
        "by_dimension": {key: dict(value) for key, value in sorted(by_dimension.items()) if key in DIRECTING_DIMENSIONS},
    }


def build_planner_outcome_metrics(
    opportunities: Iterable[dict[str, Any]], outcomes: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Account ACT/SKIP outcomes against eligible opportunities.

    Value acceptance is intentionally not calculated here; this function only
    checks decision completeness and classifies silent misses.  UCA V2 is a
    later, quality-aware stage.
    """

    normalized = _normalized_opportunities(opportunities)
    by_id = {item["opportunity_id"]: item for item in normalized}
    normalized_outcomes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(outcomes):
        try:
            outcome = normalize_opportunity_outcome(raw)
        except OpportunityModelError as exc:
            raise OpportunityModelError(f"outcomes[{index}] is invalid: {exc}", code=exc.code, path=f"outcomes[{index}].{exc.path}") from exc
        if outcome["opportunity_id"] not in by_id:
            raise OpportunityModelError("outcome references unknown opportunity", code="OPPORTUNITY_OUTCOME_UNBOUND", path=f"outcomes[{index}].opportunity_id")
        if outcome["opportunity_id"] in seen:
            raise OpportunityModelError("duplicate opportunity outcome", code="OPPORTUNITY_OUTCOME_DUPLICATE", path=f"outcomes[{index}].opportunity_id")
        if outcome["eligible"] != by_id[outcome["opportunity_id"]]["eligible"]:
            raise OpportunityModelError("outcome eligibility disagrees with opportunity evidence", code="OPPORTUNITY_ELIGIBILITY_DRIFT", path=f"outcomes[{index}].eligible")
        seen.add(outcome["opportunity_id"])
        normalized_outcomes.append(outcome)
    eligible = [item for item in normalized if item["eligible"]]
    eligible_ids = {item["opportunity_id"] for item in eligible}
    outcome_by_id = {item["opportunity_id"]: item for item in normalized_outcomes}
    acts = [item for item in normalized_outcomes if item["opportunity_id"] in eligible_ids and item["planner_decision"] == "ACT"]
    valid_skips = [item for item in normalized_outcomes if item["opportunity_id"] in eligible_ids and item["planner_decision"] == "SKIP_WITH_REASON" and item["final_status"] == "SKIPPED_VALID_REASON"]
    silent_misses = [item for item in eligible if item["opportunity_id"] not in outcome_by_id]
    invalid_skips = [item for item in normalized_outcomes if item["opportunity_id"] in eligible_ids and item["planner_decision"] == "SKIP_WITH_REASON" and item["final_status"] != "SKIPPED_VALID_REASON"]
    handled = len(acts) + len(valid_skips)
    return {
        "schema_version": "director_opportunity_planner_outcomes_v1",
        "eligible_opportunity_count": len(eligible),
        "acted_opportunity_count": len(acts),
        "valid_skip_count": len(valid_skips),
        "missed_opportunity_count": len(silent_misses),
        "invalid_skip_count": len(invalid_skips),
        "eligible_handled_count": handled,
        "eligible_handled_rate": _rate(handled, len(eligible)),
        "valid_skip_rate": _rate(len(valid_skips), len(eligible)),
        "missed_opportunity_rate": _rate(len(silent_misses), len(eligible)),
        "opportunity_outcomes": copy.deepcopy(normalized_outcomes),
        "silent_missed_opportunity_ids": [item["opportunity_id"] for item in silent_misses],
    }


__all__ = ["ELIGIBILITY_SCHEMA_VERSION", "build_eligibility_metrics", "build_planner_outcome_metrics"]
