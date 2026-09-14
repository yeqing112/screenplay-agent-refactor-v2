from core.director_shadow_gate import evaluate_shadow_gate


def _kwargs(**overrides):
    value = {
        "contract_pass_rate": 1.0, "fact_override_accepted": 0, "unknown_root_cause_count": 0,
        "director_quality_mean": 82, "director_quality_median": 87, "director_quality_p10": 72, "director_quality_min": 62,
        "creative_value_mean": 78, "creative_value_median": 80, "useful_creative_acceptance": 0.8,
        "edit_strategy_eligible_coverage": 0.82, "emotion_arc_eligible_coverage": 0.86, "information_strategy_eligible_coverage": 0.86,
        "over_directing_rate": 0.05, "shot_inflation_rate": 0.2,
    }
    value.update(overrides)
    return value


def test_shadow_gate_returns_valuable_only_when_safety_and_all_value_thresholds_pass():
    result = evaluate_shadow_gate(**_kwargs())
    assert result["status"] == "VALUABLE_ENOUGH_TO_SHADOW"
    assert result["automatic_shadow_enabled"] is False


def test_shadow_gate_distinguishes_safe_but_not_valuable():
    result = evaluate_shadow_gate(**_kwargs(useful_creative_acceptance=0.2, director_quality_p10=50))
    assert result["status"] == "SAFE_BUT_NOT_VALUABLE"
    assert result["safe_to_shadow"] is True


def test_shadow_gate_is_not_ready_when_safety_fails_or_data_missing():
    failed = evaluate_shadow_gate(**_kwargs(contract_pass_rate=0.9))
    missing = evaluate_shadow_gate(**_kwargs(creative_value_mean=None))
    assert failed["status"] == "NOT_READY"
    assert missing["status"] == "SAFE_BUT_NOT_VALUABLE"
    assert "creative_value_mean" in missing["value"]["missing"]


def test_not_ready_gate_emits_structured_reasons_from_policy():
    result = evaluate_shadow_gate(**_kwargs(contract_pass_rate=0.9, director_quality_mean=70))
    assert result["status"] == "NOT_READY"
    codes = {item["code"] for item in result["reasons"]}
    assert "CONTRACT_PASS_BELOW_THRESHOLD" in codes
    assert "DIRECTOR_QUALITY_MEAN_BELOW_THRESHOLD" in codes
    assert result["policy_version"]
