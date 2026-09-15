from core.spine_topology_forensics import (
    build_must_preserve_trace,
    classify_role,
    compare_identity_projection,
    detect_spine_layer_leakage,
    evaluate_preserve_coverage,
    resolve_segment_ref,
    skeleton_callable_after_spine,
)


def test_must_preserve_trace_is_structured_only_and_unresolved_without_binding():
    strategy = {"must_preserve": ["动作约束"], "source_trace": {"phases": []}}
    trace = build_must_preserve_trace(strategy, {"scene_id": "s1"})
    assert trace["schema_version"] == "must_preserve_trace_v1"
    assert trace["unresolved_count"] == 1
    assert trace["constraints"][0]["status"] == "PRESERVE_TRACE_UNRESOLVED"


def test_preserve_coverage_uses_beat_refs_not_prose_matching():
    strategy = {"must_preserve": ["动作"], "must_preserve_trace": [{"constraint_id": "MP01", "constraint": "动作", "supporting_beat_refs": ["beat:1"]}]}
    trace = build_must_preserve_trace(strategy, {"scene_id": "s1"})
    result = evaluate_preserve_coverage({"segments": [{"beat_refs": ["beat:1"]}]}, trace)
    assert result["constraints"][0]["status"] == "COVERED"


def test_role_classifier_does_not_force_ambiguous_roles():
    assert classify_role("ESTABLISHING")["canonical"] == "ESTABLISH"
    assert classify_role("DISCOVERY")["classification"] == "ROLE_SEMANTIC_REVIEW_REQUIRED"
    assert classify_role("made_up")["classification"] == "ROLE_UNSUPPORTED"


def test_segment_ref_resolution_requires_canonical_allowed_set():
    assert resolve_segment_ref("P01", allowed_segment_refs={"SEG01"})["canonical"] == "SEG01"
    assert resolve_segment_ref("P01", allowed_segment_refs={"SEG02"})["canonical"] is None


def test_identity_comparison_is_exact():
    projection = {"records": [{"character_id": "19", "name": "林晚"}]}
    assert compare_identity_projection(projection, projection)["status"] == "PASS"
    other = {"records": [{"character_id": "20", "name": "顾沉"}]}
    assert compare_identity_projection(projection, other)["status"] == "FAIL"


def test_layer_leakage_and_fail_closed_gate():
    assert detect_spine_layer_leakage("聚焦并停留")["severity"] in {"MINOR", "NONE"}
    assert detect_spine_layer_leakage("特写后正反打")["severity"] == "MATERIAL"
    assert skeleton_callable_after_spine(False)["skeleton_provider_callable"] is False
    assert skeleton_callable_after_spine(True)["skeleton_provider_callable"] is True
