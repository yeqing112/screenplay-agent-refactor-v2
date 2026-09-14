"""Conversion funnel metrics for Opportunity → Intervention → Value."""

from __future__ import annotations

import copy
from typing import Any, Iterable


CONVERSION_FUNNEL_SCHEMA_VERSION = "director-quality-v2-4-conversion-funnel-v1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _positive_target_delta(row: dict[str, Any]) -> bool:
    after = _dict(row.get("dimension_delta_after"))
    before = _dict(row.get("dimension_delta_before"))
    if not after:
        return False
    for key, value in after.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        old = before.get(key, 0)
        if isinstance(old, bool) or not isinstance(old, (int, float)):
            old = 0
        if float(value) > float(old):
            return True
    return False


def _rate(numerator: int, denominator: int | None) -> float | None:
    if not denominator:
        return None
    return round(float(numerator) / float(denominator), 4)


def build_conversion_funnel(trace: dict[str, Any] | Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Build stage counts/rates and explicit drop reasons from a trace."""

    rows = _list(trace.get("records")) if isinstance(trace, dict) else list(trace or [])
    rows = [item for item in rows if isinstance(item, dict)]
    eligible_rows = [item for item in rows if bool(item.get("eligible"))]
    act_rows = [item for item in eligible_rows if _text(item.get("planner_decision")).upper() == "ACT"]
    produced_rows = [item for item in act_rows if _list(item.get("patch_ids")) or _list(item.get("auxiliary_proposal_ids"))]
    contract_rows = [item for item in produced_rows if _text(item.get("final_status")) not in {"REJECTED_CONTRACT", "FALLBACK_BASELINE"} and not _list(item.get("rejected_patch_ids"))]
    applied_rows = [item for item in contract_rows if _list(item.get("applied_patch_ids"))]
    improved_rows = [item for item in applied_rows if _positive_target_delta(item)]
    useful_rows = [item for item in improved_rows if _text(item.get("final_status")) == "USEFUL_ACCEPTED" or bool(item.get("useful_accepted"))]
    valid_skip_rows = [item for item in eligible_rows if _text(item.get("planner_decision")).upper() == "SKIP_WITH_REASON" and _text(item.get("final_status")) == "SKIPPED_VALID_REASON"]

    stages = [
        ("eligible_opportunities", eligible_rows),
        ("act", act_rows),
        ("intervention_produced", produced_rows),
        ("contract_passed", contract_rows),
        ("applied", applied_rows),
        ("target_dimension_improved", improved_rows),
        ("useful_accepted", useful_rows),
    ]
    stage_rows: list[dict[str, Any]] = []
    previous_count: int | None = None
    for name, selected in stages:
        count = len(selected)
        stage_rows.append({
            "stage": name,
            "count": count,
            "rate_from_previous": _rate(count, previous_count),
            "rate_from_eligible": _rate(count, len(eligible_rows)),
            "drop_count_from_previous": max(0, (previous_count - count)) if previous_count is not None else 0,
        })
        previous_count = count
    drop_reasons = {
        "not_eligible": len(rows) - len(eligible_rows),
        "not_act": len(eligible_rows) - len(act_rows),
        "no_intervention": len(act_rows) - len(produced_rows),
        "contract_failure": len(produced_rows) - len(contract_rows),
        "not_applied": len(contract_rows) - len(applied_rows),
        "target_dimension_not_improved": len(applied_rows) - len(improved_rows),
        "no_useful_acceptance": len(improved_rows) - len(useful_rows),
    }
    return {
        "schema_version": CONVERSION_FUNNEL_SCHEMA_VERSION,
        "stages": stage_rows,
        "counts": {name: len(selected) for name, selected in stages},
        "drop_reasons": drop_reasons,
        "valid_skip_count": len(valid_skip_rows),
        "valid_skip_rate": _rate(len(valid_skip_rows), len(eligible_rows)),
        "opportunity_address_rate": _rate(len(useful_rows) + len(valid_skip_rows), len(eligible_rows)),
        "trace_record_count": len(rows),
        "trace": copy.deepcopy(rows),
    }


build_intervention_conversion_funnel = build_conversion_funnel


__all__ = ["CONVERSION_FUNNEL_SCHEMA_VERSION", "build_conversion_funnel", "build_intervention_conversion_funnel"]
