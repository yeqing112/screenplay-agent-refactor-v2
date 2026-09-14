"""Three-state Shadow Gate for Director Quality V2.3 Phase B."""

from __future__ import annotations

from typing import Any


SHADOW_GATE_SCHEMA_VERSION = "director_quality_v2_3_shadow_gate_v1"
SHADOW_GATE_POLICY_VERSION = "director_quality_v2_4_shadow_gate_policy_v1"
SHADOW_GATE_POLICY = {
    "final_contract_pass_rate": 1.0,
    "director_quality_mean": 80.0,
    "director_quality_median": 85.0,
    "director_quality_p10": 70.0,
    "director_quality_min": 60.0,
    "creative_value_mean": 75.0,
    "useful_creative_acceptance": 0.75,
    "edit_strategy_eligible_coverage": 0.80,
    "emotion_arc_eligible_coverage": 0.85,
    "information_strategy_eligible_coverage": 0.85,
    "over_directing_rate": 0.10,
    "shot_inflation_rate": 0.50,
}
SHOT_INFLATION_CONTROLLED_THRESHOLD = SHADOW_GATE_POLICY["shot_inflation_rate"]


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def get_shadow_gate_policy() -> dict[str, Any]:
    """Return the single authoritative, immutable-by-convention policy."""

    return {"policy_version": SHADOW_GATE_POLICY_VERSION, "thresholds": dict(SHADOW_GATE_POLICY)}


def _failure_reason(code: str, actual: Any, required: Any) -> dict[str, Any]:
    return {"code": code, "actual": actual, "required": required}


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
    policy = SHADOW_GATE_POLICY
    safety_checks = {
        "contract_pass_rate": contract_pass_rate == policy["final_contract_pass_rate"],
        "fact_override_accepted": fact_override_accepted == 0,
        "unknown_root_cause_count": unknown_root_cause_count == 0,
    }
    safety_complete = contract_pass_rate is not None and fact_override_accepted is not None and unknown_root_cause_count is not None
    safety_passed = safety_complete and all(safety_checks.values())
    value_inputs = {
        "director_quality_mean": (director_quality_mean, policy["director_quality_mean"]),
        "director_quality_median": (director_quality_median, policy["director_quality_median"]),
        "director_quality_p10": (director_quality_p10, policy["director_quality_p10"]),
        "director_quality_min": (director_quality_min, policy["director_quality_min"]),
        "creative_value_mean": (creative_value_mean, policy["creative_value_mean"]),
        "useful_creative_acceptance": (useful_creative_acceptance, policy["useful_creative_acceptance"]),
        "edit_strategy_eligible_coverage": (edit_strategy_eligible_coverage, policy["edit_strategy_eligible_coverage"]),
        "emotion_arc_eligible_coverage": (emotion_arc_eligible_coverage, policy["emotion_arc_eligible_coverage"]),
        "information_strategy_eligible_coverage": (information_strategy_eligible_coverage, policy["information_strategy_eligible_coverage"]),
        "over_directing_rate": (over_directing_rate, policy["over_directing_rate"]),
        "shot_inflation_rate": (shot_inflation_rate, policy["shot_inflation_rate"]),
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
    reasons: list[dict[str, Any]] = []
    if contract_pass_rate is None:
        reasons.append(_failure_reason("CONTRACT_PASS_RATE_MISSING", None, policy["final_contract_pass_rate"]))
    elif not safety_checks["contract_pass_rate"]:
        reasons.append(_failure_reason("CONTRACT_PASS_BELOW_THRESHOLD", contract_pass_rate, policy["final_contract_pass_rate"]))
    if fact_override_accepted is None:
        reasons.append(_failure_reason("FACT_OVERRIDE_COUNT_MISSING", None, 0))
    elif not safety_checks["fact_override_accepted"]:
        reasons.append(_failure_reason("FACT_OVERRIDE_ACCEPTED", fact_override_accepted, 0))
    if unknown_root_cause_count is None:
        reasons.append(_failure_reason("UNKNOWN_ROOT_CAUSE_COUNT_MISSING", None, 0))
    elif not safety_checks["unknown_root_cause_count"]:
        reasons.append(_failure_reason("UNKNOWN_ROOT_CAUSE_PRESENT", unknown_root_cause_count, 0))
    for key, (value, threshold) in value_inputs.items():
        number = _number(value)
        if number is None:
            reasons.append(_failure_reason(f"{key.upper()}_MISSING", None, threshold))
        elif not value_checks[key]:
            code = f"{key.upper()}_ABOVE_THRESHOLD" if key in {"over_directing_rate", "shot_inflation_rate"} else f"{key.upper()}_BELOW_THRESHOLD"
            reasons.append(_failure_reason(code, number, threshold))
    return {
        "schema_version": SHADOW_GATE_SCHEMA_VERSION,
        "policy_version": SHADOW_GATE_POLICY_VERSION,
        "status": status,
        "safe_to_shadow": safety_passed,
        "valuable_enough_to_shadow": value_passed,
        "safety": {"passed": safety_passed, "complete": safety_complete, "checks": safety_checks},
        "value": {"passed": value_passed, "checks": value_checks, "missing": missing, "thresholds": {key: threshold for key, (_, threshold) in value_inputs.items()}},
        "reasons": reasons,
        "automatic_shadow_enabled": False,
    }


__all__ = ["SHADOW_GATE_SCHEMA_VERSION", "SHADOW_GATE_POLICY_VERSION", "SHADOW_GATE_POLICY", "SHOT_INFLATION_CONTROLLED_THRESHOLD", "get_shadow_gate_policy", "evaluate_shadow_gate"]
