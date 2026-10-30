from core.source_claim_semantic_verifier_adapter import (
    TRANSPORT_FACT_ID, build_verifier_packet, component_contract,
    compile_shadow_overlay, evidence_authority_audit, required_components,
    support_role_registry_v1, typed_atomicity_guard, verifier_id_mapping,
)


SIGNATURE = {
    "predicate": "enter_guided", "required_qualifier_keys": ["guided_character"],
    "ref_constraints": [{"operator": "NOT_EQUAL", "left_role": "subject_ref", "right_role": "qualifier_ref:guided_character"}],
}
PROJECTION = {
    "claim_type": "CHARACTER_ACTION", "relation_class": "ACTION", "predicate": "enter_guided",
    "subject": {"ref": "CHAR_A", "kind": "CHARACTER"}, "object": {"ref": "LOC_A", "kind": "LOCATION"},
    "qualifiers": {"guided_character": {"value_type": "ENTITY_REF", "ref": "CHAR_B", "kind": "CHARACTER"}},
    "polarity": "POSITIVE", "modality": "ASSERTED", "evidence_refs": ["EV1"], "source_unit_refs": ["UNIT1"],
}
UNIT = {"unit_id": "UNIT1", "source_evidence": {"evidence_id": "EV1", "text": "Narrative action.", "sha256": "x"}}


def test_transport_mapping_is_program_owned_and_deterministic():
    mapping = verifier_id_mapping("SCC_X")
    assert mapping["mappings"] == [{"transport_fact_id": "FACT_0001", "claim_ref": "SCC_X", "transport_id_is_production_fact_id": False}]
    assert mapping["mapping_fingerprint"] == verifier_id_mapping("SCC_X")["mapping_fingerprint"]


def test_required_components_come_from_signature_not_source_prose():
    assert required_components(PROJECTION, SIGNATURE) == ["SUBJECT", "PREDICATE", "OBJECT", "QUALIFIER:guided_character", "POLARITY", "MODALITY"]


def test_typed_multi_role_relation_is_atomic_even_when_qualifier_is_a_dict():
    audit = typed_atomicity_guard(PROJECTION, SIGNATURE)
    assert audit["status"] == "PASS"
    assert audit["representation_is_not_composite"] is True
    assert audit["uses_json_dict_as_composite_signal"] is False


def test_typed_atomicity_blocks_same_guide_and_guided():
    bad = {**PROJECTION, "qualifiers": {"guided_character": {"value_type": "ENTITY_REF", "ref": "CHAR_A", "kind": "CHARACTER"}}}
    assert "TYPED_ATOMICITY_ROLE_CONSTRAINT_FAILED" in typed_atomicity_guard(bad, SIGNATURE)["errors"]


def test_relation_class_support_role_is_not_predicate_name_inference():
    registry = support_role_registry_v1()
    assert registry["mapping"]["ACTION"] == "ACTION_OCCURRENCE"
    assert registry["predicate_name_inference"] is False


def test_evidence_authority_binds_exact_single_evidence_and_unit():
    assert evidence_authority_audit(projection=PROJECTION, source_unit=UNIT, source_fingerprint="source", expected_source_fingerprint="source")["status"] == "PASS"
    bad = {**PROJECTION, "evidence_refs": ["OTHER"]}
    assert evidence_authority_audit(projection=bad, source_unit=UNIT, source_fingerprint="source", expected_source_fingerprint="source")["status"] == "BLOCKED"


def test_entailed_requires_all_components_and_empty_unsupported():
    required = required_components(PROJECTION, SIGNATURE)
    good = {"verdict": "ENTAILED", "supported_components": required, "unsupported_components": []}
    assert component_contract(good, required)["status"] == "PASS"
    missing = {"verdict": "ENTAILED", "supported_components": required[:-1], "unsupported_components": []}
    assert "VERIFIER_ENTAILED_COMPONENT_COVERAGE_INVALID" in component_contract(missing, required)["errors"]
    unsupported = {"verdict": "ENTAILED", "supported_components": required, "unsupported_components": ["OBJECT"]}
    assert "VERIFIER_ENTAILED_COMPONENT_COVERAGE_INVALID" in component_contract(unsupported, required)["errors"]


def test_component_contract_blocks_unknown_duplicate_and_overlap():
    result = {"verdict": "PARTIAL", "supported_components": ["SUBJECT", "SUBJECT", "UNKNOWN"], "unsupported_components": ["SUBJECT"]}
    errors = component_contract(result, required_components(PROJECTION, SIGNATURE))["errors"]
    assert "VERIFIER_COMPONENT_DUPLICATE" in errors
    assert "VERIFIER_COMPONENT_CONTRACT_INVALID" in errors


def test_provider_entailed_cannot_override_typed_atomicity_blocker():
    packet = build_verifier_packet(claim_ref="SCC_X", projection=PROJECTION, relation_signature=SIGNATURE, evidence={"evidence_id": "EV1", "text": "Narrative action.", "source_unit_ref": "UNIT1"})
    result = {"fact_id": TRANSPORT_FACT_ID, "verdict": "ENTAILED", "supported_components": packet["required_semantic_components"], "unsupported_components": [], "rationale": "provider"}
    overlay = compile_shadow_overlay(packet=packet, result=result, evidence_status="PASS", atomicity={"status": "BLOCKED", "errors": ["TYPED_ATOMICITY_ROLE_CONSTRAINT_FAILED"]}, component_audit={"status": "PASS"})
    assert overlay["semantic_disposition"] == "AMBIGUOUS_REVIEW"
    assert overlay["downstream_eligible"] is False
    assert overlay["production_persisted"] is False
