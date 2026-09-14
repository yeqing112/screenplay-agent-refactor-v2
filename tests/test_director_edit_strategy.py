from core.director_edit_strategy import evaluate_edit_strategy, validate_edit_strategy


def _edit(**extra):
    value = {"cut_reason": "reaction_complete", "hold_after_reveal_seconds": 0.4, "rhythm_change": "hold"}
    value.update(extra)
    return value


def test_edit_strategy_v2_requires_structured_cut_reason():
    assert validate_edit_strategy({"hold_after_reveal_seconds": 0.4})["status"] == "invalid"
    assert validate_edit_strategy(_edit())["status"] == "valid"


def test_edit_validator_detects_missing_motivation_reaction_timing_and_flatline():
    result = evaluate_edit_strategy([
        {"plan_shot_id": "S01", "edit": _edit(cut_reason="coverage", reaction_timing="before", duration_seconds=4)},
        {"plan_shot_id": "S02", "edit": _edit(duration_seconds=4)},
    ])
    codes = {item["code"] for item in result["issues"]}
    assert {"UNMOTIVATED_CUT", "REACTION_CUT_TOO_EARLY", "RHYTHM_FLATLINE"} <= codes
    assert result["coverage"] == 1.0


def test_edit_validator_checks_scene_button_and_controlled_cut_rates():
    missing = evaluate_edit_strategy([
        {"plan_shot_id": "S01", "edit": _edit(duration_seconds=10)},
        {"plan_shot_id": "S02", "edit": _edit(duration_seconds=10)},
    ], scene_button_required=True)
    assert any(item["code"] == "SCENE_BUTTON_MISSING" for item in missing["issues"])
    over = evaluate_edit_strategy([
        {"plan_shot_id": f"S{i:02d}", "edit": _edit(duration_seconds=1)} for i in range(1, 5)
    ], scene_duration_seconds=1.5)
    assert any(item["code"] == "OVER_CUTTING" for item in over["issues"])
