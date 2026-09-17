from core.fact_requirement_semantics import (
    AUTHORITY_CLASSES,
    build_authoring_decision_request,
    classify_requirement,
    get_requirement_semantics,
    registry,
    stage_gate_requirements,
)
from core.fact_coverage import build_missing_fact_manifest
from core.fact_coverage_verifier import verify_fact_coverage


def _req(predicate, **overrides):
    value = {"subject_type": "character", "subject_id": "林晚", "predicate": predicate, "scope": "global", "required": True, "consumer": "script_ir"}
    value.update(overrides)
    return value


def test_registry_defines_four_authority_classes_and_semantic_fields():
    data = registry()
    assert data["schema_version"] == "fact_requirement_registry_v1"
    assert set(AUTHORITY_CLASSES) == {"SOURCE_FACT", "DERIVED_SOURCE_FACT", "PRODUCTION_AUTHORING_DECISION", "PRODUCTION_CONTINUITY_STATE"}
    for predicate in ("visual_identity", "current_state", "geometry", "state"):
        entry = get_requirement_semantics(predicate)
        assert entry["predicate"] == predicate
        assert entry["value_schema"]
        assert entry["scope_type"]
        assert entry["retrieval_semantics"]["terms"]


def test_visual_identity_is_authoring_decision_not_script_ir_source_gate():
    row = classify_requirement(_req("visual_identity"))
    assert row["authority_class"] == "PRODUCTION_AUTHORING_DECISION"
    assert row["blocking_stage"] == "VISUAL_ASSET_GENERATION"
    assert row["gate_eligible"] is False
    request = build_authoring_decision_request(row)
    assert request["schema_version"] == "authoring_decision_request_v1"
    assert request["status"] == "PENDING"
    assert request["prohibited_conflicts"]


def test_temporal_state_global_scope_is_narrowed_to_episode_without_changing_source_fact_identity():
    row = classify_requirement(_req("current_state"))
    assert row["scope"] == "episode"
    assert row["original_scope"] == "global"
    assert row["authority_class"] == "PRODUCTION_CONTINUITY_STATE"
    assert row["blocking_stage"] == "SCENE_BLOCKING"


def test_missing_authoring_requirements_do_not_block_script_ir_but_are_reported():
    result = build_missing_fact_manifest([_req("visual_identity"), _req("gender")], [])
    assert result["status"] == "FACT_COVERAGE_INSUFFICIENT"
    assert result["blocking_count"] == 1
    assert result["authoring_pending_count"] == 1
    assert result["authoring_decision_pending"][0]["predicate"] == "visual_identity"
    coverage = verify_fact_coverage(records=[], requirements=[_req("visual_identity")])
    assert coverage["status"] == "FACT_COVERAGE_SUFFICIENT"
    assert coverage["script_ir_gate"]["allowed"] is True
    assert coverage["authoring_decision_pending"]


def test_explicit_source_required_override_remains_fail_closed():
    row = classify_requirement(_req("visual_identity", source_required=True))
    assert row["authority_class"] == "SOURCE_FACT"
    assert row["blocking_stage"] == "SCRIPT_IR"
    assert row["gate_eligible"] is True
    assert stage_gate_requirements([_req("visual_identity", source_required=True)])
