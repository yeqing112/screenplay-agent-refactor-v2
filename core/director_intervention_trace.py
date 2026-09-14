"""Opportunity-to-value intervention trace for Director Quality V2.4."""

from __future__ import annotations

import copy
from collections import Counter
from typing import Any, Iterable

from core.director_opportunity_model import normalize_opportunity


INTERVENTION_TRACE_SCHEMA_VERSION = "director_opportunity_intervention_trace_v1"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _records(value: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _list(value):
        if not isinstance(item, dict):
            continue
        if any(_text(item.get(key)) for key in keys):
            rows.append(item)
    return rows


def _id_for_patch(patch: dict[str, Any], index: int) -> str:
    return _text(patch.get("patch_id")) or f"patch:{_text(patch.get('plan_shot_id')) or index + 1}"


def _patch_ids_for_opportunity(opportunity: dict[str, Any], decision: dict[str, Any], patches: list[dict[str, Any]]) -> list[str]:
    explicit = [_text(item) for item in _list(decision.get("patch_ids")) if _text(item)]
    if explicit:
        return explicit
    opportunity_id = _text(opportunity.get("opportunity_id"))
    result: list[str] = []
    for index, patch in enumerate(patches):
        refs = [_text(item) for item in _list(patch.get("opportunity_ids") or patch.get("opportunity_refs")) if _text(item)]
        if opportunity_id in refs or opportunity_id in [_text(item) for item in _list(patch.get("strategy_refs"))]:
            result.append(_id_for_patch(patch, index))
    return result


def _auxiliary_ids_for_opportunity(decision: dict[str, Any], auxiliary: list[dict[str, Any]]) -> list[str]:
    explicit = [_text(item) for item in _list(decision.get("auxiliary_proposal_ids")) if _text(item)]
    if explicit:
        return explicit
    refs = {_text(item) for item in _list(decision.get("opportunity_ids") or decision.get("opportunity_refs")) if _text(item)}
    return [_text(item.get("proposal_id")) for item in auxiliary if _text(item.get("proposal_id")) and _text(item.get("opportunity_id")) in refs]


def _lookup_by_id(rows: Iterable[dict[str, Any]], ids: set[str], *, fallback_keys: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        row_id = _text(row.get("patch_id") or row.get("proposal_id") or row.get("id"))
        if not row_id:
            row_id = _text(row.get("plan_shot_id"))
        if row_id in ids or any(_text(row.get(key)) in ids for key in fallback_keys):
            result.append(copy.deepcopy(row))
    return result


def build_intervention_trace(
    *,
    opportunities: Iterable[dict[str, Any]],
    planner_decisions: Iterable[dict[str, Any]] | None = None,
    strategy: dict[str, Any] | None = None,
    patch_document: dict[str, Any] | None = None,
    compilation: dict[str, Any] | None = None,
    validation: dict[str, Any] | None = None,
    applied_patch_ids: Iterable[str] | None = None,
    rejected_patch_ids: Iterable[str] | None = None,
    repair_attempt_ids: Iterable[str] | None = None,
    dimension_deltas_before: dict[str, dict[str, float]] | None = None,
    dimension_deltas_after: dict[str, dict[str, float]] | None = None,
    final_statuses: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a complete, replayable trace without inventing associations."""

    normalized = [normalize_opportunity(item) for item in opportunities]
    decision_rows = _records(planner_decisions, ("opportunity_id",))
    decisions = {_text(item.get("opportunity_id")): item for item in decision_rows}
    patch_rows = _records(_dict(patch_document).get("patches"), ("plan_shot_id", "patch_id"))
    auxiliary_rows = _records(_dict(patch_document).get("auxiliary_shot_proposals"), ("proposal_id",))
    compiled_rows = _records(_dict(compilation).get("compiled_patches"), ("plan_shot_id", "patch_id"))
    rejected_rows = _records(_dict(compilation).get("rejected_patches"), ("plan_shot_id", "target_id", "patch_id"))
    validation_rows = _records(_dict(validation).get("errors"), ("target_id", "plan_shot_id", "path"))
    applied = {_text(item) for item in (applied_patch_ids or []) if _text(item)}
    rejected = {_text(item) for item in (rejected_patch_ids or []) if _text(item)}
    repairs = [_text(item) for item in (repair_attempt_ids or []) if _text(item)]
    before = dimension_deltas_before or {}
    after = dimension_deltas_after or {}
    statuses = final_statuses or {}
    traces: list[dict[str, Any]] = []
    for opportunity in normalized:
        oid = opportunity["opportunity_id"]
        decision = decisions.get(oid, {})
        planner_decision = _text(decision.get("planner_decision") or decision.get("decision")).upper()
        patch_ids = _patch_ids_for_opportunity(opportunity, decision, patch_rows)
        auxiliary_ids = _auxiliary_ids_for_opportunity(decision, auxiliary_rows)
        patch_set = set(patch_ids)
        compile_results = _lookup_by_id(compiled_rows, patch_set, fallback_keys=("plan_shot_id",))
        rejected_results = _lookup_by_id(rejected_rows, patch_set, fallback_keys=("plan_shot_id", "target_id"))
        validation_results = _lookup_by_id(validation_rows, patch_set, fallback_keys=("target_id", "plan_shot_id"))
        if planner_decision == "SKIP_WITH_REASON":
            status = "SKIPPED_VALID_REASON" if _text(decision.get("decision_reason") or decision.get("reason")) else "REJECTED_QUALITY"
        elif planner_decision != "ACT":
            status = "MISSED_OPPORTUNITY" if opportunity["eligible"] else "NOT_APPLICABLE"
        elif rejected_results or any(_text(item) in rejected for item in patch_ids):
            status = "REJECTED_CONTRACT"
        elif not patch_ids and not auxiliary_ids:
            status = "REJECTED_QUALITY"
        elif any(_text(item) in applied for item in patch_ids):
            status = "APPLIED_PENDING_MEASURE"
        else:
            status = "INTERVENTION_PRODUCED"
        status = _text(statuses.get(oid)) or status
        traces.append({
            "opportunity_id": oid,
            "eligible": bool(opportunity["eligible"]),
            "type": opportunity["type"],
            "beat_id": opportunity["beat_id"],
            "planner_decision": planner_decision or "MISSING",
            "strategy_id": _text(decision.get("strategy_id") or decision.get("strategy_ref")),
            "strategy": _text(decision.get("strategy")),
            "patch_ids": patch_ids,
            "auxiliary_proposal_ids": auxiliary_ids,
            "compile_results": compile_results,
            "validation_results": validation_results + rejected_results,
            "applied_patch_ids": [item for item in patch_ids if item in applied],
            "rejected_patch_ids": [item for item in patch_ids if item in rejected] or [_id_for_patch(item, index) for index, item in enumerate(rejected_results)],
            "repair_attempt_ids": copy.deepcopy(repairs if planner_decision == "ACT" and patch_ids else []),
            "affected_dimensions": copy.deepcopy(opportunity["recommended_directing_dimensions"]),
            "dimension_delta_before": copy.deepcopy(before.get(oid) or {}),
            "dimension_delta_after": copy.deepcopy(after.get(oid) or {}),
            "final_status": status,
        })
    counts = Counter(_text(item["final_status"]) for item in traces)
    return {
        "schema_version": INTERVENTION_TRACE_SCHEMA_VERSION,
        "records": traces,
        "summary": {key: int(value) for key, value in sorted(counts.items())},
        "eligible_count": sum(1 for item in normalized if item["eligible"]),
        "trace_complete": all(_text(item.get("opportunity_id")) and _text(item.get("final_status")) for item in traces),
        "strategy_snapshot": copy.deepcopy(_dict(strategy)),
    }


# Friendly aliases for runtime and replay callers.
build_opportunity_intervention_trace = build_intervention_trace
trace_opportunity_intervention = build_intervention_trace


__all__ = [
    "INTERVENTION_TRACE_SCHEMA_VERSION",
    "build_intervention_trace",
    "build_opportunity_intervention_trace",
    "trace_opportunity_intervention",
]
