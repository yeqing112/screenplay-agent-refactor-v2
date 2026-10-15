from __future__ import annotations

import json
from pathlib import Path

from core.provider_structured_output_qualification import compile_provider_strict_schema
from core.source_semantic_claim_authority import MODALITIES, POLARITIES
from core.source_semantic_claim_v3 import (
    build_claim_input_entity_registry,
    claim_v3_candidate_schema,
    claim_v3_candidate_set_schema,
    count_schema_dialect_extensions,
    qualifier_registry_v2,
    relation_signature_registry_v2,
)
from core.source_semantic_claim_v3_1 import qualifier_registry_v3, relation_signature_registry_v3
from core.source_semantic_claim_v3_2 import (
    PROPOSAL_ATTEMPT_ID,
    assign_reproposal_claim_ids,
    build_reproposal_prompt,
    predicate_prompt_contract_v3_2,
    provider_entity_ref_qualifier_domain_audit,
    provider_predicate_registry_v3,
    qualifier_registry_v4,
    relation_signature_registry_v4,
    role_ref_constraint_contract_v1,
    validate_provider_candidate_v3_2,
    validate_relation_role_ref_constraints,
)


ROOT = Path(__file__).resolve().parents[1]
V779 = ROOT / "docs/canonical-canary/v7_7_9-source-semantic-claim-v3-first-order-proposal-real"
V7791 = ROOT / "docs/canonical-canary/v7_7_9_1-first-order-claim-contract-reconciliation"
V778 = ROOT / "docs/canonical-canary/v7_7_8-source-semantic-claim-v3-foundation"
V777 = ROOT / "docs/canonical-canary/v7_7_7-source-entity-semantic-verification-real"
V71 = ROOT / "docs/canonical-canary/v7_1-director-source-grounded-authoring-contract"


def entities():
    return {"schema_version": "source_claim_input_entity_registry_v1", "status": "PASS", "entities": {
        "CHAR_A": {"ref": "CHAR_A", "kind": "CHARACTER", "authority": "CANONICAL_RUNTIME"},
        "CHAR_B": {"ref": "CHAR_B", "kind": "CHARACTER", "authority": "CANONICAL_RUNTIME"},
        "LOC_X": {"ref": "LOC_X", "kind": "LOCATION", "authority": "CANONICAL_RUNTIME"},
        "OBJ_X": {"ref": "OBJ_X", "kind": "OBJECT", "authority": "CANONICAL_RUNTIME"},
    }}


def candidate(predicate="enter_guided", *, subject="CHAR_A", obj="LOC_X", qualifiers=None, **extra):
    row = {
        "schema_version": "source_semantic_claim_candidate_v3",
        "subject_ref": subject,
        "predicate": predicate,
        "object_ref": obj,
        "qualifiers": qualifiers if qualifiers is not None else {"guided_character": "CHAR_B"},
        "polarity": "POSITIVE",
        "modality": "ASSERTED",
        "evidence_refs": ["EV1"],
        "source_unit_refs": ["UNIT1"],
    }
    row.update(extra)
    return row


def base_registry():
    return provider_predicate_registry_v3(
        relation_registry=relation_signature_registry_v4(),
        qualifier_registry=qualifier_registry_v4(),
        entity_registry=entities(),
    )


def validate(row):
    return validate_provider_candidate_v3_2(
        row,
        provider_registry=base_registry(),
        relation_registry=relation_signature_registry_v4(),
        entity_registry=entities(),
        qualifier_registry=qualifier_registry_v4(),
        evidence_unit_bindings={"EV1": ["UNIT1"]},
        allowed_source_unit_refs=["UNIT1"],
    )


