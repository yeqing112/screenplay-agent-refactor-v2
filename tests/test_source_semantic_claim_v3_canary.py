from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.provider_structured_output_qualification import compile_provider_strict_schema, validate_json_schema_subset
from core import llm
from core.source_semantic_claim_authority import MODALITIES, POLARITIES
from core.source_semantic_claim_v3 import (
    CLAIM_INPUT_ENTITY_REGISTRY_VERSION,
    CLAIM_V3_SET_VERSION,
    CLAIM_V3_VERSION,
    RELATION_SIGNATURES,
    RELATION_SIGNATURE_REGISTRY_VERSION,
    assign_program_owned_claim_ids,
    build_claim_input_entity_registry,
    claim_v3_candidate_schema,
    claim_v3_candidate_set_schema,
    count_schema_dialect_extensions,
    proposable_predicate_registry_v1,
    qualifier_registry_v2,
    relation_signature_registry_v2,
    validate_claim_v3_candidate,
    validate_claim_v3_set,
)
from core.source_semantic_claim_v3_canary import (
    EXECUTABLE_PREDICATE_REGISTRY_VERSION,
    build_claim_v3_proposal_prompt,
    build_source_claim_provider_entity_view,
    build_v7_7_8_1_forward_state_binding,
    claim_entity_kind_inventory,
    derive_executable_first_order_predicates,
    source_claim_predicate_prompt_contract,
)


ROOT = Path(__file__).resolve().parents[1]
CANARY = ROOT / "docs/canonical-canary/v7_7_8-source-semantic-claim-v3-foundation"
V777 = ROOT / "docs/canonical-canary/v7_7_7-source-entity-semantic-verification-real"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _entity_registry(rows=None):
    return {
        "schema_version": CLAIM_INPUT_ENTITY_REGISTRY_VERSION,
        "status": "PASS",
        "fingerprint": "fixture",
        "entities": rows if rows is not None else {
            "CHAR_A": {"ref": "CHAR_A", "kind": "CHARACTER", "authority": "CANONICAL_RUNTIME", "canonical": True},
            "LOC_A": {"ref": "LOC_A", "kind": "LOCATION", "authority": "CANONICAL_RUNTIME", "canonical": True},
            "OBJ_A": {"ref": "OBJ_A", "kind": "OBJECT", "authority": "CANONICAL_RUNTIME", "canonical": True},
            "DIA_A": {"ref": "DIA_A", "kind": "DIALOGUE_CONTENT", "authority": "CANONICAL_RUNTIME", "canonical": True},
        },
    }


def _candidate(**changes):
    value = {
        "schema_version": CLAIM_V3_VERSION,
        "subject_ref": "CHAR_A",
        "predicate": "speech_act",
        "object_ref": "DIA_A",
        "qualifiers": {},
        "polarity": "POSITIVE",
        "modality": "ASSERTED",
        "evidence_refs": ["EV_A"],
        "source_unit_refs": ["UNIT_A"],
    }
    value.update(changes)
    return value


def test_v7_7_8_1_forward_state_binds_exact_baseline_and_both_relation_layers():
    binding = build_v7_7_8_1_forward_state_binding(
        baseline_commit="8fe2d0f7f6c5a0a5fcb1ce791a06b0bdb9196aee",
        foundation_report={
            "foundation_state": "SOURCE_SEMANTIC_CLAIM_V3_FOUNDATION_READY",
            "next_state": "SOURCE_SEMANTIC_CLAIM_V3_PROPOSAL_CANARY_AUTHORIZATION_REQUIRED",
        },
        first_order_closure={"first_order_unresolved_count": 0},
        second_order_closure={"second_order_unresolved_count": 0, "execution_enabled": False},
    )
    assert binding["status"] == "PASS"
    assert binding["historical_recommended_next_action_is_authorization_gate"] is False


def test_verified_entity_and_claim_input_registry_fingerprints_recompute_from_frozen_evidence():
    source_registry = read_json(V777 / "SOURCE_VERIFIED_ENTITY_REGISTRY.json")
    frozen_claim_registry = read_json(CANARY / "CLAIM_INPUT_ENTITY_REGISTRY.json")
    computed = build_claim_input_entity_registry(
        source_registry,
        expected_fingerprint="88de4d7793043c11897605217c3e6a29847062eb87ac4b7bb20909b147e6b186",
    )
    assert computed["status"] == "PASS"
    assert computed["fingerprint"] == frozen_claim_registry["fingerprint"] == "877d43fc4cea05b487e50b6a4afcdb58e44f78338f1ebfcb388ecbe9b9740acb"
    assert len(computed["entities"]) == len(frozen_claim_registry["entities"]) == 19


