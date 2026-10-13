from __future__ import annotations

import pytest

from core.provider_structured_output_qualification import compile_provider_strict_schema, fingerprint, validate_json_schema_subset
from core.source_entity_proposal import claim_v2_schema
from core.source_semantic_claim_v3 import (
    CLAIM_V3_SET_VERSION,
    CLAIM_V3_VERSION,
    QUALIFIER_REGISTRY_VERSION,
    RELATION_SIGNATURE_REGISTRY_VERSION,
    assign_program_owned_claim_ids,
    build_claim_input_entity_registry,
    claim_v2_immutable_blocker_audit,
    claim_v3_candidate_fingerprint,
    claim_v3_candidate_schema,
    claim_v3_candidate_set_schema,
    count_schema_dialect_extensions,
    decode_claim_qualifiers_v3,
    proposable_predicate_registry_v1,
    qualifier_registry_audit,
    qualifier_registry_v2,
    qualifier_semantic_ambiguity_audit,
    relation_signature_completeness_audit,
    validate_claim_v3_candidate,
    validate_claim_v3_set,
)


def entity_registry():
    rows = {
        "CHAR_A": {"kind": "CHARACTER", "authority": "CANONICAL_RUNTIME", "canonical": True},
        "OBJ_B": {"kind": "OBJECT", "authority": "CANONICAL_RUNTIME", "canonical": True},
        "LOC_C": {"kind": "LOCATION", "authority": "CANONICAL_RUNTIME", "canonical": True},
        "PROP_D": {"kind": "PROPERTY_VALUE", "authority": "SEMANTICALLY_VERIFIED_PROPOSAL", "verification_state": "SEMANTICALLY_VERIFIED_PROPOSAL", "canonical": False},
        "STATE_E": {"kind": "STATE_VALUE", "authority": "SEMANTICALLY_VERIFIED_PROPOSAL", "verification_state": "SEMANTICALLY_VERIFIED_PROPOSAL", "canonical": False},
        "DIALOGUE_F": {"kind": "DIALOGUE_CONTENT", "authority": "CANONICAL_RUNTIME", "canonical": True},
    }
    return {"status": "PASS", "fingerprint": "frozen-fixture", "entities": rows}


def evidence_binding():
    return {"EV_1": ["UNIT_1"], "EV_2": ["UNIT_1"], "EV_3": ["UNIT_2"]}


def claim(**overrides):
    value = {
        "schema_version": CLAIM_V3_VERSION,
        "subject_ref": "CHAR_A",
        "predicate": "enter_guided",
        "object_ref": "LOC_C",
        "qualifiers": {"destination": "LOC_C"},
        "polarity": "POSITIVE",
        "modality": "ASSERTED",
        "evidence_refs": ["EV_1"],
        "source_unit_refs": ["UNIT_1"],
    }
    value.update(overrides)
    return value


def validate(value, *, registry=None, bindings=None):
    return validate_claim_v3_candidate(
        value,
        input_entity_registry=registry or entity_registry(),
        evidence_unit_bindings=bindings or evidence_binding(),
        allowed_source_unit_refs=["UNIT_1", "UNIT_2"],
    )


def test_v2_remains_the_legacy_union_blocker_and_its_contract_is_unchanged():
    before = fingerprint(claim_v2_schema())
    audit = claim_v2_immutable_blocker_audit()
    after = fingerprint(claim_v2_schema())
    assert audit["status"] == "LEGACY_BLOCKED_UNION_TYPE"
    assert "UNION_TYPE_UNSUPPORTED:$.properties.claims.items.properties.qualifiers.additionalProperties.type" in audit["compiler_errors"]
    assert audit["candidate_set_schema_version"] == "source_semantic_claim_candidate_set_v2"
    assert audit["v2_mutated"] is False
    assert before == after == audit["candidate_set_schema_fingerprint"]