def test_historical_v7_7_9_reproducibility_and_partial_freeze_remain_unchanged():
    raw = json.loads((V779 / "SOURCE_CLAIM_V3_RAW_FORENSIC.json").read_text(encoding="utf-8"))
    old_proposal = json.loads((V779 / "SOURCE_CLAIM_V3_PROPOSAL_SET.json").read_text(encoding="utf-8"))
    old_contract = json.loads((V7791 / "PROPOSAL_OWNERSHIP_CLASSIFICATION.json").read_text(encoding="utf-8"))
    assert raw["raw_response_sha256"] == "44730220ba61ce249d1ebd5b87e3a0373b4cc220e58b7f96eef04a5b06f40585"
    assert old_proposal["status"] == "SOURCE_SEMANTIC_CLAIM_V3_PROPOSAL_PARTIAL"
    assert old_contract["counts"] == {"PROVIDER_PROPOSABLE": 5, "PROGRAM_DETERMINISTIC": 1, "DEFERRED_SECOND_ORDER": 2}
    assert old_contract["classes"]["PROGRAM_DETERMINISTIC"] == ["speech_act"]


def test_new_execution_registries_are_isolated_from_historical_v2_and_v3():
    old2_relation = relation_signature_registry_v2()
    old2_qualifier = qualifier_registry_v2()
    old3_relation = relation_signature_registry_v3()
    old3_qualifier = qualifier_registry_v3()
    before = json.dumps([old2_relation, old2_qualifier, old3_relation, old3_qualifier], sort_keys=True)
    new_rel = relation_signature_registry_v4()
    new_qual = qualifier_registry_v4()
    after = json.dumps([relation_signature_registry_v2(), qualifier_registry_v2(), relation_signature_registry_v3(), qualifier_registry_v3()], sort_keys=True)
    assert new_rel["schema_version"] == "source_claim_relation_signature_registry_v4"
    assert new_qual["schema_version"] == "source_claim_qualifier_registry_v4"
    assert before == after


def test_provider_ownership_surface_excludes_speech_act_and_story_companion():
    registry = base_registry()
    relation = relation_signature_registry_v4()
    assert registry["schema_version"] == "source_claim_proposal_predicate_registry_v3"
    assert set(registry["predicates"]) == {"enter_guided", "left_by", "received_by"}
    assert set(registry["dormant_predicates"]) == {"has_property", "state_value"}
    assert registry["program_deterministic_predicates"] == ["speech_act"]
    assert "speech_act" not in registry["predicates"]
    assert relation["signatures"]["speech_act"]["provider_proposable"] is False


def test_guided_character_is_required_and_character_typed():
    sig = relation_signature_registry_v4()["signatures"]["enter_guided"]
    q = qualifier_registry_v4()["qualifiers"]
    assert sig["required_qualifier_keys"] == ["guided_character"]
    assert sig["qualifier_entity_kind_constraints"] == {"guided_character": ["CHARACTER"]}
    assert q == {"guided_character": {"value_type": "ENTITY_REF"}}


def test_guided_character_missing_or_wrong_kind_is_blocked():
    missing = validate(candidate(qualifiers={}))
    wrong_kind = validate(candidate(qualifiers={"guided_character": "LOC_X"}))
    assert "REQUIRED_QUALIFIER_MISSING:enter_guided:guided_character" in missing["errors"]
    assert "QUALIFIER_ENTITY_KIND_MISMATCH:guided_character:LOCATION" in wrong_kind["errors"]


def test_same_character_cannot_guide_itself():
    result = validate(candidate(subject="CHAR_A", qualifiers={"guided_character": "CHAR_A"}))
    assert result["status"] == "BLOCKED"
    assert "RELATION_REF_CONSTRAINT_VIOLATION:enter_guided:subject_ref:qualifier_ref:guided_character" in result["errors"]


def test_distinct_guide_and_guided_character_pass_typed_gate_only():
    result = validate(candidate(subject="CHAR_A", qualifiers={"guided_character": "CHAR_B"}))
    assert result["status"] == "PASS"
    assert result["verifier_eligible"] is False
    assert result["authority"] == "UNTRUSTED_PROPOSED"
    assert result["canonical"] is False
    assert result["projection"]["object"] == {"ref": "LOC_X", "kind": "LOCATION"}


