from core.prompt_ir_compiler import compile_phase_a, verbalize_phase_b_deterministic


def test_deterministic_verbalizer_does_not_call_external_model():
    phase_a = compile_phase_a({"shot_id": 1, "scene_name": "走廊", "duration": 4, "camera_angle": "CU", "camera_movement": "static", "action_process": "抬头", "action_beats": [{"description": "抬头"}]})
    result = verbalize_phase_b_deterministic(phase_a)
    assert "走廊" in result["static_prompt"]
    assert "抬头" in result["motion_prompt"]
    assert "不新增" in result["negative_prompt"]