def test_v3_schema_is_single_scalar_strict_and_compiles_without_dialect_expansion():
    predicates = proposable_predicate_registry_v1()
    schema = claim_v3_candidate_set_schema(candidate_schema=claim_v3_candidate_schema(input_entity_registry=entity_registry(), proposable_predicates=predicates))
    compiled = compile_provider_strict_schema(schema)
    counts = count_schema_dialect_extensions(schema)
    assert compiled["audit"]["status"] == "PASS"
    assert counts == {"union_type": 0, "oneOf": 0, "anyOf": 0, "dangling_ref": 0}
    qualifiers = schema["properties"]["claims"]["items"]["properties"]["qualifiers"]
    assert qualifiers == {"type": "object", "additionalProperties": {"type": "string", "minLength": 1}}
    assert validate_json_schema_subset({"schema_version": CLAIM_V3_SET_VERSION, "claims": [claim()]}, compiled["schema"])["status"] == "PASS"


def test_provider_candidate_contract_has_no_program_owned_semantic_fields():
    base = claim()
    for forbidden in ("candidate_id", "claim_id", "source_claim_id", "subject_kind", "object_kind", "claim_type", "relation_class", "authority", "canonical", "final_status", "char_start", "sha256"):
        assert validate({**base, forbidden: "PROVIDER_CONTROLLED"})["status"] == "BLOCKED", forbidden


def test_v3_predicate_registry_excludes_legacy_and_unresolved_relations():
    registry = proposable_predicate_registry_v1()
    audit = relation_signature_completeness_audit()
    assert registry["status"] == "PASS"
    assert registry["predicate_count"] == 6
    assert set(registry["excluded_legacy_structural_predicates"]) == {"scene_existence", "scene_identity_evidence"}
    assert set(registry["unresolved_predicates"]) == {"knows", "uncertainty"}
    assert audit["status"] == "PASS"
    assert audit["unresolved_relation_count"] == 2
    assert all(set(row) >= {"predicate", "claim_type", "relation_class", "allowed_subject_kinds", "allowed_object_kinds", "allowed_qualifier_keys", "required_qualifier_keys"} for row in registry["predicates"].values())


def test_v2_ownership_possession_ambiguity_is_audited_and_excluded_from_v3():
    audit = qualifier_semantic_ambiguity_audit()
    registry = qualifier_registry_v2()
    assert audit["status"] == "PASS"
    assert audit["ambiguous_keys_excluded_from_v3"] is True
    assert set(audit["audited_keys"]) == {"ownership", "possession"}
    assert not ({"ownership", "possession"} & set(registry["qualifiers"]))
    assert all(len(row["legacy_v2_python_types"]) == 2 and not row["v3_supported"] for row in audit["audited_keys"].values())
    assert qualifier_registry_audit(registry)["all_keys_have_one_value_type"] is True
    assert QUALIFIER_REGISTRY_VERSION == "source_claim_qualifier_registry_v2"


def test_claim_input_registry_only_admits_canonical_and_semantically_verified_entities():
    source = {
        "schema_version": "source_verified_entity_registry_v1",
        "canonical_runtime_entities": {"CHAR_A": {"ref": "CHAR_A", "kind": "CHARACTER", "authority": "CANONICAL_RUNTIME", "canonical": True}},
        "proposal_entities": {"PEC_A": {"ref": "PEC_A", "kind": "OBJECT", "authority": "SEMANTICALLY_VERIFIED_PROPOSAL", "verification_state": "SEMANTICALLY_VERIFIED_PROPOSAL", "canonical": False}},
    }
    source["fingerprint"] = fingerprint(source)
    # V7.7.7 adds execution status as an envelope after fingerprinting.
    source["status"] = "SOURCE_ENTITY_SEMANTIC_VERIFICATION_VALIDATED"
    built = build_claim_input_entity_registry(source, expected_fingerprint=source["fingerprint"])
    assert built["status"] == "PASS"
    assert built["errors"] == []
    assert built["canonical_entity_count"] == 1
    assert built["verified_proposal_count"] == 1
    assert built["blocked_entity_count"] == 0
    assert built["canonical_promotions"] == 0


@pytest.mark.parametrize("authority", ["UNTRUSTED_PROPOSED", "REJECTED_PROPOSAL", "ENTITY_SEMANTIC_REVIEW_REQUIRED"])
def test_untrusted_rejected_and_review_required_entities_are_blocked(authority):
    registry = entity_registry()
    registry["entities"]["CHAR_A"]["authority"] = authority
    result = validate(claim(), registry=registry)
    assert result["status"] == "BLOCKED"
    assert any(error.startswith("ENTITY_AUTHORITY_BLOCKED:CHAR_A") for error in result["errors"])


