from __future__ import annotations

from core.atomic_shot_expansion import materialize_candidate, validate_atomic_expansion
from core.semantic_events import project_semantic_events
from core.shot_topology_graph_binder import bind_topology, validate_bound_edges
from core.shot_topology_skeleton import normalize_skeleton, validate_skeleton
from core.visual_editorial_spine import normalize_spine, validate_spine
from scripts.run_director_quality_v3_shot_architecture_redesign_foundation import _expansion, _scene, _skeleton_raw, _spine_raw, _strategy


def _compiled():
    scene, strategy = _scene(), _strategy()
    spine = normalize_spine(_spine_raw(), scene_id=scene["scene_id"], strategy_fingerprint=strategy["strategy_fingerprint"])
    skeleton = normalize_skeleton(_skeleton_raw(), scene_id=scene["scene_id"], spine_fingerprint=spine["spine_fingerprint"])
    bound = bind_topology(skeleton["ir"], semantic_events=project_semantic_events(scene))
    expansion = _expansion(bound)
    return scene, strategy, spine, skeleton, bound, expansion


def test_spine_contract_chronology_and_strategy_fidelity():
    scene, strategy, spine, *_ = _compiled()
    result = validate_spine(spine["ir"], scene=scene, strategy=strategy)
    assert result["status"] == "PASS"
    bad = _spine_raw(); bad["segments"] = list(reversed(bad["segments"]))
    bad_ir = normalize_spine(bad, scene_id=scene["scene_id"], strategy_fingerprint=strategy["strategy_fingerprint"])["ir"]
    assert validate_spine(bad_ir, scene=scene, strategy=strategy)["status"] == "FAIL"


def test_spine_forbidden_field_future_leak_and_must_avoid_fail_closed():
    scene, strategy, *_ = _compiled()
    bad = _spine_raw(); bad["segments"][0]["shot_size"] = "CU"
    assert normalize_spine(bad, scene_id=scene["scene_id"], strategy_fingerprint=strategy["strategy_fingerprint"])["status"] == "FAIL"
    future = _spine_raw(); future["segments"][0]["information_change"] = "beat:3 is revealed"
    ir = normalize_spine(future, scene_id=scene["scene_id"], strategy_fingerprint=strategy["strategy_fingerprint"])["ir"]
    assert any(e["code"] == "SPINE_FUTURE_INFORMATION_LEAK" for e in validate_spine(ir, scene=scene, strategy=strategy)["hard_errors"])
    avoid = _spine_raw(); avoid["segments"][0]["visual_motif"] = "提前揭示第三方"
    ir = normalize_spine(avoid, scene_id=scene["scene_id"], strategy_fingerprint=strategy["strategy_fingerprint"])["ir"]
    assert any(e["code"] == "SPINE_MUST_AVOID_VIOLATION" for e in validate_spine(ir, scene=scene, strategy=strategy)["hard_errors"])


def test_skeleton_coverage_role_reaction_and_authority_boundaries():
    scene, strategy, spine, skeleton, *_ = _compiled()
    assert validate_skeleton(skeleton["ir"], spine=spine["ir"], scene=scene, strategy=strategy)["status"] == "PASS"
    bad = _skeleton_raw(); bad["nodes"][0]["camera_movement"] = "PAN"
    assert normalize_skeleton(bad, scene_id=scene["scene_id"], spine_fingerprint=spine["spine_fingerprint"])["status"] == "FAIL"
    missing = _skeleton_raw(); missing["nodes"][1]["stimulus_beat_refs"] = []
    ir = normalize_skeleton(missing, scene_id=scene["scene_id"], spine_fingerprint=spine["spine_fingerprint"])["ir"]
    assert any(e["code"] == "REACTION_SEMANTIC_STIMULUS_MISSING" for e in validate_skeleton(ir, spine=spine["ir"], scene=scene, strategy=strategy)["hard_errors"])
    identity = _skeleton_raw(); identity["nodes"][0]["subjects"] = ["character:unknown"]
    ir = normalize_skeleton(identity, scene_id=scene["scene_id"], spine_fingerprint=spine["spine_fingerprint"])["ir"]
    assert any(e["code"] == "SKELETON_IDENTITY_BINDING_INVALID" for e in validate_skeleton(ir, spine=spine["ir"], scene=scene, strategy=strategy)["hard_errors"])


def test_graph_binder_unique_ambiguous_missing_future_and_self_edge():
    scene, strategy, spine, skeleton, bound, _ = _compiled()
    assert bound["binding_status"] == "PASS"
    ambiguous = _skeleton_raw(); ambiguous["nodes"] = [dict(ambiguous["nodes"][0], beat_refs=["beat:2"]), dict(ambiguous["nodes"][0], segment_key="SEG01", beat_refs=["beat:2"]), dict(ambiguous["nodes"][1], segment_key="SEG02", stimulus_beat_refs=["beat:2"])]
    amb = bind_topology(normalize_skeleton(ambiguous, scene_id=scene["scene_id"], spine_fingerprint=spine["spine_fingerprint"])["ir"], semantic_events=project_semantic_events(scene))
    assert any(e["code"] == "GRAPH_BINDING_AMBIGUOUS" for e in amb["errors"])
    missing = _skeleton_raw(); missing["nodes"] = [dict(missing["nodes"][1], stimulus_beat_refs=["beat:99"])]
    mis = bind_topology(normalize_skeleton(missing, scene_id=scene["scene_id"], spine_fingerprint=spine["spine_fingerprint"])["ir"], semantic_events=project_semantic_events(scene))
    assert any(e["code"] == "GRAPH_BINDING_TARGET_MISSING" for e in mis["errors"])
    future = _skeleton_raw(); future["nodes"] = [dict(future["nodes"][1], segment_key="SEG01", phase_id="P01", beat_refs=["beat:1"], stimulus_beat_refs=["beat:2"]), dict(future["nodes"][0], segment_key="SEG02", phase_id="P02", beat_refs=["beat:2"])]
    fut = bind_topology(normalize_skeleton(future, scene_id=scene["scene_id"], spine_fingerprint=spine["spine_fingerprint"])["ir"], semantic_events=project_semantic_events(scene))
    assert any(e["code"] == "GRAPH_BINDING_ORDER_INVALID" for e in fut["errors"])
    assert any(e["code"] == "GRAPH_SELF_EDGE_INVALID" for e in validate_bound_edges([{"edge_type": "REACTION_TO", "from_node_id": "ST01", "to_node_id": "ST01"}]))


def test_atomic_expansion_coverage_mutation_and_deterministic_materialization():
    _, _, _, _, bound, expansion = _compiled()
    assert validate_atomic_expansion(bound, expansion)["status"] == "PASS"
    assert materialize_candidate(bound, expansion)["candidate"]["shots"][1]["stimulus_ref"] == "shot:SA01"
    assert materialize_candidate(bound, {"expansions": list(reversed(expansion["expansions"]))})["architecture_candidate_fingerprint"] == materialize_candidate(bound, expansion)["architecture_candidate_fingerprint"]
    mutation = {"expansions": [dict(expansion["expansions"][0], phase_id="P99"), expansion["expansions"][1]]}
    assert validate_atomic_expansion(bound, mutation)["status"] == "FAIL"
    unknown = {"expansions": list(expansion["expansions"]) + [dict(expansion["expansions"][0], node_id="ST99")]}
    assert validate_atomic_expansion(bound, unknown)["status"] == "FAIL"
    duplicate = {"expansions": [expansion["expansions"][0], expansion["expansions"][0]]}
    assert validate_atomic_expansion(bound, duplicate)["status"] == "FAIL"
