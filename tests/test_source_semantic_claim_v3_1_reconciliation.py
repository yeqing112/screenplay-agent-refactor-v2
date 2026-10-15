from __future__ import annotations

import json
from pathlib import Path

from core.source_semantic_claim_v3 import (
    build_claim_input_entity_registry,
    qualifier_registry_v2,
    relation_signature_registry_v2,
    validate_claim_v3_set,
)
from core.source_semantic_claim_v3_1 import (
    PROGRAM_DETERMINISTIC,
    PROVIDER_PROPOSABLE,
    build_deterministic_speech_act_candidate,
    first_order_relation_ownership_registry_v1,
    proposal_ownership_classification_v1,
    provider_predicate_registry_v2,
    qualifier_registry_v3,
    relation_signature_registry_v3,
    required_qualifier_executability_contract_v1,
    source_speech_act_binding_registry_v1,
    speech_act_deterministic_contract_v1,
    speech_act_proposal_ownership_contract_v1,
    validate_deterministic_speech_act_candidate,
    validate_provider_candidate_v3_1,
)


ROOT = Path(__file__).resolve().parents[1]
V779 = ROOT / "docs/canonical-canary/v7_7_9-source-semantic-claim-v3-first-order-proposal-real"
V778 = ROOT / "docs/canonical-canary/v7_7_8-source-semantic-claim-v3-foundation"
V71 = ROOT / "docs/canonical-canary/v7_1-director-source-grounded-authoring-contract"


def fixture_entities():
    return {
        "schema_version": "source_claim_input_entity_registry_v1",
        "status": "PASS",
        "entities": {
            "CHAR_A": {"ref": "CHAR_A", "kind": "CHARACTER", "authority": "CANONICAL_RUNTIME"},
            "CHAR_B": {"ref": "CHAR_B", "kind": "CHARACTER", "authority": "CANONICAL_RUNTIME"},
            "LOC_A": {"ref": "LOC_A", "kind": "LOCATION", "authority": "CANONICAL_RUNTIME"},
            "DIALOGUE_1": {"ref": "DIALOGUE_1", "kind": "DIALOGUE_CONTENT", "authority": "CANONICAL_RUNTIME"},
            "OBJ_A": {"ref": "OBJ_A", "kind": "OBJECT", "authority": "CANONICAL_RUNTIME"},
        },
    }


def candidate(predicate="enter_guided", **overrides):
    result = {
        "schema_version": "source_semantic_claim_candidate_v3",
        "subject_ref": "CHAR_A",
        "predicate": predicate,
        "object_ref": "LOC_A",
        "qualifiers": {"guided_character": "CHAR_B"} if predicate == "enter_guided" else {},
        "polarity": "POSITIVE",
        "modality": "ASSERTED",
        "evidence_refs": ["EV1"],
        "source_unit_refs": ["UNIT1"],
    }
    result.update(overrides)
    return result


def dialogue_fixture():
    binding = {
        "classification": "AUTHORIZED_SEMANTIC_BINDING",
        "binding_type": "COREFERENCE_RESOLUTION",
        "identity_evidence": [{"evidence_id": "IDENTITY_EV"}],
        "utterance_evidence": [{"evidence_id": "UTTERANCE_EV"}],
    }
    script_ir = {"scenes": [{"dialogues": [{
        "dialogue_id": "DIALOGUE_1",
        "speaker": "CHAR_A",
        "text": "unparsed dialogue text",
        "source_evidence": {"evidence_id": "EV1"},
        "speaker_binding": binding,
    }]}]}
    units = [{
        "unit_id": "DIALOGUE_1",
        "source_type": "SOURCE_DIALOGUE",
        "speaker": "CHAR_A",
        "text": "different prose is not inspected",
        "source_evidence": {"evidence_id": "EV1"},
    }]
    entities = fixture_entities()
    return binding, script_ir, units, entities


