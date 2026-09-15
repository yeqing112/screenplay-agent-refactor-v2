import importlib.util


def _module():
    spec = importlib.util.spec_from_file_location("shot_canary", "scripts/run_director_quality_v3_shot_architecture_canary.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_single_shot_provider_shape_is_preserved_but_protocol_invalid():
    module = _module()
    row = {"scene_id": "s1", "base": {"strategy_fingerprint": "fp"}, "base_fingerprint": "fp", "inputs": {"scene": {"scene_id": "s1", "beats": [{"beat_id": "1"}]}, "scene_blocking": {"participants": []}, "character_canonical": {"records": []}}}
    raw = '{"phase_id":"P01","beat_refs":["1"],"function":"ESTABLISH","subject":"room","shot_size":"WS","camera_position":"door","camera_movement":"STATIC","composition_intent":"space","performance_focus":"none","information_focus":"room","prop_focus":"none","spatial_anchor":"door","entry_state":"start","exit_state":"hold","cut_in_motivation":"orient","cut_out_motivation":"next","hold_logic":"hold","continuity_requirements":["axis"],"must_preserve_refs":["x"]}'
    result = module._validate(row, raw)
    assert result["draft_ir"]["shot_count"] == 1
    assert result["protocol"]["status"] == "FAIL"
    assert any(e["code"] == "ARCHITECTURE_OUTPUT_SHAPE_INVALID" for e in result["projection"]["errors"])
