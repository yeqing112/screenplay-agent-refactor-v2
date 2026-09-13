from core.storyboard_materializer import materialize_storyboard_from_shot_plan


def test_materializer_copies_plan_intent_without_adding_shots():
    plan = {"scene_name": "门厅", "evidence_fingerprint": "fp", "shots": [{"plan_shot_id": "S01", "purpose": "reveal", "event": "人物抬头", "duration_hint_seconds": 4, "camera": {"shot_size": "CU", "angle": "eye_level", "movement": "static", "speed": "slow", "camera_side": "screen_left"}, "entry_state": {"present": True}, "exit_state": {"focus": "door"}, "asset_bindings": {"scene_asset_id": "SC1"}, "continuity_contract": {"screen_direction": "maintain"}}]}
    result = materialize_storyboard_from_shot_plan(plan)
    assert len(result) == 1
    shot = result[0]
    assert shot["plan_shot_id"] == "S01"
    assert shot["duration"] == 4
    assert shot["camera_movement"] == "static"
    assert shot["meta_info"]["camera"] == plan["shots"][0]["camera"]
    assert shot["asset_bindings"]["scene_asset_id"] == "SC1"
    assert shot["meta_info"]["shot_plan_ref"]["plan_shot_id"] == "S01"
