from __future__ import annotations

import pytest

from core.shot_topology_skeleton import normalize_skeleton, validate_skeleton
from core.spine_topology_forensics import compare_identity_projection, validate_must_preserve_trace
from scripts.run_director_quality_v3_final_spine_topology_recanary import (
    allowed_segment_refs_from_spine,
    build_skeleton_request,
    _base_commit_gate,
)


def test_preserve_trace_requires_structured_authority_fields_and_fails_closed_when_missing():
    trace = {"schema_version": "must_preserve_trace_v1", "scene_id": "s1", "constraints": [{"constraint_id": "MP01", "description": "x", "supporting_beat_refs": ["beat:1"], "supporting_event_keys": [], "source_authority": ["beat:1"], "resolution_status": "RESOLVED"}]}
    assert validate_must_preserve_trace(trace, scene_id="s1")["status"] == "PASS"
    assert validate_must_preserve_trace({}, scene_id="s1")["status"] == "FAIL"


def test_skeleton_runtime_requires_authoritative_identity_projection():
    skeleton = normalize_skeleton({"nodes": []}, scene_id="s1", spine_fingerprint="fp")["ir"]
    result = validate_skeleton(skeleton, spine={"segments": []}, scene={"scene_id": "s1"}, strategy={"scene_phases": []}, require_authority=True)
    assert any(error["code"] == "IDENTITY_AUTHORITY_MISSING" for error in result["hard_errors"])


def test_provider_runtime_identity_projection_fingerprint_parity_is_exact():
    projection = {"records": [{"character_id": "19", "name": "林晚"}]}
    assert compare_identity_projection(projection, projection)["status"] == "PASS"
    assert compare_identity_projection(projection, {"records": [{"character_id": "19", "name": "其他"}]})["status"] == "FAIL"


def test_provider_runtime_identity_projection_detects_non_name_field_drift():
    provider = {"records": [{"character_id": "19", "name": "林晚", "gender": "女"}]}
    runtime = {"records": [{"character_id": "19", "name": "林晚", "gender": "男"}]}
    result = compare_identity_projection(provider, runtime)
    assert result["status"] == "FAIL"
    assert result["provider_fingerprint"] != result["runtime_fingerprint"]


def test_allowed_segment_refs_are_read_from_actual_spine_not_phase_count():
    spine = {"segments": [{"segment_key": "SEG01"}, {"segment_key": "SEG02"}, {"segment_key": "SEG03"}, {"segment_key": "SEG04"}]}
    assert allowed_segment_refs_from_spine(spine) == ["SEG01", "SEG02", "SEG03", "SEG04"]
    with pytest.raises(ValueError):
        allowed_segment_refs_from_spine({"segments": []})


def test_allowed_segment_refs_reject_phase_ids_and_noncanonical_labels():
    with pytest.raises(ValueError):
        allowed_segment_refs_from_spine({"segments": [{"segment_key": "P01"}]})
    with pytest.raises(ValueError):
        allowed_segment_refs_from_spine({"segments": [{"segment_key": "entrance"}]})


def test_preserve_coverage_is_structural_and_does_not_need_prose_repetition():
    from core.visual_editorial_spine import validate_spine

    scene = {"scene_id": "s1", "beats": [{"beat_id": "1"}, {"beat_id": "2"}, {"beat_id": "3"}]}
    strategy = {"strategy_fingerprint": "fp", "scene_phases": [{"phase_id": "P01", "beat_ids": ["1"]}], "must_avoid": []}
    spine = {"schema_version": "visual_editorial_spine_ir_v1", "scene_id": "s1", "strategy_fingerprint": "fp", "segments": [{"segment_key": "SEG01", "phase_ids": ["P01"], "beat_refs": ["beat:1", "beat:2", "beat:3"], "dramatic_function": "MP01 is covered structurally", "audience_attention": "a", "performance_pressure": "p", "information_change": "i", "spatial_focus": "s", "visual_motif": "m", "editorial_rhythm": "r", "entry_condition": "e", "exit_condition": "x"}]}
    trace = {"schema_version": "must_preserve_trace_v1", "scene_id": "s1", "constraints": [{"constraint_id": "MP01", "description": "long prose never repeated", "supporting_beat_refs": ["beat:3"], "supporting_event_keys": [], "resolution_status": "RESOLVED"}]}
    result = validate_spine(spine, scene=scene, strategy=strategy, must_preserve_trace=trace)
    assert result["status"] == "PASS"