def test_v3_1_registries_are_versioned_and_historic_v2_remains_unchanged():
    old_relation = relation_signature_registry_v2()
    old_qualifier = qualifier_registry_v2()
    old_speech = old_relation["signatures"]["speech_act"]
    old_enter = old_relation["signatures"]["enter_guided"]
    old_speech_qualifiers = list(old_speech["allowed_qualifier_keys"])

    new_relation = relation_signature_registry_v3()
    new_qualifier = qualifier_registry_v3()

    assert new_relation["schema_version"] == "source_claim_relation_signature_registry_v3"
    assert new_qualifier["schema_version"] == "source_claim_qualifier_registry_v3"
    assert old_relation["signatures"]["speech_act"]["allowed_qualifier_keys"] == old_speech_qualifiers == ["speaker_binding"]
    assert old_relation["signatures"]["enter_guided"] == old_enter
    assert old_qualifier["schema_version"] == "source_claim_qualifier_registry_v2"


def test_speaker_binding_is_not_provider_writable_and_speech_act_is_program_owned():
    qualifier = qualifier_registry_v3()
    ownership = first_order_relation_ownership_registry_v1()
    relation = relation_signature_registry_v3()["signatures"]["speech_act"]
    contract = speech_act_proposal_ownership_contract_v1()

    assert "speaker_binding" not in qualifier["qualifiers"]
    assert qualifier["excluded_keys"]["speaker_binding"] == "PROGRAM_OWNED_PROVENANCE_NOT_SEMANTIC_QUALIFIER"
    assert relation["allowed_qualifier_keys"] == []
    assert relation["provider_proposable"] is False
    assert ownership["predicates"]["speech_act"]["proposal_owner"] == PROGRAM_DETERMINISTIC
    assert contract["provider_proposable"] is False


def test_speech_act_is_not_removed_from_first_order_ontology():
    registry = relation_signature_registry_v3()
    row = registry["signatures"]["speech_act"]
    assert row["claim_type"] == "SOURCE_SPEECH_ACT"
    assert row["relation_class"] == "SPEECH_ACT"
    assert row["proposal_mode"] == PROGRAM_DETERMINISTIC


def test_three_ownership_classes_partition_first_and_second_order_relations():
    result = proposal_ownership_classification_v1()
    assert result["status"] == "PASS"
    assert result["counts"] == {
        "PROVIDER_PROPOSABLE": 5,
        "PROGRAM_DETERMINISTIC": 1,
        "DEFERRED_SECOND_ORDER": 2,
    }
    assert result["classes"][PROVIDER_PROPOSABLE] == ["enter_guided", "has_property", "left_by", "received_by", "state_value"]
    assert set(result["classes"]["DEFERRED_SECOND_ORDER"]) == {"knows", "uncertainty"}
    assert result["second_order_registry_modified"] is False


def test_program_binding_uses_structured_speaker_and_binding_provenance():
    _binding, script_ir, units, entities = dialogue_fixture()
    registry = source_speech_act_binding_registry_v1(
        script_ir=script_ir, source_units=units, entity_registry=entities, source_fingerprint="source-fp",
    )
    row = registry["bindings"][0]
    assert registry["status"] == "PASS"
    assert row["dialogue_content_ref"] == "DIALOGUE_1"
    assert row["speaker_ref"] == "CHAR_A"
    assert set(row["evidence_refs"]) == {"EV1", "IDENTITY_EV", "UTTERANCE_EV"}
    assert row["source_unit_refs"] == ["DIALOGUE_1"]
    assert row["speaker_binding_provenance_fingerprint"]
    assert row["source_fingerprint"] == "source-fp"
    assert registry["dialogue_prose_parsed_for_speaker"] is False


def test_missing_structured_speaker_binding_blocks_without_prose_fallback():
    _, script_ir, units, entities = dialogue_fixture()
    script_ir["scenes"][0]["dialogues"][0]["speaker_binding"] = None
    script_ir["scenes"][0]["dialogues"][0]["text"] = "CHAR_A says the line"
    result = source_speech_act_binding_registry_v1(
        script_ir=script_ir, source_units=units, entity_registry=entities, source_fingerprint="source-fp",
    )
    assert result["status"] == "BLOCKED"
    assert "STRUCTURED_SPEAKER_BINDING_MISSING:DIALOGUE_1" in result["errors"]


