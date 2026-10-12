import copy

from core.source_entity_proposal import (
    CLAIM_V2_FORBIDDEN_FIELDS,
    ENTITY_FORBIDDEN_FIELDS,
    ENTITY_KINDS,
    assign_program_owned_claim_ids,
    assign_program_owned_entity_ids,
    claim_v2_schema,
    entity_candidate_fingerprint,
    proposal_entity_registry,
    resolve_structured_output_capability,
    source_entity_proposal_schema,
    structured_output_capability_contract,
    structured_response_format,
    validate_claim_v2_candidate,
    validate_entity_candidate,
    validate_entity_proposal,
)


def evidence_fixture():
    units = [{"unit_id": "UNIT_1", "text": "CHAR_A finds object alpha near LOC_Y."}]
    index = {"anchors": [{"anchor_ref": "EV_1", "unit_id": "UNIT_1", "source_fingerprint": "SRC_FP", "text": units[0]["text"]}]}
    return units, index


def entity_candidate():
    return {"schema_version": "source_entity_candidate_v1", "kind": "OBJECT", "surface_form": "object alpha", "evidence_refs": ["EV_1"], "source_unit_refs": ["UNIT_1"]}


def claim_candidate():
    return {"schema_version": "source_semantic_claim_candidate_v2", "subject": {"kind": "CHARACTER", "ref": "CHAR_A"}, "predicate": "has_property", "object": {"kind": "OBJECT", "ref": "PEC_0001"}, "qualifiers": {}, "polarity": "POSITIVE", "modality": "ASSERTED", "evidence_refs": ["EV_1"], "source_unit_refs": ["UNIT_1"]}


def test_entity_candidate_schema_and_evidence_binding_pass():
    units, index = evidence_fixture()
    assert validate_entity_candidate(entity_candidate(), evidence_index=index, source_units=units, source_fingerprint="SRC_FP")["status"] == "PASS"


def test_surface_form_must_exist_exactly_in_evidence():
    units, index = evidence_fixture()
    candidate = entity_candidate()
    candidate["surface_form"] = "object beta"
    result = validate_entity_candidate(candidate, evidence_index=index, source_units=units, source_fingerprint="SRC_FP")
    assert result["status"] == "BLOCKED"
    assert "SURFACE_FORM_NOT_IN_EVIDENCE:EV_1" in result["errors"]


def test_entity_binding_rejects_stale_and_cross_unit_evidence():
    units, index = evidence_fixture()
    candidate = entity_candidate()
    candidate["source_unit_refs"] = ["UNIT_2"]
    index["anchors"][0]["source_fingerprint"] = "OLD_FP"
    result = validate_entity_candidate(candidate, evidence_index=index, source_units=units, source_fingerprint="SRC_FP")
    assert result["status"] == "BLOCKED"
    assert "EVIDENCE_STALE:EV_1" in result["errors"]
    assert "EVIDENCE_NOT_BOUND_TO_SOURCE_UNIT:EV_1" in result["errors"]
    assert "SOURCE_UNIT_REF_MISSING:UNIT_2" in result["errors"]


def test_entity_forbidden_authority_fields_are_rejected():
    units, index = evidence_fixture()
    candidate = entity_candidate()
    candidate["canonical_entity_id"] = "CHAR_A"
    result = validate_entity_candidate(candidate, evidence_index=index, source_units=units, source_fingerprint="SRC_FP")
    assert result["status"] == "BLOCKED"
    assert "ENTITY_EXTRA_FIELD:canonical_entity_id" in result["errors"]
    assert "canonical_entity_id" in ENTITY_FORBIDDEN_FIELDS


def test_entity_proposal_wrapper_is_strict():
    units, index = evidence_fixture()
    result = validate_entity_proposal({"schema_version": "source_entity_proposal_v1", "entities": [entity_candidate()]}, evidence_index=index, source_units=units, source_fingerprint="SRC_FP")
    assert result["status"] == "PASS"
    bad = {"schema_version": "source_entity_proposal_v1", "entities": [entity_candidate()], "extra": True}
    assert validate_entity_proposal(bad, evidence_index=index, source_units=units)["status"] == "BLOCKED"


def test_program_owned_entity_id_is_deterministic_and_provider_free():
    candidate = entity_candidate()
    first = assign_program_owned_entity_ids([candidate])
    second = assign_program_owned_entity_ids([candidate])
    assert first == second
    assert first["rows"][0]["proposal_entity_ref"] == "PEC_0001"
    assert first["provider_supplied_id"] is False


def test_entity_duplicate_detection_is_exact_only():
    candidate = entity_candidate()
    duplicate = copy.deepcopy(candidate)
    result = assign_program_owned_entity_ids([candidate, duplicate])
    assert result["rows"][1]["status"] == "BLOCKED_DUPLICATE"
    variant = copy.deepcopy(candidate)
    variant["surface_form"] = "Object alpha"
    assert assign_program_owned_entity_ids([candidate, variant])["rows"][1]["status"] == "PROPOSED"