def test_role_constraint_validator_is_generic_for_not_equal():
    result = validate_relation_role_ref_constraints(
        claim={"predicate": "any_relation", "subject_ref": "R1", "object_ref": "O1"},
        signature={"predicate": "any_relation", "ref_constraints": [{"operator": "NOT_EQUAL", "left_role": "subject_ref", "right_role": "qualifier_ref:recipient"}]},
        typed_qualifiers={"recipient": {"value_type": "ENTITY_REF", "ref": "R1", "kind": "CHARACTER"}},
    )
    assert result["status"] == "BLOCKED"
    assert result["errors"] == ["RELATION_REF_CONSTRAINT_VIOLATION:any_relation:subject_ref:qualifier_ref:recipient"]
    assert role_ref_constraint_contract_v1()["supported_operators"] == ["NOT_EQUAL"]


def test_destination_qualifier_is_rejected_for_enter_guided():
    result = validate(candidate(qualifiers={"guided_character": "CHAR_B", "destination": "LOC_X"}))
    assert result["status"] == "BLOCKED"
    assert "QUALIFIER_NOT_PROVIDER_WRITABLE:destination" in result["errors"]


def test_provider_entity_ref_qualifier_domains_are_complete():
    audit = provider_entity_ref_qualifier_domain_audit(
        qualifier_registry=qualifier_registry_v4(), relation_registry=relation_signature_registry_v4(),
    )
    assert audit["status"] == "PASS"
    assert audit["unresolved_entity_ref_qualifier_domain_count"] == 0
    assert audit["rows"] == [{
        "predicate": "enter_guided", "qualifier": "guided_character", "value_type": "ENTITY_REF",
        "allowed_entity_kinds": ["CHARACTER"], "status": "PASS",
    }]


def test_entity_ref_qualifier_without_domain_blocks_generic_domain_audit():
    relation = relation_signature_registry_v4()
    relation["signatures"]["received_by"]["allowed_qualifier_keys"] = ["transfer_source"]
    q = qualifier_registry_v4()
    q["qualifiers"]["transfer_source"] = {"value_type": "ENTITY_REF"}
    result = provider_entity_ref_qualifier_domain_audit(qualifier_registry=q, relation_registry=relation)
    assert result["status"] == "BLOCKED"
    assert result["unresolved_entity_ref_qualifier_domain_count"] == 1
    assert "PROVIDER_ENTITY_REF_QUALIFIER_DOMAIN_MISSING:received_by:transfer_source" in result["errors"]


def test_transfer_source_is_deferred_not_guessed_or_provider_writable():
    q = qualifier_registry_v4()
    relation = relation_signature_registry_v4()["signatures"]["received_by"]
    assert "transfer_source" not in q["qualifiers"]
    assert q["excluded_from_current_provider_surface"]["transfer_source"] == "ENTITY_REF_DOMAIN_UNRESOLVED"
    assert relation["allowed_qualifier_keys"] == []


def test_received_by_with_empty_qualifiers_passes_and_transfer_source_blocks():
    empty = candidate("received_by", obj="OBJ_X", qualifiers={})
    assert validate(empty)["status"] == "PASS"
    transfer = candidate("received_by", obj="OBJ_X", qualifiers={"transfer_source": "CHAR_B"})
    result = validate(transfer)
    assert result["status"] == "BLOCKED"
    assert "QUALIFIER_NOT_PROVIDER_WRITABLE:transfer_source" in result["errors"]


def test_left_by_qualifiers_must_be_empty():
    empty = candidate("left_by", obj="OBJ_X", qualifiers={})
    assert validate(empty)["status"] == "PASS"
    nonempty = candidate("left_by", obj="OBJ_X", qualifiers={"anything": "x"})
    assert "QUALIFIER_NOT_PROVIDER_WRITABLE:anything" in validate(nonempty)["errors"]


def test_speech_act_is_rejected_as_not_provider_proposable():
    row = candidate("speech_act", obj="OBJ_X", qualifiers={})
    result = validate(row)
    assert result["status"] == "BLOCKED"
    assert "PREDICATE_NOT_PROVIDER_PROPOSABLE:speech_act" in result["errors"]


