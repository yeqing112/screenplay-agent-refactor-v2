from scripts.run_director_quality_v3_strategy_approval_repair_adjudication import (
    project_provider_repair_output_to_strategy_ir_v2,
    segment_match,
    scope_audit,
    _closure,
    _editable,
    _authority_audit,
)


def test_ingress_ignores_declared_program_metadata_but_rejects_unknown_creative():
    projected = project_provider_repair_output_to_strategy_ir_v2({
        "schema_version": "director_scene_strategy_ir_v2",
        "scene_id": "s",
        "strategy_fingerprint": "fake",
        "source_trace": {"fake": True},
        "new_scene_meaning": "forbidden",
    })
    assert projected["ignored_program_owned_fields"] == ["source_trace", "strategy_fingerprint"]
    assert projected["unknown_provider_fields"] == ["new_scene_meaning"]
    assert projected["projection_status"] == "FAIL"


def test_segment_scope_matcher_supports_named_phase_and_wildcards():
    assert segment_match("scene_phases[*].performance[*].character_id", "scene_phases[P01].performance[0].character_id")
    assert segment_match("scene_phases[*].power.center_ref", "scene_phases[P03].power.center_ref")
    assert segment_match("scene_phases[P02].information.hint_refs", "scene_phases[P02].information.hint_refs")
    assert not segment_match("scene_phases[P01].information.*", "scene_phases[P02].information.*")


def test_dependency_closure_allows_scene_three_audience_mirror_but_not_visual_thesis():
    base = {"scene_phases": [{"phase_id": "P01", "information": {"audience_suspicions": [{"claim": "顾沉可能进入", "support_refs": ["beat:B1"]}]}, "audience_state": {"suspects": ["顾沉可能进入"]}}]}
    revised = {"scene_phases": [{"phase_id": "P01", "information": {"audience_suspicions": [{"claim": "昨夜有人进入", "support_refs": ["beat:B1"]}]}, "audience_state": {"suspects": ["昨夜有人进入"]}}]}
    result = scope_audit(base, revised, _editable("book990402:e2:回声照相馆"), _closure("book990402:e2:回声照相馆"))
    assert result["scope_status"] == "PASS"
    revised["visual_thesis"] = "unrelated"
    assert scope_audit(base, revised, _editable("book990402:e2:回声照相馆"), _closure("book990402:e2:回声照相馆"))["scope_status"] == "FAIL"


def test_authority_is_independent_from_canonical_validity():
    assert _authority_audit([{"code": "UNKNOWN_IR_FIELD"}])["status"] == "SAFE"
    assert _authority_audit([{"code": "FACT_AUTHORITY_VIOLATION"}])["status"] == "UNSAFE"
