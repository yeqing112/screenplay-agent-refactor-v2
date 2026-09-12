from core.shot_plan import build_shot_plan


def test_continuity_contract_is_present_even_when_optional_values_are_unknown():
    plan = build_shot_plan(
        treatment={"scene_name": "门厅", "beat_map": [{"beat_id": "B1", "event": "看向门外"}]},
        blocking={"scene_name": "门厅", "participants": [], "unknowns": []},
    )
    contract = plan["shots"][0]["continuity_contract"]
    assert contract["screen_direction"] == "maintain"
    assert isinstance(contract["eyeline"], dict)
    assert isinstance(contract["prop_state"], dict)