def test_preserve_coverage_reports_uncovered_and_unresolved_distinctly():
    from core.visual_editorial_spine import validate_spine

    scene = {"scene_id": "s1", "beats": [{"beat_id": "1"}, {"beat_id": "2"}]}
    strategy = {"strategy_fingerprint": "fp", "scene_phases": [{"phase_id": "P01", "beat_ids": ["1"]}], "must_avoid": []}
    spine = {"schema_version": "visual_editorial_spine_ir_v1", "scene_id": "s1", "strategy_fingerprint": "fp", "segments": [{"segment_key": "SEG01", "phase_ids": ["P01"], "beat_refs": ["beat:1", "beat:2"], "dramatic_function": "d", "audience_attention": "a", "performance_pressure": "p", "information_change": "i", "spatial_focus": "s", "visual_motif": "m", "editorial_rhythm": "r", "entry_condition": "e", "exit_condition": "x"}]}
    trace = {"schema_version": "must_preserve_trace_v1", "scene_id": "s1", "constraints": [
        {"constraint_id": "MP01", "description": "missing beat", "supporting_beat_refs": ["beat:9"], "supporting_event_keys": [], "resolution_status": "RESOLVED"},
        {"constraint_id": "MP02", "description": "unresolved source", "supporting_beat_refs": [], "supporting_event_keys": [], "resolution_status": "PRESERVE_TRACE_UNRESOLVED"},
    ]}
    result = validate_spine(spine, scene=scene, strategy=strategy, must_preserve_trace=trace)
    codes = {error["code"] for error in result["hard_errors"]}
    assert "SPINE_MUST_PRESERVE_UNCOVERED" in codes
    assert "PRESERVE_TRACE_UNRESOLVED" in codes


def test_preserve_event_trace_can_supplement_beat_coverage_without_prose_matching():
    from core.visual_editorial_spine import validate_spine

    scene = {"scene_id": "s1", "beats": [{"beat_id": "1"}], "semantic_events": {"events": [{"event_key": "EVIDENCE_01"}]}}
    strategy = {"strategy_fingerprint": "fp", "scene_phases": [{"phase_id": "P01", "beat_ids": ["1"]}], "must_avoid": []}
    spine = {"schema_version": "visual_editorial_spine_ir_v1", "scene_id": "s1", "strategy_fingerprint": "fp", "segments": [{"segment_key": "SEG01", "phase_ids": ["P01"], "beat_refs": ["beat:1"], "dramatic_function": "d", "audience_attention": "a", "performance_pressure": "p", "information_change": "i", "spatial_focus": "s", "visual_motif": "m", "editorial_rhythm": "r", "entry_condition": "e", "exit_condition": "x"}]}
    trace = {"schema_version": "must_preserve_trace_v1", "scene_id": "s1", "constraints": [{"constraint_id": "MP01", "description": "human prose differs", "supporting_beat_refs": [], "supporting_event_keys": ["EVIDENCE_01"], "resolution_status": "RESOLVED"}]}
    assert validate_spine(spine, scene=scene, strategy=strategy, must_preserve_trace=trace)["status"] == "PASS"


def test_base_commit_gate_rejects_post_base_runtime_code_drift():
    result = _base_commit_gate("92b6d77", "HEAD")
    assert result["status"] == "FAIL"
    assert result["reason"] == "POST_BASE_CODE_DRIFT"


def test_skeleton_request_never_uses_phase_ids_as_segment_refs():
    request = build_skeleton_request(
        {"scene_id": "s1", "inputs": {"scene_blocking": {}, "scene": {}}},
        {"scene_phases": [{"phase_id": "P01"}, {"phase_id": "P02"}, {"phase_id": "P03"}]},
        [{"character_id": "19", "canonical_name": "林晚"}],
        {"segments": [{"segment_key": "SEG01"}, {"segment_key": "SEG02"}, {"segment_key": "SEG03"}, {"segment_key": "SEG04"}]},
        {"constraints": []},
        {"events": []},
    )
    assert request["allowed_segment_refs"] == ["SEG01", "SEG02", "SEG03", "SEG04"]
    assert all(not value.startswith("P") for value in request["allowed_segment_refs"])
