from core.director_opportunity_detector import detect_creative_opportunities


def _evidence():
    return {
        "script_scene": {"scene_id": "SCENE_01", "state_out": {"location": "door"}},
        "treatment": {
            "scene_id": "SCENE_01",
            "beat_map": [
                {"beat_id": "B01", "type": "setup", "event": "两人进入房间", "participants": ["C1", "C2"]},
                {"beat_id": "B02", "type": "reveal", "event": "C1发现钥匙", "participants": ["C1"], "information_change": "钥匙属于失踪者", "emotion_change": "警觉"},
            ],
        },
        "blocking": {"scene_id": "SCENE_01", "participants": ["C1", "C2"]},
        "structural_shot_plan": {
            "scene_id": "SCENE_01",
            "shots": [
                {"plan_shot_id": "S01", "beat_id": "B01", "participants": ["C1", "C2"], "duration_hint_seconds": 4},
                {"plan_shot_id": "S02", "beat_id": "B02", "participants": ["C1"], "duration_hint_seconds": 2.5, "asset_bindings": {"prop_asset_ids": ["PROP_KEY"]}, "composition": {"frame_relationship": "isolated"}},
            ],
        },
    }


def test_detector_emits_only_evidence_backed_opportunities():
    opportunities = detect_creative_opportunities(**_evidence())
    types = {item["type"] for item in opportunities}
    assert "OPP_INFORMATION_REVEAL" in types
    assert "OPP_EMOTION_TURN" in types
    assert "OPP_PROP_EMPHASIS" in types
    assert all(item["eligible"] is True for item in opportunities)
    assert all(item["evidence_refs"] and item["reason"] for item in opportunities)
    assert all(item["scene_id"] == "SCENE_01" for item in opportunities)


def test_detector_does_not_invent_opportunities_without_beats_or_scene_identity():
    assert detect_creative_opportunities(script_scene={"scene_id": "SCENE_01"}, treatment={"scene_id": "SCENE_01"}) == []
    try:
        detect_creative_opportunities(treatment={"beat_map": [{"beat_id": "B01", "type": "reveal"}]})
    except ValueError as exc:
        assert "scene_id" in str(exc)
    else:
        raise AssertionError("missing scene identity must fail closed")


def test_detector_keeps_opportunity_ids_unique_when_multiple_rules_match_one_beat():
    opportunities = detect_creative_opportunities(**_evidence())
    ids = [item["opportunity_id"] for item in opportunities]
    assert len(ids) == len(set(ids))
