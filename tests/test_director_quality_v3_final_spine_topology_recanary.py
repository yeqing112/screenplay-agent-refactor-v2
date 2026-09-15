from core.shot_topology_skeleton import validate_skeleton
from core.visual_editorial_spine import validate_spine
from scripts.run_director_quality_v3_final_spine_topology_recanary import build_skeleton_request
from scripts.run_director_quality_v3_final_spine_topology_recanary import _fixture_spine


def _spine():
    return {"schema_version": "visual_editorial_spine_ir_v1", "scene_id": "s1", "strategy_fingerprint": "fp", "spine_summary": "x", "segments": [{"segment_key": "SEG01", "phase_ids": ["P01"], "beat_refs": ["beat:1"], "dramatic_function": "x", "audience_attention": "x", "performance_pressure": "x", "information_change": "x", "spatial_focus": "x", "visual_motif": "x", "editorial_rhythm": "x", "entry_condition": "x", "exit_condition": "x"}]}


def test_preserve_runtime_uses_trace_not_prose_exact_match():
    scene = {"scene_id": "s1", "beats": [{"beat_id": "1"}]}
    strategy = {"strategy_fingerprint": "fp", "scene_phases": [{"phase_id": "P01", "beat_ids": ["1"]}], "must_avoid": []}
    trace = {"constraints": [{"constraint_id": "MP01", "description": "long prose never repeated", "supporting_beat_refs": ["beat:1"], "status": "RESOLVED"}]}
    assert validate_spine(_spine(), scene=scene, strategy=strategy, must_preserve_trace=trace)["status"] == "PASS"
    missing = validate_spine(_spine(), scene=scene, strategy=strategy, must_preserve_trace=None)
    assert any(e["code"] == "PRESERVE_AUTHORITY_MISSING" for e in missing["hard_errors"])


def test_skeleton_identity_authority_missing_fails_closed_and_legacy_shape_is_not_used_when_explicit():
    skeleton = {"nodes": []}
    result = validate_skeleton(skeleton, spine={"segments": []}, scene={"characters": {"records": [{"character_id": "19"}]}}, strategy={"scene_phases": []}, identity_projection=None)
    assert any(e["code"] == "IDENTITY_AUTHORITY_MISSING" for e in result["hard_errors"])


def test_allowed_segment_refs_come_from_actual_spine_and_can_differ_from_phase_count():
    req = build_skeleton_request({"inputs": {"scene_blocking": {}, "scene": {}} , "scene_id": "s1"}, {"scene_phases": [{"phase_id": "P01"}, {"phase_id": "P02"}, {"phase_id": "P03"}]}, [{"character_id": "19", "canonical_name": "林晚"}], {"segments": [{"segment_key": "SEG01"}, {"segment_key": "SEG02"}, {"segment_key": "SEG03"}, {"segment_key": "SEG04"}]}, {"constraints": []}, {"events": []})
    assert req["allowed_segment_refs"] == ["SEG01", "SEG02", "SEG03", "SEG04"]
    assert req["skeleton_contract"]["primary_role_allowed_values"]


def test_unknown_character_reference_fails_with_authoritative_projection():
    skeleton = {"nodes": [{"node_key": "N01", "segment_key": "SEG01", "phase_id": "P01", "beat_refs": ["beat:1"], "primary_role": "OBSERVE", "secondary_role": None, "subjects": ["character:999"], "dramatic_reason": "x"}]}
    scene = {"beats": [{"beat_id": "1"}], "characters": {"records": []}}
    result = validate_skeleton(skeleton, spine={"segments": [{"segment_key": "SEG01", "phase_ids": ["P01"]}]}, scene=scene, strategy={"scene_phases": [{"phase_id": "P01"}]}, identity_projection={"records": [{"character_id": "19"}]}, allowed_segment_refs={"SEG01"})
    assert any(e["code"] == "SKELETON_IDENTITY_BINDING_INVALID" for e in result["hard_errors"])


def test_final_runner_dry_run_artifact_is_unauthorized_and_provider_free():
    import json
    result = json.loads(open("artifacts/director-quality-v3-final-spine-topology-preflight-dry-run.json", encoding="utf-8").read())
    assert result["provider_calls"] == 0
    assert result["authorization"] is False
    assert result["status_code"] == "DIRECTOR_V3_FINAL_SPINE_TOPOLOGY_RECANARY_NOT_AUTHORIZED"


def test_fixture_spine_has_more_segments_than_strategy_phases():
    fixture = _fixture_spine({"scene_phases": [{"phase_id": "P01"}, {"phase_id": "P02"}, {"phase_id": "P03"}]})
    assert [s["segment_key"] for s in fixture["segments"]] == ["SEG01", "SEG02", "SEG03", "SEG04"]