def test_structured_script_ir_speaker_must_match_bound_source_unit_speaker():
    _, script_ir, units, entities = dialogue_fixture()
    script_ir["scenes"][0]["dialogues"][0]["speaker"] = "CHAR_B"
    result = source_speech_act_binding_registry_v1(
        script_ir=script_ir, source_units=units, entity_registry=entities, source_fingerprint="source-fp",
    )
    assert result["status"] == "BLOCKED"
    assert "DIALOGUE_STRUCTURED_SPEAKER_MISMATCH:DIALOGUE_1" in result["errors"]


def test_deterministic_speech_act_preserves_occurrence_evidence_and_not_world_truth():
    _, script_ir, units, entities = dialogue_fixture()
    registry = source_speech_act_binding_registry_v1(
        script_ir=script_ir, source_units=units, entity_registry=entities, source_fingerprint="source-fp",
    )
    candidate_row = build_deterministic_speech_act_candidate(registry["bindings"][0])
    audit = validate_deterministic_speech_act_candidate(candidate_row, registry)
    boundary = speech_act_deterministic_contract_v1()
    assert audit["status"] == "PASS"
    assert candidate_row["evidence_refs"] == ["EV1", "IDENTITY_EV", "UTTERANCE_EV"]
    assert candidate_row["qualifiers"] == {}
    assert candidate_row["authority_boundary"] == "STRUCTURED_SPEECH_OCCURRENCE_ONLY"
    assert candidate_row["dialogue_proposition_world_fact"] is False
    assert candidate_row["persisted"] is False
    assert boundary["proves_dialogue_proposition_truth"] is False
    assert boundary["semantic_verifier_required_for_dialogue_proposition"] is True


def test_wrong_speaker_is_blocked_by_program_binding_gate():
    _, script_ir, units, entities = dialogue_fixture()
    registry = source_speech_act_binding_registry_v1(
        script_ir=script_ir, source_units=units, entity_registry=entities, source_fingerprint="source-fp",
    )
    row = build_deterministic_speech_act_candidate(registry["bindings"][0])
    row["subject_ref"] = "CHAR_B"
    audit = validate_deterministic_speech_act_candidate(row, registry)
    assert audit["status"] == "BLOCKED"
    assert "SPEECH_ACT_SPEAKER_BINDING_MISMATCH" in audit["errors"]


def test_deterministic_speech_act_rejects_changed_program_owned_binding_provenance():
    _, script_ir, units, entities = dialogue_fixture()
    registry = source_speech_act_binding_registry_v1(
        script_ir=script_ir, source_units=units, entity_registry=entities, source_fingerprint="source-fp",
    )
    row = build_deterministic_speech_act_candidate(registry["bindings"][0])
    row["program_owned_provenance"]["speaker_binding_provenance_fingerprint"] = "drift"
    audit = validate_deterministic_speech_act_candidate(row, registry)
    assert audit["status"] == "BLOCKED"
    assert "SPEECH_ACT_PROVENANCE_FINGERPRINT_MISMATCH" in audit["errors"]


def test_enter_guided_requires_guided_character_entity_ref_and_drops_destination():
    relation = relation_signature_registry_v3()["signatures"]["enter_guided"]
    qualifiers = qualifier_registry_v3()["qualifiers"]
    assert relation["allowed_qualifier_keys"] == ["guided_character"]
    assert relation["required_qualifier_keys"] == ["guided_character"]
    assert relation["qualifier_entity_kind_constraints"] == {"guided_character": ["CHARACTER"]}
    assert qualifiers["guided_character"]["value_type"] == "ENTITY_REF"
    assert "destination" not in relation["allowed_qualifier_keys"]
    assert "destination" not in qualifiers


def test_enter_guided_missing_required_participant_is_blocked():
    result = validate_provider_candidate_v3_1(
        candidate(qualifiers={}),
        provider_registry=provider_predicate_registry_v2(relation_signature_registry_v3(), fixture_entities()),
        entity_registry=fixture_entities(),
    )
    assert result["status"] == "BLOCKED"
    assert "REQUIRED_QUALIFIER_MISSING:enter_guided:guided_character" in result["errors"]


