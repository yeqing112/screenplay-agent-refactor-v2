from core.shot_plan import build_shot_plan


def test_shot_plan_binds_declared_scene_and_character_assets_only():
    plan = build_shot_plan(
        treatment={"scene_name": "走廊", "beat_map": [{"beat_id": "B1", "event": "停下"}]},
        blocking={"scene_name": "走廊", "participants": [{"character_id": "CHAR_A"}], "scene_asset_id": "SCENE_A", "props": [{"prop_id": "PROP_A"}], "unknowns": []},
    )
    bindings = plan["shots"][0]["asset_bindings"]
    assert bindings["scene_asset_id"] == "SCENE_A"
    assert bindings["character_asset_ids"] == ["CHAR_A"]
    assert bindings["prop_asset_ids"] == ["PROP_A"]

