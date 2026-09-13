from core.director_repair_prompt import build_director_repair_prompt


def test_repair_prompt_has_stable_prefix_and_variable_tail_hashes():
    first = build_director_repair_prompt({"target": {"plan_shot_id": "S01", "path": "camera.angle"}, "issue": "A"})
    second = build_director_repair_prompt({"target": {"plan_shot_id": "S02", "path": "camera.angle"}, "issue": "B"})
    assert first["system_prompt"] == second["system_prompt"]
    assert first["stable_prefix_hash"] == second["stable_prefix_hash"]
    assert first["stable_prefix_length"] > 0
    assert first["variable_tail_hash"] != second["variable_tail_hash"]
    assert "camera.angle" in first["user_prompt"]
