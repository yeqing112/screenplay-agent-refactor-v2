"""Opportunity-level ACT/SKIP planner contract.

The existing CreativePatch planner remains responsible for bounded shot
changes.  This module sits one level above it and makes the planner's intent
auditable: every eligible opportunity is either acted on or explicitly
skipped with a reason.
"""

from __future__ import annotations

import copy
from typing import Any, Iterable

from core.director_opportunity_model import OpportunityModelError, normalize_opportunity


PLANNER_DECISION_SCHEMA_VERSION = "director_opportunity_planner_decision_v1"
_DECISION_KEYS = {"schema_version", "opportunity_id", "decision", "strategy", "reason", "evidence_fingerprint"}


class OpportunityPlannerError(ValueError):
    code = "DIRECTOR_OPPORTUNITY_PLANNER_INVALID"

    def __init__(self, message: str, *, code: str | None = None, path: str = "") -> None:
        super().__init__(message)
        self.code = code or self.code
        self.path = path


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _normalize_opportunities(opportunities: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(opportunities):
        try:
            item = normalize_opportunity(raw)
        except OpportunityModelError as exc:
            raise OpportunityPlannerError(f"opportunity[{index}] is invalid: {exc}", code=exc.code, path=f"opportunities[{index}].{exc.path}") from exc
        if item["opportunity_id"] in seen:
            raise OpportunityPlannerError("duplicate opportunity_id", code="OPPORTUNITY_DUPLICATE_ID", path=f"opportunities[{index}].opportunity_id")
        seen.add(item["opportunity_id"])
        result.append(item)
    return result


def _decision_items(raw: Any) -> list[Any]:
    if isinstance(raw, dict):
        unknown = sorted(set(raw) - {"schema_version", "decisions"})
        if unknown:
            raise OpportunityPlannerError(f"planner output contains forbidden fields: {', '.join(unknown)}", code="OPPORTUNITY_PLANNER_FIELD_FORBIDDEN")
        raw = raw.get("decisions")
    if not isinstance(raw, list):
        raise OpportunityPlannerError("planner output must contain a decisions list", path="decisions")
    return raw


def normalize_planner_decisions(raw: Any, opportunities: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate and order decisions against the detector's opportunities.

    Ordering follows opportunity order, not provider order, so downstream
    metrics and audit replay are deterministic.
    """

    normalized_opportunities = _normalize_opportunities(opportunities)
    by_id = {item["opportunity_id"]: item for item in normalized_opportunities}
    items = _decision_items(raw)
    decisions: dict[str, dict[str, Any]] = {}
    for index, value in enumerate(items):
        if not isinstance(value, dict):
            raise OpportunityPlannerError("decision must be an object", path=f"decisions[{index}]")
        unknown = sorted(set(value) - _DECISION_KEYS)
        if unknown:
            raise OpportunityPlannerError(f"decision contains forbidden fields: {', '.join(unknown)}", code="OPPORTUNITY_PLANNER_FIELD_FORBIDDEN", path=f"decisions[{index}]")
        opportunity_id = _text(value.get("opportunity_id"))
        if opportunity_id not in by_id:
            raise OpportunityPlannerError("decision references unknown opportunity", code="OPPORTUNITY_DECISION_UNBOUND", path=f"decisions[{index}].opportunity_id")
        if opportunity_id in decisions:
            raise OpportunityPlannerError("duplicate opportunity decision", code="OPPORTUNITY_DECISION_DUPLICATE", path=f"decisions[{index}].opportunity_id")
        decision = _text(value.get("decision")).upper()
        if decision not in {"ACT", "SKIP_WITH_REASON", "NOT_APPLICABLE"}:
            raise OpportunityPlannerError("decision must be ACT, SKIP_WITH_REASON, or NOT_APPLICABLE", path=f"decisions[{index}].decision")
        opportunity = by_id[opportunity_id]
        if opportunity["eligible"] and decision == "NOT_APPLICABLE":
            raise OpportunityPlannerError("eligible opportunity cannot be NOT_APPLICABLE", path=f"decisions[{index}].decision")
        reason = _text(value.get("reason"))
        strategy = _text(value.get("strategy"))
        if decision == "ACT" and not strategy:
            raise OpportunityPlannerError("ACT requires a strategy", code="OPPORTUNITY_ACT_STRATEGY_REQUIRED", path=f"decisions[{index}].strategy")
        if decision == "SKIP_WITH_REASON" and not reason:
            raise OpportunityPlannerError("SKIP_WITH_REASON requires a reason", code="OPPORTUNITY_SKIP_REASON_REQUIRED", path=f"decisions[{index}].reason")
        decisions[opportunity_id] = {
            "schema_version": PLANNER_DECISION_SCHEMA_VERSION,
            "opportunity_id": opportunity_id,
            "decision": decision,
            "strategy": strategy,
            "reason": reason,
            "evidence_fingerprint": _text(value.get("evidence_fingerprint")),
        }
    missing = [item["opportunity_id"] for item in normalized_opportunities if item["eligible"] and item["opportunity_id"] not in decisions]
    if missing:
        raise OpportunityPlannerError(
            f"eligible opportunities require an explicit decision: {', '.join(missing)}",
            code="OPPORTUNITY_DECISION_MISSING",
            path="decisions",
        )
    return [copy.deepcopy(decisions[item["opportunity_id"]]) for item in normalized_opportunities if item["opportunity_id"] in decisions]


def validate_planner_decisions(raw: Any, opportunities: Iterable[dict[str, Any]]) -> dict[str, Any]:
    try:
        decisions = normalize_planner_decisions(raw, opportunities)
    except OpportunityPlannerError as exc:
        return {"status": "invalid", "errors": [{"code": exc.code, "path": exc.path, "message": str(exc)}], "decisions": []}
    return {"status": "valid", "errors": [], "decisions": decisions}


__all__ = ["PLANNER_DECISION_SCHEMA_VERSION", "OpportunityPlannerError", "normalize_planner_decisions", "validate_planner_decisions"]
