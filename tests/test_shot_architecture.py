from core.shot_architecture import (
    compare_architectures,
    normalize_architecture_ir,
    transition_graph,
    validate_content_constraints,
    validate_coverage,
    validate_information,
    validate_protocol,
    validate_spatial,
    validate_topology,
)


def _scene():
    return {"scene_id": "s1", "beats": [{"beat_id": "1"}, {"beat_id": "2"}, {"beat_id": "3"}], "characters": {"records": [{"character_id": "C1"}, {"character_id": "C2"}]}}


def _strategy():
    return {"scene_id": "s1", "scene_phases": [{"phase_id": "P01", "beat_ids": ["1", "2"]}, {"phase_id": "P02", "beat_ids": ["3"]}], "must_preserve": ["red door"], "must_avoid": ["reveal identity"]}


def _shot(beat, phase="P01", function="OBSERVE", subject="character:C1", info="observe"):
    return {"phase_id": phase, "beat_refs": [beat], "function": function, "subject": subject, "shot_size": "MS", "camera_position": "door axis", "camera_movement": "STATIC", "composition_intent": "hold the doorway", "performance_focus": "C1 watches", "information_focus": info, "prop_focus": "none", "spatial_anchor": "door", "entry_state": "in position", "exit_state": "holds", "cut_in_motivation": "orient attention", "cut_out_motivation": "new information", "hold_logic": "hold for pressure", "continuity_requirements": ["screen direction"], "must_preserve_refs": ["red door"]}


def test_one_beat_multiple_shots_and_multiple_beats_one_shot_are_valid():
    raw = {"scene_id": "s1", "architecture_summary": "建立门口关系。随后压力推进。最后收束。", "shots": [_shot("1"), _shot("1", function="REACTION", subject="character:C2", info="reaction"), _shot("2", function="PRESSURE"), _shot("3", "P02", "REVEAL")]}
    ir = normalize_architecture_ir(raw, scene_id="s1", strategy_fingerprint="fp")["ir"]
    assert validate_protocol(ir, scene=_scene(), strategy=_strategy())["valid"]
    assert validate_coverage(ir, _strategy(), _scene())["status"] == "PASS"


def test_duplicate_unknown_and_constraint_failures_are_detected():
    bad = _shot("9"); bad["information_focus"] = "reveal identity"
    raw = {"scene_id": "s1", "architecture_summary": "x。y。z。", "shots": [bad]}
    ir = normalize_architecture_ir(raw, scene_id="s1", strategy_fingerprint="fp")["ir"]
    protocol = validate_protocol(ir, scene=_scene(), strategy=_strategy())
    assert any(e["code"] == "UNKNOWN_BEAT_REFERENCE" for e in protocol["errors"])
    assert validate_content_constraints(ir, _strategy())["status"] == "FAIL"


def test_spatial_anchor_unknown_and_redundancy_are_hard_topology_findings():
    raw = {"scene_id": "s1", "architecture_summary": "建立。推进。收束。", "shots": [_shot("1"), _shot("1")]}
    ir = normalize_architecture_ir(raw, scene_id="s1", strategy_fingerprint="fp")["ir"]
    assert validate_topology(ir)["status"] == "FAIL"
    ir["shots"][0]["spatial_anchor"] = "unknown"
    assert validate_spatial(ir, {"participants": []})["status"] == "FAIL"


def test_information_order_and_transition_graph():
    raw = {"scene_id": "s1", "architecture_summary": "建立。推进。收束。", "shots": [_shot("1"), _shot("2", function="PRESSURE"), _shot("3", "P02", "CLOSING")]}
    ir = normalize_architecture_ir(raw, scene_id="s1", strategy_fingerprint="fp")["ir"]
    assert validate_information(ir, _scene())["status"] == "PASS"
    assert len(transition_graph(ir)) == 2


def test_distinctiveness_detects_exact_template_leakage_only_when_all_signals_match():
    a = {"scene_id": "a", "architecture_summary": "same", "shots": [{"function": ["WS"], "shot_size": "WS", "camera_movement": "STATIC"}]}
    b = {"scene_id": "b", "architecture_summary": "same", "shots": [{"function": ["WS"], "shot_size": "WS", "camera_movement": "STATIC"}]}
    c = {"scene_id": "c", "architecture_summary": "same", "shots": [{"function": ["WS"], "shot_size": "WS", "camera_movement": "STATIC"}]}
    result = compare_architectures([a, b, c])
    assert result["pair_count"] == 3
    assert result["hard_template_leakage"] is True


def test_topology_flags_reaction_without_stimulus_and_mechanical_beat_mapping():
    first = _shot("1", function="REACTION")
    second = _shot("2", function="OBSERVE")
    ir = normalize_architecture_ir({"scene_id": "s1", "architecture_summary": "建立。推进。收束。", "shots": [first, second]}, scene_id="s1", strategy_fingerprint="fp")["ir"]
    result = validate_topology(ir)
    assert any(error["code"] == "REACTION_WITHOUT_STIMULUS" for error in result["hard_errors"])
    assert any(warning["code"] == "MECHANICAL_BEAT_TO_SHOT_MAPPING" for warning in result["warnings"])