def test_enter_guided_rejects_non_character_guided_participant():
    result = validate_provider_candidate_v3_1(
        candidate(qualifiers={"guided_character": "LOC_A"}),
        provider_registry=provider_predicate_registry_v2(relation_signature_registry_v3(), fixture_entities()),
        entity_registry=fixture_entities(),
    )
    assert result["status"] == "BLOCKED"
    assert "QUALIFIER_ENTITY_KIND_MISMATCH:guided_character:LOCATION" in result["errors"]


def test_enter_guided_accepts_character_ref_in_required_qualifier():
    entities = fixture_entities()
    result = validate_provider_candidate_v3_1(
        candidate(), provider_registry=provider_predicate_registry_v2(relation_signature_registry_v3(), entities),
        entity_registry=entities,
    )
    assert result["status"] == "PASS"
    assert result["typed_qualifiers"]["guided_character"] == {"value_type": "ENTITY_REF", "ref": "CHAR_B", "kind": "CHARACTER"}
    assert result["verifier_eligible"] is False


def test_destination_is_not_allowed_for_enter_guided_in_new_contract():
    result = validate_provider_candidate_v3_1(
        candidate(qualifiers={"guided_character": "CHAR_B", "destination": "LOC_A"}),
        provider_registry=provider_predicate_registry_v2(relation_signature_registry_v3(), fixture_entities()),
        entity_registry=fixture_entities(),
    )
    assert result["status"] == "BLOCKED"
    assert "QUALIFIER_NOT_PROVIDER_WRITABLE:destination" in result["errors"]


def test_required_entity_qualifier_kind_participates_in_executability():
    entities = fixture_entities()
    entities["entities"] = {"LOC_A": entities["entities"]["LOC_A"]}
    registry = provider_predicate_registry_v2(relation_signature_registry_v3(), entities)
    assert "enter_guided" in registry["dormant_predicates"]
    row = registry["dormant_predicates"]["enter_guided"]
    assert row["execution_status"] == "TYPE_DEPENDENCY_UNAVAILABLE"
    assert "QUALIFIER_ENTITY_KIND_UNAVAILABLE:guided_character" in row["missing_type_dependencies"]
    contract = required_qualifier_executability_contract_v1()
    assert contract["qualifier_name_special_cases"] is False


def test_provider_registry_excludes_speech_act_and_derives_three_executable_predicates():
    entities = fixture_entities()
    entities["entities"].update({
        "OBJECT_A": {"ref": "OBJECT_A", "kind": "OBJECT", "authority": "CANONICAL_RUNTIME"},
        "ENV_A": {"ref": "ENV_A", "kind": "ENVIRONMENT", "authority": "CANONICAL_RUNTIME"},
    })
    registry = provider_predicate_registry_v2(relation_signature_registry_v3(), entities)
    assert registry["schema_version"] == "source_claim_proposal_predicate_registry_v2"
    assert set(registry["predicates"]) == {"enter_guided", "left_by", "received_by"}
    assert set(registry["dormant_predicates"]) == {"has_property", "state_value"}
    assert registry["program_deterministic_predicates"] == ["speech_act"]
    assert "speech_act" not in registry["predicates"]


def test_current_v7_7_9_candidates_are_both_ineligible_under_new_contract():
    v777_registry_path = ROOT / "docs/canonical-canary/v7_7_7-source-entity-semantic-verification-real/SOURCE_VERIFIED_ENTITY_REGISTRY.json"
    source_registry = json.loads(v777_registry_path.read_text(encoding="utf-8"))
    entities = build_claim_input_entity_registry(source_registry)
    new_registry = provider_predicate_registry_v2(relation_signature_registry_v3(), entities)
    previous = json.loads((V779 / "SOURCE_CLAIM_V3_PROPOSAL_SET.json").read_text(encoding="utf-8"))
    results = [validate_provider_candidate_v3_1(
        row["raw_candidate"], provider_registry=new_registry, entity_registry=entities,
    ) for row in previous["candidates"]]
    assert [result["status"] for result in results] == ["BLOCKED", "BLOCKED"]
    assert any("REQUIRED_QUALIFIER_MISSING:enter_guided:guided_character" in e for e in results[0]["errors"])
    assert "PREDICATE_NOT_PROVIDER_PROPOSABLE:speech_act" in results[1]["errors"]
    assert "QUALIFIER_NOT_PROVIDER_WRITABLE:speaker_binding" in results[1]["errors"]