def test_current_runtime_executability_keeps_dormant_value_relations():
    registry = provider_predicate_registry_v3(
        relation_registry=relation_signature_registry_v4(),
        qualifier_registry=qualifier_registry_v4(), entity_registry=entities(),
    )
    assert set(registry["predicates"]) == {"enter_guided", "left_by", "received_by"}
    assert set(registry["dormant_predicates"]) == {"has_property", "state_value"}
    assert registry["dormant_predicates"]["has_property"]["available_object_kind_counts"] == {"PROPERTY_VALUE": 0}
    assert registry["dormant_predicates"]["state_value"]["available_object_kind_counts"] == {"STATE_VALUE": 0}
    assert all(row["execution_status"] == "TYPE_DEPENDENCY_UNAVAILABLE" for row in registry["dormant_predicates"].values())


def test_strict_reproposal_transport_schema_is_dynamic_and_has_no_extensions():
    source_registry = json.loads((V777 / "SOURCE_VERIFIED_ENTITY_REGISTRY.json").read_text(encoding="utf-8"))
    entity_registry = build_claim_input_entity_registry(source_registry, expected_fingerprint="88de4d7793043c11897605217c3e6a29847062eb87ac4b7bb20909b147e6b186")
    registry = provider_predicate_registry_v3(relation_registry=relation_signature_registry_v4(), qualifier_registry=qualifier_registry_v4(), entity_registry=entity_registry)
    schema = claim_v3_candidate_set_schema(candidate_schema=claim_v3_candidate_schema(input_entity_registry=entity_registry, proposable_predicates=registry))
    compiled = compile_provider_strict_schema(schema)
    counts = count_schema_dialect_extensions(schema)
    item = schema["properties"]["claims"]["items"]
    assert compiled["audit"]["status"] == "PASS"
    assert item["additionalProperties"] is False
    assert item["properties"]["predicate"]["enum"] == sorted(registry["predicates"])
    assert "speech_act" not in item["properties"]["predicate"]["enum"]
    assert counts == {"union_type": 0, "oneOf": 0, "anyOf": 0, "dangling_ref": 0}


def test_prompt_contains_only_runtime_executable_predicates_and_no_speech_surface():
    source_contract = json.loads((V71 / "SOURCE_AUTHORING_UNIT_CONTRACT.json").read_text(encoding="utf-8"))
    entities_registry = json.loads((V7791 / "SOURCE_SPEECH_ACT_BINDING_REGISTRY.json").read_text(encoding="utf-8"))
    del entities_registry  # companion evidence is deliberately separate from provider prompt data
    entity_view = json.loads((V779 / "SOURCE_CLAIM_PROVIDER_ENTITY_VIEW.json").read_text(encoding="utf-8"))
    input_registry = json.loads((V778 / "CLAIM_INPUT_ENTITY_REGISTRY.json").read_text(encoding="utf-8"))
    relation = relation_signature_registry_v4()
    q = qualifier_registry_v4()
    registry = provider_predicate_registry_v3(relation_registry=relation, qualifier_registry=q, entity_registry=input_registry)
    contract = predicate_prompt_contract_v3_2(relation)
    assert contract["status"] == "PASS"
    assert "speech_act" not in contract["predicates"]
    system, user = build_reproposal_prompt(
        source_units=source_contract["units"], provider_entity_view=entity_view,
        provider_registry=registry, predicate_contract=contract, qualifier_registry=q,
        polarities=POLARITIES, modalities=MODALITIES,
    )
    prompt = system + user
    assert '"enter_guided"' in prompt and '"left_by"' in prompt and '"received_by"' in prompt
    for forbidden in ("speech_act", "speaker_binding", "has_property", "state_value", "knows", "uncertainty"):
        assert forbidden not in prompt
    assert "Do not infer who transferred it" in prompt
    assert "Do not force meaning into the closest predicate" in system


def test_predicate_definitions_are_generic_and_model_argument_roles_explicitly():
    contract = predicate_prompt_contract_v3_2(relation_signature_registry_v4())
    guided = contract["predicates"]["enter_guided"]["semantic_definition"]
    received = contract["predicates"]["received_by"]["semantic_definition"]
    assert "subject_ref is the guide" in guided and "object_ref is the destination" in guided
    assert "guided_character is the guided person" in guided and "All three roles are required" in guided
    assert "Do not infer who transferred it" in received
    serialized = json.dumps(contract, ensure_ascii=False)
    for story_literal in ("顾沉", "林晚", "暗房", "车票", "铁盒"):
        assert story_literal not in serialized


