"""Three-state Shadow Gate for Director Quality V2.3 Phase B."""

from __future__ import annotations

from typing import Any


SHADOW_GATE_SCHEMA_VERSION = "director_quality_v2_3_shadow_gate_v1"
SHOT_INFLATION_CONTROLLED_THRESHOLD = 0.5


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def evaluate_shadow_gate(
    *,
    contract_pass_rate: float | None,
    fact_override_accepted: int | None,
    unknown_root_cause_count: int | None,
    director_quality_mean: float | None,
    director_quality_median: float | None,
    director_quality_p10: float | None,
    director_quality_min: float | None,
    creative_value_mean: float | None,
    creative_value_median: float | None,
    useful_creative_acceptance: float | None,
    edit_strategy_eligible_coverage: float | None,
    emotion_arc_eligible_coverage: float | None,
    information_strategy_eligible_coverage: float | None,
    over_directing_rate: float | None,
    shot_inflation_rate: float | None,
) -> dict[str, Any]:
    safety_checks = {
        "contract_pass_rate": contract_pass_rate == 1.0,
        "fact_override_accepted": fact_override_accepted == 0,
        "unknown_root_cause_count": unknown_root_cause_count == 0,
    }
    safety_complete = contract_pass_rate is not None and fact_override_accepted is not None and unknown_root_cause_count is not None
    safety_passed = safety_complete and all(safety_checks.values())
    value_inputs = {
        "director_quality_mean": (director_quality_mean, 80.0),
        "director_quality_median": (director_quality_median, 85.0),
        "director_quality_p10": (director_quality_p10, 70.0),
        "director_quality_min": (director_quality_min, 60.0),
        "creative_value_mean": (creative_value_mean, 75.0),
        "useful_creative_acceptance": (useful_creative_acceptance, 0.75),
        "edit_strategy_eligible_coverage": (edit_strategy_eligible_coverage, 0.80),
        "emotion_arc_eligible_coverage": (emotion_arc_eligible_coverage, 0.85),
        "information_strategy_eligible_coverage": (information_strategy_eligible_coverage, 0.85),
        "over_directing_rate": (over_directing_rate, 0.10),
        "shot_inflation_rate": (shot_inflation_rate, SHOT_INFLATION_CONTROLLED_THRESHOLD),
    }
    value_checks: dict[str, bool] = {}
    missing: list[str] = []
    for key, (value, threshold) in value_inputs.items():
        number = _number(value)
        if number is None:
            missing.append(key)
            value_checks[key] = False
        elif key in {"over_directing_rate", "shot_inflation_rate"}:
            value_checks[key] = number <= threshold
        else:
            value_checks[key] = number >= threshold
    value_passed = safety_passed and not missing and all(value_checks.values())
    if value_passed:
        status = "VALUABLE_ENOUGH_TO_SHADOW"
    elif safety_passed:
        status = "SAFE_BUT_NOT_VALUABLE"
    else:
        status = "NOT_READY"
    return {
        "schema_version": SHADOW_GATE_SCHEMA_VERSION,
        "status": status,
        "safe_to_shadow": safety_passed,
        "valuable_enough_to_shadow": value_passed,
        "safety": {"passed": safety_passed, "complete": safety_complete, "checks": safety_checks},
        "value": {"passed": value_passed, "checks": value_checks, "missing": missing, "thresholds": {key: threshold for key, (_, threshold) in value_inputs.items()}},
        "automatic_shadow_enabled": False,
    }


__all__ = ["SHADOW_GATE_SCHEMA_VERSION", "SHOT_INFLATION_CONTROLLED_THRESHOLD", "evaluate_shadow_gate"]