def test_entity_kind_inventory_is_deterministic_and_has_no_synthesized_values():
    registry = read_json(CANARY / "CLAIM_INPUT_ENTITY_REGISTRY.json")
    first = claim_entity_kind_inventory(registry)
    second = claim_entity_kind_inventory(registry)
    assert first == second
    assert first["status"] == "PASS"
    assert first["kind_counts"] == {
        "CHARACTER": 2, "DIALOGUE_CONTENT": 1, "ENVIRONMENT": 2,
        "LOCATION": 2, "OBJECT": 8, "SCENE": 1,
        "TEXT_CONTENT": 2, "UNKNOWN_ENTITY": 1,
    }
    assert first["kind_counts"].get("PROPERTY_VALUE", 0) == 0
    assert first["kind_counts"].get("STATE_VALUE", 0) == 0


def test_executable_predicates_are_derived_only_from_types_and_include_dormant_reasons():
    registry = read_json(CANARY / "CLAIM_INPUT_ENTITY_REGISTRY.json")
    derived = derive_executable_first_order_predicates(relation_signature_registry_v2(), registry)
    assert derived["schema_version"] == EXECUTABLE_PREDICATE_REGISTRY_VERSION
    assert derived["status"] == "PASS"
    assert set(derived["predicates"]) == {"enter_guided", "left_by", "received_by", "speech_act"}
    assert set(derived["dormant_predicates"]) == {"has_property", "state_value"}
    assert all(row["execution_status"] == "TYPE_DEPENDENCY_UNAVAILABLE" for row in derived["dormant_predicates"].values())
    assert derived["dormant_predicates"]["has_property"]["available_object_kind_counts"] == {"PROPERTY_VALUE": 0}
    assert derived["dormant_predicates"]["state_value"]["available_object_kind_counts"] == {"STATE_VALUE": 0}
    assert derived["source_prose_consulted"] is False
    assert derived["surface_forms_consulted"] is False
    assert derived["evidence_text_consulted"] is False


def test_predicate_is_dormant_when_required_subject_kind_is_absent():
    signatures = {"schema_version": RELATION_SIGNATURE_REGISTRY_VERSION, "signatures": {"speech_act": RELATION_SIGNATURES["speech_act"]}}
    registry = _entity_registry({"DIA_A": {"kind": "DIALOGUE_CONTENT", "authority": "CANONICAL_RUNTIME"}})
    derived = derive_executable_first_order_predicates(signatures, registry)
    assert derived["status"] == "PASS"
    assert derived["predicates"] == {}
    assert derived["dormant_predicates"]["speech_act"]["execution_status"] == "TYPE_DEPENDENCY_UNAVAILABLE"
    assert derived["dormant_predicates"]["speech_act"]["available_subject_kind_counts"] == {"CHARACTER": 0}


def test_predicate_is_dormant_when_required_object_kind_is_absent():
    signatures = {"schema_version": RELATION_SIGNATURE_REGISTRY_VERSION, "signatures": {"speech_act": RELATION_SIGNATURES["speech_act"]}}
    registry = _entity_registry({"CHAR_A": {"kind": "CHARACTER", "authority": "CANONICAL_RUNTIME"}})
    derived = derive_executable_first_order_predicates(signatures, registry)
    assert derived["status"] == "PASS"
    assert derived["predicates"] == {}
    assert derived["dormant_predicates"]["speech_act"]["execution_status"] == "TYPE_DEPENDENCY_UNAVAILABLE"
    assert derived["dormant_predicates"]["speech_act"]["available_object_kind_counts"] == {"DIALOGUE_CONTENT": 0}


def test_second_order_predicates_are_excluded_from_provider_executable_registry():
    derived = derive_executable_first_order_predicates(
        relation_signature_registry_v2(), read_json(CANARY / "CLAIM_INPUT_ENTITY_REGISTRY.json")
    )
    assert not ({"knows", "uncertainty"} & set(derived["predicates"]))
    assert "VERIFIED_FIRST_ORDER_CLAIM_REF" not in json.dumps(derived)


def test_provider_entity_view_uses_frozen_forms_without_granting_identity_authority():
    input_registry = read_json(CANARY / "CLAIM_INPUT_ENTITY_REGISTRY.json")
    source_registry = read_json(V777 / "SOURCE_VERIFIED_ENTITY_REGISTRY.json")
    view = build_source_claim_provider_entity_view(input_registry, source_registry)
    assert view["status"] == "PASS"
    assert view["entity_count"] == 19
    assert set(view["entities"]["PEC_0004"]) == {"ref", "kind", "display_form", "authority"}
    assert view["entities"]["PEC_0004"]["display_form"] == source_registry["proposal_entities"]["PEC_0004"]["surface_form"]
    assert view["identity_authority"] is False
    assert view["entity_identity_derived_from_display_form"] is False


