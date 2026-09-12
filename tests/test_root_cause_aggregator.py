from core.root_cause_aggregator import aggregate_root_causes


def test_aggregator_groups_semantic_symptoms_and_preserves_sources():
    result = aggregate_root_causes([
        {"code": "scene_asset_missing", "severity": "blocked", "scene_id": "S1", "shot_id": "SH1", "message": "missing"},
        {"code": "missing_scene_reference", "severity": "warning", "scene_id": "S1", "shot_id": "SH2", "message": "missing"},
        {"code": "action_overloaded", "severity": "error", "scene_id": "S1", "shot_id": "SH1"},
    ])
    assert result["symptom_count"] == 3
    assert result["root_cause_count"] == 2
    scene_root = next(item for item in result["root_causes"] if item["root_cause_id"] == "RC_SCENE_ASSET_MISSING")
    assert scene_root["severity"] == "blocked"
    assert scene_root["affected_scene_count"] == 1
    assert scene_root["affected_shot_count"] == 2
    assert scene_root["symptom_count"] == 2
    assert len(scene_root["symptoms"]) == 2


def test_aggregator_unknown_codes_are_stable_and_do_not_hide_diagnostics():
    diagnostics = {"checks": [{"code": "new_provider_contract", "severity": "warning", "shot_id": "SH9"}]}
    first = aggregate_root_causes(diagnostics)
    second = aggregate_root_causes(diagnostics)
    assert first["root_causes"][0]["root_cause_id"] == second["root_causes"][0]["root_cause_id"]
    assert first["symptom_count"] == 1
    assert first["symptoms"][0]["code"] == "new_provider_contract"
