from core.executability import build_executability_repair_plan, preflight_shot_plan


def test_shot_plan_preflight_blocks_overloaded_short_shot_and_routes_repair():
    result = preflight_shot_plan([{
        "plan_shot_id": "S01", "duration_hint_seconds": 4,
        "event": "扫码支付。随后掏出照片。然后推到对方面前。她抬眼凝视。",
        "action_beats": [], "camera": {"movement": "static"}, "entry_state": {"x": 1}, "exit_state": {"x": 2},
    }])
    assert result["status"] == "blocked"
    repair = build_executability_repair_plan(result)
    assert repair["operations"][0]["target_layer"] == "SHOT_PLAN"
    assert repair["operations"][0]["operation"] == "split_shot"


def test_preflight_allows_single_action_and_returns_pass():
    result = preflight_shot_plan([{"plan_shot_id": "S01", "duration_hint_seconds": 4, "event": "人物进入", "camera": {"movement": "static"}, "entry_state": {"present": False}, "exit_state": {"present": True}}])
    assert result["status"] == "pass"