def test_predicate_prompt_contract_is_typed_versioned_and_not_story_specific():
    contract = source_claim_predicate_prompt_contract(relation_signature_registry_v2())
    assert contract["status"] == "PASS"
    assert set(contract["predicates"]) == set(RELATION_SIGNATURES)
    assert contract["predicates"]["enter_guided"]["allowed_subject_kinds"] == ["CHARACTER"]
    assert "omit" in contract["predicates"]["enter_guided"]["semantic_definition"].lower()
    assert contract["story_specific_examples"] is False
    assert contract["source_prose_used_to_define_predicates"] is False


def test_prompt_warns_against_lossy_mapping_and_only_contains_executable_predicates():
    source_units = [{
        "unit_id": "UNIT_A", "source_type": "SOURCE_ACTION", "text": "A generic source sentence.", "speaker": "Character A",
        "source_evidence": {"evidence_id": "EV_A", "text": "A generic source sentence."},
    }]
    entities = {"entities": {"CHAR_A": {"ref": "CHAR_A", "kind": "CHARACTER", "display_form": "Character A", "authority": "CANONICAL_RUNTIME"}}}
    executable = {"predicates": {"speech_act": RELATION_SIGNATURES["speech_act"]}}
    contract = source_claim_predicate_prompt_contract(relation_signature_registry_v2())
    system, user = build_claim_v3_proposal_prompt(
        source_units=source_units,
        provider_entity_view=entities,
        executable_predicate_registry=executable,
        predicate_prompt_contract=contract,
        qualifier_registry=qualifier_registry_v2(),
        polarities=POLARITIES,
        modalities=MODALITIES,
    )
    assert "Do not force source meaning into the closest available predicate" in system
    assert "A source unit may produce zero or more claims" in system
    assert '"speech_act"' in user
    assert '"enter_guided"' not in user
    assert "UNIT_A" in user and "EV_A" in user and "A generic source sentence." in user
    assert "speaker_display_form" in user and "Character A" in user
    assert "attempt-11" not in user


def test_executable_transport_schema_is_strict_and_excludes_dormant_and_second_order_predicates():
    input_registry = read_json(CANARY / "CLAIM_INPUT_ENTITY_REGISTRY.json")
    executable = derive_executable_first_order_predicates(relation_signature_registry_v2(), input_registry)
    schema = claim_v3_candidate_set_schema(candidate_schema=claim_v3_candidate_schema(input_entity_registry=input_registry, proposable_predicates=executable))
    compiled = compile_provider_strict_schema(schema)
    predicate_enum = compiled["schema"]["properties"]["claims"]["items"]["properties"]["predicate"]["enum"]
    assert compiled["audit"]["status"] == "PASS"
    assert set(predicate_enum) == set(executable["predicates"])
    assert count_schema_dialect_extensions(schema) == {"union_type": 0, "oneOf": 0, "anyOf": 0, "dangling_ref": 0}
    assert schema["additionalProperties"] is False


def test_provider_cannot_supply_entity_kinds_claim_types_or_ids():
    registry = _entity_registry()
    executable = {"status": "PASS", "predicates": {key: RELATION_SIGNATURES[key] for key in ("speech_act",)}}
    for field in ("subject_kind", "object_kind", "claim_type", "relation_class", "candidate_id", "claim_id", "source_claim_id"):
        result = validate_claim_v3_candidate(
            _candidate(**{field: "PROVIDER_CONTROLLED"}),
            input_entity_registry=registry,
            evidence_unit_bindings={"EV_A": ["UNIT_A"]},
            allowed_source_unit_refs=["UNIT_A"],
            proposable_predicates=executable,
        )
        assert result["status"] == "BLOCKED", field


def test_unknown_entity_refs_are_blocked():
    result = validate_claim_v3_candidate(
        _candidate(subject_ref="MISSING"), input_entity_registry=_entity_registry(),
        evidence_unit_bindings={"EV_A": ["UNIT_A"]}, allowed_source_unit_refs=["UNIT_A"],
    )
    assert "UNKNOWN_ENTITY_REF:MISSING" in result["errors"]


def test_non_executable_predicate_is_blocked():
    executable = {"status": "PASS", "predicates": {"speech_act": RELATION_SIGNATURES["speech_act"]}}
    result = validate_claim_v3_candidate(
        _candidate(predicate="has_property"), input_entity_registry=_entity_registry(),
        evidence_unit_bindings={"EV_A": ["UNIT_A"]}, allowed_source_unit_refs=["UNIT_A"],
        proposable_predicates=executable,
    )
    assert "PREDICATE_NOT_PROPOSABLE:has_property" in result["errors"]


