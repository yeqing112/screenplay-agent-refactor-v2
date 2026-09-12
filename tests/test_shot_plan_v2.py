from core.shot_plan import build_shot_plan


def test_shot_plan_v2_materializes_executable_contract():
    plan = build_shot_plan(
        treatment={"scene_name": "门厅", "scene_id": "E01_SC001", "beat_map": [{"beat_id": "B01", "type": "action", "event": "人物推门进入"}]},
        blocking={"scene_name": "门厅", "scene_id": "E01_SC001", "participants": [{"character_id": "c1"}], "unknowns": []},
    )
    shot = plan["shots"][0]
    assert plan["unknowns"] == []
    assert shot["scene_id"] == "E01_SC001"
    assert shot["camera"]["shot_size"]
    assert shot["duration_hint_seconds"] > 0
    assert shot["action_beats"][0]["end_seconds"] <= shot["duration_hint_seconds"]
    assert shot["asset_bindings"]["character_asset_ids"] == ["c1"]
    assert "continuity_contract" in shot