def test_program_speech_act_companion_is_freshness_only_and_not_in_provider_raw():
    companion = json.loads((V7791 / "SOURCE_SPEECH_ACT_BINDING_REGISTRY.json").read_text(encoding="utf-8"))
    deterministic = json.loads((V7791 / "SOURCE_SPEECH_ACT_DETERMINISTIC_CONTRACT.json").read_text(encoding="utf-8"))
    assert companion["binding_count"] == 1
    assert companion["status"] == "PASS"
    assert deterministic["proves_dialogue_proposition_truth"] is False
    assert deterministic["creates_world_fact"] is False


def test_scc_assignment_is_deterministic_new_attempt_scoped_and_never_reuses_old_id():
    one = candidate()
    two = candidate("received_by", obj="OBJ_X", qualifiers={})
    valid_results = [validate(one), validate(two)]
    first = assign_reproposal_claim_ids(valid_results, entity_registry_fingerprint="entity-fp")
    second = assign_reproposal_claim_ids(list(reversed(valid_results)), entity_registry_fingerprint="entity-fp")
    assert first["status"] == "PASS"
    assert first["candidate_fingerprint_ordering"] == second["candidate_fingerprint_ordering"]
    ids = [row["claim_id"] for row in first["rows"]]
    assert ids == ["SCC_V7_7_10_0001", "SCC_V7_7_10_0002"]
    assert all(row["authority"] == "UNTRUSTED_PROPOSED" and row["canonical"] is False for row in first["rows"])
    assert first["proposal_attempt_id"] == PROPOSAL_ATTEMPT_ID
    assert first["historical_ids_reused"] is False


def test_claim_v2_second_order_and_completeness_freezes_remain_intact():
    v2 = json.loads((V778 / "CLAIM_V2_IMMUTABLE_BLOCKER_AUDIT.json").read_text(encoding="utf-8"))
    v31 = json.loads((V7791 / "PROPOSAL_OWNERSHIP_CLASSIFICATION.json").read_text(encoding="utf-8"))
    freeze = json.loads((V7791 / "NO_PROVIDER_NO_PRODUCTION_WRITE_AUDIT.json").read_text(encoding="utf-8"))
    assert v2["status"] == "LEGACY_BLOCKED_UNION_TYPE"
    assert v2["v2_mutated"] is False
    assert set(v31["classes"]["DEFERRED_SECOND_ORDER"]) == {"knows", "uncertainty"}
    assert freeze["entity_semantic_completeness"] == "NOT_PROVEN"
    assert freeze["claim_proposal_completeness"] == "NOT_PROVEN"
    assert freeze["second_order_epistemic_coverage"] == "DEFERRED_NOT_PROVEN"
    assert freeze["typed_director_requirement_manifest"] == "MISSING"


def test_frozen_entity_and_source_registry_fingerprints_are_current():
    source_registry = json.loads((V777 / "SOURCE_VERIFIED_ENTITY_REGISTRY.json").read_text(encoding="utf-8"))
    input_registry = build_claim_input_entity_registry(source_registry)
    frozen = json.loads((V778 / "CLAIM_INPUT_ENTITY_REGISTRY.json").read_text(encoding="utf-8"))
    source_freeze = json.loads((V779 / "SOURCE_CLAIM_V3_INPUT_FREEZE.json").read_text(encoding="utf-8"))
    assert source_registry["fingerprint"] == "88de4d7793043c11897605217c3e6a29847062eb87ac4b7bb20909b147e6b186"
    assert input_registry["fingerprint"] == frozen["fingerprint"] == "877d43fc4cea05b487e50b6a4afcdb58e44f78338f1ebfcb388ecbe9b9740acb"
    assert source_freeze["origin_source_raw_hash"] == "190ab63c632ca47ae6c6fa224c1fad9622eca49218ef9f14c3fa18ce98641cb1"
    assert source_freeze["source_unit_count"] == 12
    assert source_freeze["source_unit_fingerprint"] == "2089dccea46d2392a328335a75266f1c982a66a4d53cda5c502f748fbf95e37f"
