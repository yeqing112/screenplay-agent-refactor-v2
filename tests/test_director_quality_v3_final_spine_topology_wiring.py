from __future__ import annotations

import pytest

from core.shot_topology_skeleton import normalize_skeleton, validate_skeleton
from core.spine_topology_forensics import compare_identity_projection, validate_must_preserve_trace
from scripts.run_director_quality_v3_final_spine_topology_recanary import (
    allowed_segment_refs_from_spine,
    build_skeleton_request,
)


def test_preserve_trace_requires_structured_authority_fields_and_fails_closed_when_missing():
    trace = {"schema_version": "must_preserve_trace_v1", "scene_id": "s1", "constraints": [{"constraint_id": "MP01", "description": "x", "supporting_beat_refs": ["beat:1"], "supporting_event_keys": [], "resolution_status": "RESOLVED"}]}
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


def test_allowed_segment_refs_are_read_from_actual_spine_not_phase_count():
    spine = {"segments": [{"segment_key": "SEG01"}, {"segment_key": "SEG02"}, {"segment_key": "SEG03"}, {"segment_key": "SEG04"}]}
    assert allowed_segment_refs_from_spine(spine) == ["SEG01", "SEG02", "SEG03", "SEG04"]
    with pytest.raises(ValueError):
        allowed_segment_refs_from_spine({"segments": []})


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