def test_claim_entity_kinds_are_resolved_from_refs_not_provider_fields():
    result = validate(claim())
    assert result["status"] == "PASS"
    assert result["projection"]["subject"] == {"ref": "CHAR_A", "kind": "CHARACTER"}
    assert result["projection"]["object"] == {"ref": "LOC_C", "kind": "LOCATION"}
    assert "subject_kind" not in result["projection"]


def test_entity_ref_qualifier_resolves_only_through_claim_input_registry():
    good = validate(claim())
    bad = validate(claim(qualifiers={"destination": "NOT_A_REGISTRY_REF"}))
    assert good["status"] == "PASS"
    assert bad["status"] == "BLOCKED"
    assert "UNKNOWN_ENTITY_REF:NOT_A_REGISTRY_REF" in bad["errors"]


def test_qualifier_key_and_relation_allowlist_are_both_enforced():
    unknown = validate(claim(qualifiers={"invented_key": "ABC"}))
    disallowed = validate(claim(predicate="speech_act", object_ref="DIALOGUE_F", qualifiers={"destination": "LOC_C"}))
    assert "UNKNOWN_QUALIFIER_KEY:invented_key" in unknown["errors"]
    assert "QUALIFIER_NOT_ALLOWED_FOR_PREDICATE:speech_act:destination" in disallowed["errors"]


def test_symbolic_token_syntax_is_not_natural_language_normalization():
    registry = qualifier_registry_v2()
    allowed = entity_registry()
    good = decode_claim_qualifiers_v3({"light_state": "LIGHT_OFF"}, qualifier_registry=registry, entity_registry=allowed["entities"])
    for value in ("light_off", "LIGHT OFF", "light off", "TRUE "):
        bad = decode_claim_qualifiers_v3({"light_state": value}, qualifier_registry=registry, entity_registry=allowed["entities"])
        assert bad["status"] == "BLOCKED"
        assert "SYMBOLIC_TOKEN_INVALID:light_state" in bad["errors"]
    assert good["status"] == "PASS"
    assert good["typed_qualifiers"]["light_state"]["value"] == "LIGHT_OFF"


def test_boolean_token_decoder_accepts_only_exact_uppercase_wire_tokens():
    test_only_boolean_registry = {"schema_version": QUALIFIER_REGISTRY_VERSION, "qualifiers": {"test_flag": {"value_type": "BOOLEAN_TOKEN"}}}
    entities = entity_registry()["entities"]
    assert decode_claim_qualifiers_v3({"test_flag": "TRUE"}, qualifier_registry=test_only_boolean_registry, entity_registry=entities)["typed_qualifiers"]["test_flag"]["value"] is True
    assert decode_claim_qualifiers_v3({"test_flag": "FALSE"}, qualifier_registry=test_only_boolean_registry, entity_registry=entities)["typed_qualifiers"]["test_flag"]["value"] is False
    for value in ("true", "false", "1", "yes", "是"):
        result = decode_claim_qualifiers_v3({"test_flag": value}, qualifier_registry=test_only_boolean_registry, entity_registry=entities)
        assert result["status"] == "BLOCKED"
        assert result["errors"] == ["BOOLEAN_TOKEN_INVALID:test_flag"]


def test_relation_subject_object_and_qualifier_signatures_block_mismatch():
    wrong_subject = validate(claim(subject_ref="OBJ_B"))
    wrong_object = validate(claim(object_ref="OBJ_B", qualifiers={}))
    wrong_qualifier_ref = validate(claim(qualifiers={"destination": "OBJ_B"}))
    assert any(error.startswith("RELATION_SUBJECT_KIND_MISMATCH") for error in wrong_subject["errors"])
    assert any(error.startswith("RELATION_OBJECT_KIND_MISMATCH") for error in wrong_object["errors"])
    assert any(error.startswith("QUALIFIER_ENTITY_KIND_MISMATCH:destination:OBJECT") for error in wrong_qualifier_ref["errors"])
    assert RELATION_SIGNATURE_REGISTRY_VERSION == "source_claim_relation_signature_registry_v2"


def test_legacy_structural_predicates_are_not_proposable():
    for predicate in ("scene_existence", "scene_identity_evidence"):
        result = validate(claim(predicate=predicate))
        assert result["status"] == "BLOCKED"
        assert f"PREDICATE_NOT_PROPOSABLE:{predicate}" in result["errors"]


