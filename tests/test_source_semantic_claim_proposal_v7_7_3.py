"""Provider-free contract tests for the V7.7.3 proposal boundary."""
from __future__ import annotations

from core.director_claim_relation_registry import validate_relation_registry
from core.source_semantic_claim_authority import validate_evidence_binding
from core.source_semantic_claim_proposal import (
    CANDIDATE_SET_VERSION,
    PROPOSAL_VERSION,
    build_proposal_prompt,
    candidate_set,
    duplicate_and_contradiction_audit,
    proposed_fact_projection,
    provider_identity,
    surface_coverage,
    validate_candidate_strict,
    validate_wrapper,
    wrapper_schema,
)


ENTITY_REGISTRY = {
    "CHAR_A": {"kind": "CHARACTER"},
    "LOC_A": {"kind": "LOCATION"},
    "DIALOGUE_1": {"kind": "DIALOGUE_CONTENT"},
}


def _candidate(**overrides):
    value = {
        "schema_version": "source_semantic_claim_candidate_v1",
        "candidate_id": "SCC_1",
        "subject": {"kind": "CHARACTER", "ref": "CHAR_A"},
        "predicate": "enter_guided",
        "object": {"kind": "LOCATION", "ref": "LOC_A"},
        "qualifiers": {"destination": "LOC_A"},
        "polarity": "POSITIVE",
        "modality": "ASSERTED",
        "evidence_refs": ["EV_1"],
        "source_unit_refs": ["UNIT_1"],
    }
    value.update(overrides)
    return value


def test_wrapper_is_strict_and_empty_wrapper_is_valid():
    assert wrapper_schema()["additionalProperties"] is False
    assert validate_wrapper({"schema_version": PROPOSAL_VERSION, "candidates": []})["status"] == "PASS"
    assert validate_wrapper({"schema_version": PROPOSAL_VERSION, "candidates": [], "extra": 1})["status"] == "BLOCKED"


def test_candidate_extra_and_forbidden_fields_block():
    assert validate_candidate_strict({**_candidate(), "display_text": "x"}, entity_registry=ENTITY_REGISTRY)["status"] == "BLOCKED"
    nested = {**_candidate(), "qualifiers": {"destination": "LOC_A", "nested": {"promote": True}}}
    assert validate_candidate_strict(nested, entity_registry=ENTITY_REGISTRY)["status"] == "BLOCKED"


def test_predicate_qualifier_and_entity_binding_are_typed():
    assert validate_candidate_strict(_candidate(predicate="not_registered"), entity_registry=ENTITY_REGISTRY)["status"] == "BLOCKED"
    assert validate_candidate_strict(_candidate(qualifiers={"destination": 1}), entity_registry=ENTITY_REGISTRY)["status"] == "BLOCKED"
    assert validate_candidate_strict(_candidate(object={"kind": "LOCATION", "ref": "UNKNOWN"}), entity_registry=ENTITY_REGISTRY)["status"] == "BLOCKED"
    assert validate_candidate_strict(_candidate(), entity_registry=ENTITY_REGISTRY)["status"] == "PASS"


def test_evidence_freshness_and_scope_are_program_validated():
    evidence = {"anchors": [{"anchor_ref": "EV_1", "source_fingerprint": "FP", "source_package_id": "PKG"}]}
    assert validate_evidence_binding(evidence_refs=["EV_1"], evidence_index=evidence, source_fingerprint="FP", source_package_id="PKG")["status"] == "PASS"
    assert validate_evidence_binding(evidence_refs=["EV_1"], evidence_index=evidence, source_fingerprint="STALE", source_package_id="PKG")["status"] == "BLOCKED"
    assert validate_evidence_binding(evidence_refs=["EV_2"], evidence_index=evidence, source_fingerprint="FP", source_package_id="PKG")["status"] == "BLOCKED"


def test_candidate_set_fingerprint_and_projection_are_deterministic_and_non_authoritative():
    result = candidate_set([_candidate()], entity_registry=ENTITY_REGISTRY)
    assert result["schema_version"] == CANDIDATE_SET_VERSION
    assert result["valid_count"] == 1
    assert result["candidate_fingerprint"] == candidate_set([_candidate()], entity_registry=ENTITY_REGISTRY)["candidate_fingerprint"]
    projection = proposed_fact_projection(result["valid_typed_candidates"])
    assert projection["projection_count"] == 1
    assert projection["facts"][0]["fact_id"] == "FACT_0001"
    assert projection["facts"][0]["status"] == "model_observation"
    assert projection["persisted"] is False


def test_duplicate_audit_and_surface_coverage_never_claim_semantic_completeness():
    candidates = [_candidate(), {**_candidate(), "candidate_id": "SCC_2"}]
    assert duplicate_and_contradiction_audit(candidates)["status"] == "BLOCKED"
    coverage = surface_coverage(source_units=[{"unit_id": "UNIT_1"}, {"unit_id": "UNIT_2"}], candidates=candidates)
    assert coverage["name"] == "PROPOSAL_SURFACE_COVERAGE"
    assert coverage["semantic_completeness"] == "NOT_PROVEN"


def test_prompt_identity_excludes_attempt_findings_and_profile_is_runtime_data():
    system, user = build_proposal_prompt(
        source_units=[{"unit_id": "UNIT_1", "source_type": "SOURCE_ACTION", "text": "source"}],
        script_ir={"schema_version": "script_ir_v1", "episode": 1, "scenes": []},
        entity_registry=ENTITY_REGISTRY,
        mapping_registry={"schema_version": "source_fact_claim_mapping_registry_v1", "mappings": {}},
        qualifier_contract={"schema_version": "typed_qualifier_contract_v1"},
    )
    assert "attempt-11" not in system + user
    assert "handwritten ticket" not in system + user
    identity = provider_identity(profile_snapshot={"profile_id": "runtime", "provider": "openai-compatible", "model": "model", "base_host": "https://host"}, system_prompt=system, user_prompt=user)
    assert identity["profile_id"] == "runtime"
    assert identity["request_fingerprint"]


def test_relation_registry_proves_v773_ontology_classes():
    assert validate_relation_registry()["status"] == "PASS"