@pytest.mark.parametrize(("field", "ref", "error"), [
    ("subject_ref", "OBJ_A", "RELATION_SUBJECT_KIND_MISMATCH:speech_act:OBJECT"),
    ("object_ref", "LOC_A", "RELATION_OBJECT_KIND_MISMATCH:speech_act:LOCATION"),
])
def test_wrong_relation_subject_or_object_kind_is_blocked(field, ref, error):
    result = validate_claim_v3_candidate(
        _candidate(**{field: ref}), input_entity_registry=_entity_registry(),
        evidence_unit_bindings={"EV_A": ["UNIT_A"]}, allowed_source_unit_refs=["UNIT_A"],
    )
    assert error in result["errors"]


def test_qualifier_rules_and_evidence_unit_binding_are_enforced():
    bad_qualifier = validate_claim_v3_candidate(
        _candidate(qualifiers={"confidence": "LOW"}), input_entity_registry=_entity_registry(),
        evidence_unit_bindings={"EV_A": ["UNIT_A"]}, allowed_source_unit_refs=["UNIT_A"],
    )
    assert "UNKNOWN_QUALIFIER_KEY:confidence" in bad_qualifier["errors"]
    bad_binding = validate_claim_v3_candidate(
        _candidate(), input_entity_registry=_entity_registry(),
        evidence_unit_bindings={"EV_A": ["OTHER_UNIT"]}, allowed_source_unit_refs=["UNIT_A"],
    )
    assert "EVIDENCE_UNIT_BINDING_MISMATCH:EV_A" in bad_binding["errors"]


def test_program_claim_ids_are_deterministic_and_keep_proposals_untrusted():
    validated = validate_claim_v3_set(
        {"schema_version": CLAIM_V3_SET_VERSION, "claims": [_candidate()]},
        input_entity_registry=_entity_registry(),
        evidence_unit_bindings={"EV_A": ["UNIT_A"]},
        allowed_source_unit_refs=["UNIT_A"],
    )
    assigned = assign_program_owned_claim_ids(
        validated["candidate_results"], entity_registry_fingerprint="fixture"
    )
    assert validated["status"] == "PASS"
    assert assigned["status"] == "PASS"
    assert assigned["rows"][0]["claim_id"] == "SCC_0001"
    assert assigned["rows"][0]["authority"] == "UNTRUSTED_PROPOSED"
    assert assigned["rows"][0]["canonical"] is False


def test_strict_json_schema_subset_validation_does_not_repair_or_coerce():
    input_registry = _entity_registry()
    executable = {"status": "PASS", "predicates": {"speech_act": RELATION_SIGNATURES["speech_act"]}}
    schema = claim_v3_candidate_set_schema(candidate_schema=claim_v3_candidate_schema(input_entity_registry=input_registry, proposable_predicates=executable))
    transport = compile_provider_strict_schema(schema)["schema"]
    valid = {"schema_version": CLAIM_V3_SET_VERSION, "claims": [_candidate()]}
    assert validate_json_schema_subset(valid, transport)["status"] == "PASS"
    assert validate_json_schema_subset({**valid, "unknown": True}, transport)["status"] == "BLOCKED"


def test_llm_raw_response_callback_runs_before_audit_response_parsing(monkeypatch):
    raw = '{"schema_version":"source_semantic_claim_candidate_set_v3","claims":[]}'
    order = []
    raw_values = []

    class FakeResponse:
        status_code = 200
        headers = {"x-request-id": "mock-request-id"}

        def raise_for_status(self):
            return None

        def json(self):
            return {"usage": {"total_tokens": 7}, "choices": [{"message": {"content": raw}, "finish_reason": "stop"}]}

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.delenv("E2E_EXTERNAL_RUNTIME", raising=False)
    monkeypatch.setattr(llm.httpx, "Client", lambda **_kwargs: FakeClient())
    monkeypatch.setattr(llm._limiter, "wait_if_needed", lambda *_args: None)
    monkeypatch.setattr(llm._limiter, "record", lambda *_args: None)
    result = llm.call_llm(
        "user prompt", system="system prompt", retries=1,
        estimated_tokens=7, max_tokens=128, temperature=0,
        model_profile={"id": "fixture", "provider": "openai-compatible", "model_name": "fixture", "base_url": "https://example.invalid/v1", "api_key": "fixture-secret"},
        response_format={"type": "json_schema", "json_schema": {"name": "fixture", "strict": True, "schema": {"type": "object", "additionalProperties": False, "required": [], "properties": {}}}},
        raw_response_callback=lambda value: (order.append("raw"), raw_values.append(value)),
        audit_callback=lambda _record: order.append("audit"),
    )
    assert result == raw
    assert order == ["raw", "audit"]
    assert raw_values == [raw]
