"""Strict acceptance/rollback policy for a targeted Tail Repair."""

from __future__ import annotations

from typing import Any, Iterable


REPAIR_ACCEPTANCE_SCHEMA_VERSION = "director-quality-v2-4-tail-repair-acceptance-v1"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def evaluate_repair_acceptance(
    *,
    before_quality: dict[str, Any],
    after_quality: dict[str, Any],
    target_dimensions: Iterable[str],
    contract_pass: bool,
    fact_override_count: int = 0,
    creative_value_before: float | None = None,
    creative_value_after: float | None = None,
    over_directing_before: float | None = None,
    over_directing_after: float | None = None,
    shot_inflation_before: float | None = None,
    shot_inflation_after: float | None = None,
    structural_blocker_count: int = 0,
    epsilon: float = 0.0,
    major_quality_regression: float = 5.0,
    over_directing_threshold: float = 0.10,
) -> dict[str, Any]:
    """Return acceptance and explicit rollback reasons.

    The target-dimension improvement requirement is independent of overall
    score.  This prevents unrelated score movement from claiming value.
    """

    before_dims = _dict(before_quality.get("dimensions"))
    after_dims = _dict(after_quality.get("dimensions"))
    target = sorted({_text(item) for item in target_dimensions if _text(item)})
    deltas = {dimension: round(float(after_dims.get(dimension, 0)) - float(before_dims.get(dimension, 0)), 4) for dimension in target}
    reasons: list[str] = []
    if not contract_pass:
        reasons.append("CONTRACT_BLOCK")
    if int(fact_override_count or 0) != 0:
        reasons.append("FACT_OVERRIDE")
    if int(structural_blocker_count or 0) != 0:
        reasons.append("NEW_STRUCTURAL_BLOCKER")
    if not any(value > float(epsilon) for value in deltas.values()):
        reasons.append("TARGET_DIMENSION_NOT_IMPROVED")
    before_score = _number(before_quality.get("director_quality_score")) or 0.0
    after_score = _number(after_quality.get("director_quality_score")) or 0.0
    if after_score < before_score - float(major_quality_regression):
        reasons.append("DIRECTOR_QUALITY_REGRESSION")
    if creative_value_before is not None and creative_value_after is not None and creative_value_after < creative_value_before:
        reasons.append("CREATIVE_VALUE_REGRESSION")
    if over_directing_after is not None and over_directing_after > over_directing_threshold and (over_directing_before is None or over_directing_after > over_directing_before):
        reasons.append("OVER_DIRECTING_REGRESSION")
    if shot_inflation_after is not None and shot_inflation_before is not None and shot_inflation_after > shot_inflation_before:
        reasons.append("SHOT_INFLATION_REGRESSION")
    return {
        "schema_version": REPAIR_ACCEPTANCE_SCHEMA_VERSION,
        "accepted": not reasons,
        "target_dimensions": target,
        "target_dimension_deltas": deltas,
        "quality_before": before_score,
        "quality_after": after_score,
        "rollback_reason": ";".join(reasons),
        "reasons": reasons,
    }


accept_tail_repair = evaluate_repair_acceptance


__all__ = ["REPAIR_ACCEPTANCE_SCHEMA_VERSION", "evaluate_repair_acceptance", "accept_tail_repair"]