def test_historical_v7_7_9_validation_reproduces_one_pass_one_blocked():
    raw_audit = json.loads((V779 / "SOURCE_CLAIM_V3_RAW_FORENSIC.json").read_text(encoding="utf-8"))
    frozen_entities = json.loads((V778 / "CLAIM_INPUT_ENTITY_REGISTRY.json").read_text(encoding="utf-8"))
    frozen_executable = json.loads((V779 / "EXECUTABLE_FIRST_ORDER_PREDICATE_REGISTRY.json").read_text(encoding="utf-8"))
    source_contract = json.loads((V71 / "SOURCE_AUTHORING_UNIT_CONTRACT.json").read_text(encoding="utf-8"))
    payload = json.loads(raw_audit["raw_response"])
    evidence_bindings = {}
    for unit in source_contract["units"]:
        evidence_ref = (unit.get("source_evidence") or {}).get("evidence_id")
        if evidence_ref:
            evidence_bindings[evidence_ref] = [unit["unit_id"]]
    replay = validate_claim_v3_set(
        payload,
        input_entity_registry=frozen_entities,
        evidence_unit_bindings=evidence_bindings,
        allowed_source_unit_refs=[row["unit_id"] for row in source_contract["units"]],
        qualifier_registry=qualifier_registry_v2(),
        proposable_predicates=frozen_executable,
    )
    assert raw_audit["raw_response_sha256"] == "44730220ba61ce249d1ebd5b87e3a0373b4cc220e58b7f96eef04a5b06f40585"
    assert replay["candidate_count"] == 2
    assert replay["valid_count"] == 1
    assert replay["blocked_count"] == 1
    assert replay["candidate_results"][1]["errors"] == ["SYMBOLIC_TOKEN_INVALID:speaker_binding"]


def test_current_proposal_verifier_eligible_count_is_zero_and_old_state_is_immutable():
    old_status = json.loads((V779 / "SOURCE_CLAIM_V3_PROPOSAL_SET.json").read_text(encoding="utf-8"))["status"]
    assert old_status == "SOURCE_SEMANTIC_CLAIM_V3_PROPOSAL_PARTIAL"
    previous = json.loads((V779 / "SOURCE_CLAIM_V3_PROPOSAL_SET.json").read_text(encoding="utf-8"))
    assert json.loads((V779 / "SOURCE_CLAIM_V3_RAW_FORENSIC.json").read_text(encoding="utf-8"))["raw_response_sha256"] == "44730220ba61ce249d1ebd5b87e3a0373b4cc220e58b7f96eef04a5b06f40585"
    source_registry = json.loads((ROOT / "docs/canonical-canary/v7_7_7-source-entity-semantic-verification-real/SOURCE_VERIFIED_ENTITY_REGISTRY.json").read_text(encoding="utf-8"))
    entities = build_claim_input_entity_registry(source_registry)
    provider_registry = provider_predicate_registry_v2(relation_signature_registry_v3(), entities)
    current_results = [
        validate_provider_candidate_v3_1(row["raw_candidate"], provider_registry=provider_registry, entity_registry=entities)
        for row in previous["candidates"]
    ]
    verifier_eligible = [row for row in current_results if row["status"] == "PASS" and row["verifier_eligible"]]
    assert len(verifier_eligible) == 0
    assert [row["status"] for row in current_results] == ["BLOCKED", "BLOCKED"]


def test_claim_v2_and_second_order_historical_contracts_remain_untouched():
    v2 = json.loads((V778 / "CLAIM_V2_IMMUTABLE_BLOCKER_AUDIT.json").read_text(encoding="utf-8"))
    second = json.loads((V778 / "SECOND_ORDER_DEFERRED_COVERAGE_STATUS.json").read_text(encoding="utf-8"))
    assert v2["status"] == "LEGACY_BLOCKED_UNION_TYPE"
    assert v2["v2_mutated"] is False
    assert second["status"] == "DEFERRED_NOT_PROVEN"
    assert second["deferred_second_order_predicates"] == ["knows", "uncertainty"]