def test_proposal_registry_keeps_canonical_and_proposed_authority_distinct():
    assigned = assign_program_owned_entity_ids([entity_candidate()])
    registry = proposal_entity_registry(canonical_entities={"CHAR_A": {"kind": "CHARACTER"}}, assigned_entities=assigned)
    assert registry["entities"]["CHAR_A"]["authority"] == "CANONICAL_RUNTIME"
    assert registry["entities"]["PEC_0001"]["authority"] == "UNTRUSTED_PROPOSED"


def test_claim_v2_passes_with_registry_refs():
    registry = {"CHAR_A": {"kind": "CHARACTER"}, "PEC_0001": {"kind": "OBJECT"}}
    units, index = evidence_fixture()
    assert validate_claim_v2_candidate(claim_candidate(), entity_registry=registry, evidence_index=index, source_units=units, source_fingerprint="SRC_FP")["status"] == "PASS"


def test_claim_v2_rejects_free_text_subject_and_object():
    candidate = claim_candidate()
    candidate["subject"] = "CHAR_A"
    candidate["object"] = "object alpha"
    result = validate_claim_v2_candidate(candidate, entity_registry={"CHAR_A": {"kind": "CHARACTER"}, "PEC_0001": {"kind": "OBJECT"}})
    assert result["status"] == "BLOCKED"
    assert "SUBJECT_REF_MUST_BE_OBJECT" in result["errors"]
    assert "OBJECT_REF_MUST_BE_OBJECT" in result["errors"]


def test_claim_v2_rejects_unknown_entity_ref_and_provider_id_injection():
    candidate = claim_candidate()
    candidate["subject"]["ref"] = "PEC_9999"
    candidate["candidate_id"] = "SCC_0001"
    result = validate_claim_v2_candidate(candidate, entity_registry={"CHAR_A": {"kind": "CHARACTER"}, "PEC_0001": {"kind": "OBJECT"}})
    assert result["status"] == "BLOCKED"
    assert "UNKNOWN_ENTITY_REF:PEC_9999" in result["errors"]
    assert "CLAIM_V2_EXTRA_FIELD:candidate_id" in result["errors"]
    assert "candidate_id" in CLAIM_V2_FORBIDDEN_FIELDS


def test_program_owned_claim_id_is_assigned_after_validation():
    result = assign_program_owned_claim_ids([claim_candidate()], validation_rows=[{"status": "PASS"}])
    assert result["rows"][0]["claim_id"] == "SCC_0001"
    assert result["provider_supplied_id"] is False


def _refs_are_self_contained(schema):
    refs = []
    def walk(value):
        if isinstance(value, dict):
            if "$ref" in value:
                refs.append(value["$ref"])
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(schema)
    defs = schema.get("$defs", {})
    return all(ref.startswith("#/$defs/") and ref.split("/", 2)[-1] in defs for ref in refs)


def test_json_schemas_are_self_contained_and_strict():
    entity_schema = source_entity_proposal_schema()
    claim_schema = claim_v2_schema()
    assert entity_schema["additionalProperties"] is False
    assert claim_schema["additionalProperties"] is False
    assert entity_schema["properties"]["entities"]["items"]["type"] == "object"
    assert _refs_are_self_contained(entity_schema)
    assert _refs_are_self_contained(claim_schema)
    assert claim_schema["properties"]["claims"]["items"]["additionalProperties"] is False


def test_structured_output_capability_unknown_and_object_only_fail_closed():
    assert resolve_structured_output_capability({})["state"] == "UNKNOWN"
    assert resolve_structured_output_capability({"structured_output_capability": "JSON_OBJECT_ONLY"})["authorization_allowed"] is False
    assert resolve_structured_output_capability({"structured_output_capability": "JSON_SCHEMA_SUPPORTED"})["authorization_allowed"] is False
    assert resolve_structured_output_capability({"structured_output_capability": "JSON_SCHEMA_STRICT_SUPPORTED"})["authorization_allowed"] is True


def test_response_format_preview_contains_schema_and_strict_flag():
    preview = structured_response_format(source_entity_proposal_schema(), name="source_entity_proposal_v1")
    assert preview["type"] == "json_schema"
    assert preview["json_schema"]["strict"] is True
    assert preview["json_schema"]["schema"]["$id"] == "source_entity_proposal_v1"


def test_capability_contract_lists_required_states_and_unknown_policy():
    contract = structured_output_capability_contract()
    assert set(contract["states"]) == {"JSON_OBJECT_ONLY", "JSON_SCHEMA_SUPPORTED", "JSON_SCHEMA_STRICT_SUPPORTED", "UNKNOWN"}
    assert contract["unknown_is_fail_closed"] is True


def test_generic_entity_kinds_are_story_neutral():
    assert "OBJECT" in ENTITY_KINDS
    assert "IRON_BOX" not in ENTITY_KINDS
    assert "TICKET" not in ENTITY_KINDS


def test_different_display_prose_does_not_change_typed_result():
    typed = entity_candidate()
    display_a = {"display_prose": "first arbitrary prose", "typed": typed}
    display_b = {"display_prose": "second unrelated prose", "typed": typed}
    assert assign_program_owned_entity_ids([display_a["typed"]]) == assign_program_owned_entity_ids([display_b["typed"]])


def test_entity_fingerprint_stability():
    candidate = entity_candidate()
    assert entity_candidate_fingerprint(candidate) == entity_candidate_fingerprint(copy.deepcopy(candidate))