def test_evidence_must_exist_and_belong_to_a_declared_frozen_source_unit():
    unknown = validate(claim(evidence_refs=["EV_UNKNOWN"]))
    mismatch = validate(claim(source_unit_refs=["UNIT_2"]))
    unknown_unit = validate(claim(source_unit_refs=["UNIT_UNKNOWN"]))
    assert "EVIDENCE_REF_UNKNOWN:EV_UNKNOWN" in unknown["errors"]
    assert "EVIDENCE_UNIT_BINDING_MISMATCH:EV_1" in mismatch["errors"]
    assert "SOURCE_UNIT_REF_UNKNOWN:UNIT_UNKNOWN" in unknown_unit["errors"]


def test_set_schema_and_runtime_validator_enforce_closed_wrapper():
    predicate_registry = proposable_predicate_registry_v1()
    schema = claim_v3_candidate_set_schema(candidate_schema=claim_v3_candidate_schema(input_entity_registry=entity_registry(), proposable_predicates=predicate_registry))
    compiled = compile_provider_strict_schema(schema)
    payload = {"schema_version": CLAIM_V3_SET_VERSION, "claims": [claim()]}
    assert compiled["audit"]["status"] == "PASS"
    assert validate_json_schema_subset(payload, compiled["schema"])["status"] == "PASS"
    payload["claims"][0]["claim_id"] = "PROVIDER_ID"
    assert validate_json_schema_subset(payload, compiled["schema"])["status"] == "BLOCKED"
    runtime = validate_claim_v3_set({"schema_version": CLAIM_V3_SET_VERSION, "claims": [claim(), {**claim(), "predicate": "no_signature"}]}, input_entity_registry=entity_registry(), evidence_unit_bindings=evidence_binding(), allowed_source_unit_refs=["UNIT_1"])
    assert runtime["status"] == "BLOCKED"
    assert runtime["blocked_count"] == 1


def test_projection_and_program_owned_claim_ids_are_deterministic_and_untrusted():
    first_result = validate(claim())
    second_result = validate(claim(predicate="left_by", subject_ref="CHAR_A", object_ref="OBJ_B", qualifiers={}))
    entity_fp = "entity-registry-fingerprint"
    assigned_a = assign_program_owned_claim_ids([first_result, second_result], entity_registry_fingerprint=entity_fp)
    assigned_b = assign_program_owned_claim_ids([second_result, first_result], entity_registry_fingerprint=entity_fp)
    assert assigned_a["status"] == "PASS"
    assert assigned_a["rows"] == assigned_b["rows"]
    assert [row["claim_id"] for row in assigned_a["rows"]] == ["SCC_0001", "SCC_0002"]
    assert all(row["authority"] == "UNTRUSTED_PROPOSED" and row["canonical"] is False for row in assigned_a["rows"])
    assert all("claim_id" in row and "source_claim_id" not in row for row in assigned_a["rows"])
    assert claim_v3_candidate_fingerprint(first_result["projection"], entity_registry_fingerprint=entity_fp) == claim_v3_candidate_fingerprint(first_result["projection"], entity_registry_fingerprint=entity_fp)


def test_fingerprint_changes_only_with_typed_semantics_evidence_or_registry_versions():
    base = validate(claim())["projection"]
    changed_display = {**base, "display_prose": "ignored display"}
    assert claim_v3_candidate_fingerprint(base) == claim_v3_candidate_fingerprint(changed_display)
    changed = {**base, "predicate": "speech_act"}
    assert claim_v3_candidate_fingerprint(base) != claim_v3_candidate_fingerprint(changed)
    assert claim_v3_candidate_fingerprint(base) != claim_v3_candidate_fingerprint(base, qualifier_registry_version="future-v3")


def test_program_owned_claim_projection_never_mutates_authority_stores():
    result = validate(claim())
    assigned = assign_program_owned_claim_ids([result], entity_registry_fingerprint="fixture")
    assert assigned["rows"][0]["authority"] == "UNTRUSTED_PROPOSED"
    assert assigned["rows"][0]["canonical"] is False
    assert assigned["rows"][0]["projection"]["schema_version"] == "source_semantic_claim_candidate_projection_v3"
