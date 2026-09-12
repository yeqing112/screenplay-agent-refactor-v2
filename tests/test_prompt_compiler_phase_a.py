from core.prompt_ir_compiler import compile_phase_a, validate_phase_a_state


def test_phase_a_is_deterministic_and_contains_required_state():
    state = compile_phase_a({"shot_id": 1, "scene_name": "门厅", "duration": 4, "camera_angle": "MS", "camera_movement": "static", "action_process": "人物进入", "action_beats": [{"description": "人物进入"}], "start_state": "门外", "end_state": "门内", "asset_bindings": {"scene": {"asset_id": "SC1"}}})
    assert state["phase_a_status"] == "pass"
    assert validate_phase_a_state(state)["status"] == "pass"
    assert state["compiler_fingerprint"]
    assert state["executability"]["status"] == "pass"


def test_phase_a_blocks_missing_core_action():
    state = compile_phase_a({"shot_id": 1, "scene_name": "门厅", "duration": 4})
    assert state["phase_a_status"] == "blocked"
    assert any(item["code"] == "CORE_ACTION_REQUIRED" for item in state["compiler_diagnostics"]["errors"])

