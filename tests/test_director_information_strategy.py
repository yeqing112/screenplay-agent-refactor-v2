from core.director_information_strategy import evaluate_information_strategy, validate_information_strategy


def _strategy():
    return {
        "known_to_audience": ["房间有人进入"],
        "withheld_from_audience": ["钥匙属于失踪者"],
        "reveal_plan": [{"beat_id": "B02", "reveals": ["钥匙属于失踪者"], "withholds": [], "audience_should_notice": "钥匙刻字", "audience_should_not_yet_know": "失踪者身份"}],
        "reaction_priority": ["C1"],
        "audience_focus": ["钥匙", "C1的反应"],
    }


def test_information_strategy_v2_requires_explicit_reveal_plan():
    assert validate_information_strategy(_strategy())["status"] == "valid"
    assert validate_information_strategy({"known_to_audience": []})["status"] == "invalid"


def test_information_validator_detects_late_reveal_and_missing_reaction():
    result = evaluate_information_strategy(
        _strategy(),
        shots=[{"beat_id": "B02", "information_strategy": {"reveals": []}, "performance_direction": []}],
        beat_map=[{"beat_id": "B01"}, {"beat_id": "B02"}],
    )
    codes = {item["code"] for item in result["issues"]}
    assert "LATE_REVEAL" in codes


def test_information_validator_accepts_reveal_with_visible_reaction():
    result = evaluate_information_strategy(
        _strategy(),
        shots=[{"beat_id": "B02", "information_strategy": {"reveals": ["钥匙属于失踪者"]}, "performance_direction": [{"visible_behavior": "瞳孔收缩"}]}],
        beat_map=[{"beat_id": "B01"}, {"beat_id": "B02"}],
    )
    assert result["coverage"] == 1.0
    assert not any(item["code"] == "MISSING_REACTION_TO_REVEAL" for item in result["issues"])
