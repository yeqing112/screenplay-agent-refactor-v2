"""Value-aware evaluation for Phase B creative interventions."""

from __future__ import annotations

import copy
from typing import Any, Iterable

from core.director_opportunity_model import build_opportunity_outcome, normalize_opportunity
from core.director_opportunity_planner import normalize_planner_decisions


CREATIVE_VALUE_SCHEMA_VERSION = "director_useful_creative_acceptance_v2"


def _rate(numerator: int, denominator: int) -> float | None:
    return round(float(numerator) / float(denominator), 4) if denominator else None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalized_opportunities(opportunities: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [normalize_opportunity(item) for item in opportunities]


def evaluate_useful_creative_acceptance(
    *,
    opportunities: Iterable[dict[str, Any]],
    decisions: Iterable[dict[str, Any]] | dict[str, Any],
    interventions: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Evaluate opportunity outcomes without treating valid skips as misses.

    ``interventions`` are post-compiler facts supplied by the caller.  This
    function never infers patch legality or quality deltas from text; absent
    evidence is a fail-closed outcome rather than a useful acceptance.
    """

    normalized = _normalized_opportunities(opportunities)
    planner_decisions = normalize_planner_decisions(decisions, normalized)
    decision_by_id = {item["opportunity_id"]: item for item in planner_decisions}
    intervention_by_id: dict[str, dict[str, Any]] = {}
    for item in interventions:
        if not isinstance(item, dict):
            continue
        opportunity_id = _text(item.get("opportunity_id"))
        if opportunity_id and opportunity_id not in intervention_by_id:
            intervention_by_id[opportunity_id] = copy.deepcopy(item)

    outcomes: list[dict[str, Any]] = []
    for opportunity in normalized:
        opportunity_id = opportunity["opportunity_id"]
        if not opportunity["eligible"]:
            decision = decision_by_id.get(opportunity_id, {"decision": "NOT_APPLICABLE", "reason": ""})
            outcomes.append(build_opportunity_outcome(opportunity=opportunity, planner_decision=decision["decision"], decision_reason=_text(decision.get("reason")), final_status="SKIPPED_VALID_REASON"))
            continue
        decision = decision_by_id.get(opportunity_id)
        if decision is None:
            outcomes.append(build_opportunity_outcome(opportunity=opportunity, planner_decision="SKIP_WITH_REASON", decision_reason="未收到显式决策", final_status="MISSED_OPPORTUNITY"))
            continue
        if decision["decision"] == "SKIP_WITH_REASON":
            outcomes.append(build_opportunity_outcome(opportunity=opportunity, planner_decision="SKIP_WITH_REASON", decision_reason=decision.get("reason", ""), final_status="SKIPPED_VALID_REASON"))
            continue
        if decision["decision"] != "ACT":
            outcomes.append(build_opportunity_outcome(opportunity=opportunity, planner_decision=decision["decision"], decision_reason=decision.get("reason", ""), final_status="MISSED_OPPORTUNITY"))
            continue
        intervention = intervention_by_id.get(opportunity_id)
        if not intervention:
            outcomes.append(build_opportunity_outcome(opportunity=opportunity, planner_decision="ACT", final_status="FALLBACK_BASELINE", fallback=True))
            continue
        patch_valid = intervention.get("patch_valid") is True
        applied = intervention.get("applied") is True
        fact_contract_pass = intervention.get("fact_contract_pass") is True
        new_blocker = intervention.get("new_blocker") is True
        quality_delta = intervention.get("quality_delta", 0.0)
        dimension_deltas = _dict(intervention.get("dimension_deltas"))
        try:
            positive_delta = float(quality_delta) > 0 and any(isinstance(value, (int, float)) and not isinstance(value, bool) and float(value) > 0 for value in dimension_deltas.values())
        except (TypeError, ValueError):
            positive_delta = False
            quality_delta = 0.0
        if not patch_valid or not fact_contract_pass:
            status = "REJECTED_CONTRACT"
        elif not applied:
            status = "FALLBACK_BASELINE"
        elif new_blocker:
            status = "REJECTED_QUALITY"
        elif positive_delta:
            status = "USEFUL_ACCEPTED"
        else:
            status = "ACCEPTED_NO_MEASURABLE_VALUE"
        outcomes.append(build_opportunity_outcome(opportunity=opportunity, planner_decision="ACT", accepted=status == "USEFUL_ACCEPTED", repaired=bool(intervention.get("repaired")), fallback=status == "FALLBACK_BASELINE", quality_delta=quality_delta if isinstance(quality_delta, (int, float)) and not isinstance(quality_delta, bool) else 0.0, dimension_deltas=dimension_deltas, final_status=status))

    eligible_outcomes = [item for item in outcomes if item["eligible"]]
    useful = [item for item in eligible_outcomes if item["final_status"] == "USEFUL_ACCEPTED"]
    accepted = [item for item in eligible_outcomes if item["accepted"]]
    valid_skips = [item for item in eligible_outcomes if item["final_status"] == "SKIPPED_VALID_REASON"]
    missed = [item for item in eligible_outcomes if item["final_status"] == "MISSED_OPPORTUNITY"]
    return {
        "schema_version": CREATIVE_VALUE_SCHEMA_VERSION,
        "eligible_opportunity_count": len(eligible_outcomes),
        "useful_accepted_count": len(useful),
        "accepted_count": len(accepted),
        "accepted_no_measurable_value_count": sum(item["final_status"] == "ACCEPTED_NO_MEASURABLE_VALUE" for item in eligible_outcomes),
        "rejected_contract_count": sum(item["final_status"] == "REJECTED_CONTRACT" for item in eligible_outcomes),
        "rejected_quality_count": sum(item["final_status"] == "REJECTED_QUALITY" for item in eligible_outcomes),
        "fallback_baseline_count": sum(item["final_status"] == "FALLBACK_BASELINE" for item in eligible_outcomes),
        "valid_skip_count": len(valid_skips),
        "missed_opportunity_count": len(missed),
        "useful_creative_acceptance_rate": _rate(len(useful), len(eligible_outcomes)),
        "valid_skip_rate": _rate(len(valid_skips), len(eligible_outcomes)),
        "missed_opportunity_rate": _rate(len(missed), len(eligible_outcomes)),
        "outcomes": outcomes,
    }


__all__ = ["CREATIVE_VALUE_SCHEMA_VERSION", "evaluate_useful_creative_acceptance"]
