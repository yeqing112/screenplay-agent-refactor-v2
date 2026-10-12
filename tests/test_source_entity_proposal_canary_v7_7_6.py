import copy

from core.provider_structured_output_qualification import (
    compile_provider_strict_schema,
    fingerprint,
    provider_identity,
    qualification_fingerprint,
    strict_probe_response_format,
)
from core.source_entity_proposal import (
    ENTITY_PROPOSAL_VERSION,
    assign_program_owned_entity_ids,
    proposal_entity_registry,
    source_entity_proposal_schema,
    validate_entity_candidate,
    validate_entity_proposal,
)
from core.source_entity_proposal_runtime import (
    build_existing_canonical_registry,
    classify_entity_proposal_result,
    exact_existing_entity_duplicate,
    qualification_freshness_gate,
    validate_entity_evidence_binding,
    validate_entity_source_unit_binding,
    validate_entity_surface_binding,
)
from core.provider_structured_output_qualification import validate_json_schema_subset


def units_and_evidence():
    units = [
        {"unit_id": "UNIT_A", "source_type": "SOURCE_ACTION", "source_ref": "SRC_A", "source_order": 1, "source_evidence_refs": ["EV_A"], "source_evidence": {"evidence_id": "EV_A", "sha256": "HASH_A", "text": "CHAR_A finds object alpha."}},
        {"unit_id": "UNIT_B", "source_type": "SOURCE_ACTION", "source_ref": "SRC_B", "source_order": 2, "source_evidence_refs": ["EV_B"], "source_evidence": {"evidence_id": "EV_B", "sha256": "HASH_B", "text": "object beta remains in place."}},
    ]
    source_fp = "SOURCE_FP"
    package_id = "PACKAGE_A"
    anchors = []
    for unit in units:
        evidence = unit["source_evidence"]
        anchors.append({"anchor_ref": evidence["evidence_id"], "unit_id": unit["unit_id"], "source_fingerprint": source_fp, "source_package_id": package_id, "sha256": evidence["sha256"], "text": evidence["text"]})
    return units, {"anchors": anchors}, source_fp, package_id


def candidate(**overrides):
    value = {"schema_version": "source_entity_candidate_v1", "kind": "OBJECT", "surface_form": "object alpha", "evidence_refs": ["EV_A"], "source_unit_refs": ["UNIT_A"]}
    value.update(overrides)
    return value


def test_qualification_identity_and_fingerprint_match():
    identity = provider_identity(profile_id="P", provider="openai-compatible", model="M", base_host="https://host")
    qualification = qualification_fingerprint(identity=identity, capability="JSON_SCHEMA_STRICT_SUPPORTED", probe_schema_fingerprint="schema", request_fingerprint="request", raw_response_sha256="raw", qualified=True)
    gate = qualification_freshness_gate(profile_identity=identity, qualification=qualification, expected_qualification_fingerprint=qualification["qualification_fingerprint"])
    assert gate["status"] == "PASS"
    changed = {**identity, "base_host": "https://other"}
    drift = qualification_freshness_gate(profile_identity=changed, qualification=qualification, expected_qualification_fingerprint=qualification["qualification_fingerprint"])
    assert drift["status"] == "BLOCKED"
    assert "base_host" in drift["failed_checks"]


def test_entity_transport_schema_compiles_and_is_strict():
    result = compile_provider_strict_schema(source_entity_proposal_schema())
    assert result["audit"]["status"] == "PASS"
    assert result["schema"]
    assert result["schema"]["additionalProperties"] is False
    assert result["schema"]["properties"]["entities"]["items"]["additionalProperties"] is False
    assert result["audit"]["input_unchanged"] is True


def test_strict_response_format_uses_compiled_business_schema():
    schema = compile_provider_strict_schema(source_entity_proposal_schema())["schema"]
    response_format = {"type": "json_schema", "json_schema": {"name": ENTITY_PROPOSAL_VERSION, "strict": True, "schema": schema}}
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"] == schema
    assert strict_probe_response_format()["type"] == "json_schema"


def test_entity_candidate_transport_and_internal_schema_pass():
    units, index, source_fp, package_id = units_and_evidence()
    payload = {"schema_version": "source_entity_proposal_v1", "entities": [candidate()]}
    transport_schema = compile_provider_strict_schema(source_entity_proposal_schema())["schema"]
    assert validate_json_schema_subset(payload, transport_schema)["status"] == "PASS"
    internal = validate_entity_proposal(payload, evidence_index=index, source_units=units, source_fingerprint=source_fp)
    assert internal["status"] == "PASS"
    assert package_id


def test_unknown_evidence_is_blocked():
    units, index, source_fp, _ = units_and_evidence()
    result = validate_entity_candidate(candidate(evidence_refs=["EV_UNKNOWN"]), evidence_index=index, source_units=units, source_fingerprint=source_fp)
    assert result["status"] == "BLOCKED"
    assert "EVIDENCE_REF_MISSING:EV_UNKNOWN" in result["errors"]


def test_cross_unit_evidence_is_blocked():
    units, index, source_fp, package_id = units_and_evidence()
    item = candidate(source_unit_refs=["UNIT_B"])
    evidence = validate_entity_evidence_binding(item, evidence_index=index, source_fingerprint=source_fp, source_package_id=package_id)
    unit_binding = validate_entity_source_unit_binding(item, unit_evidence_map={u["unit_id"]: u["source_evidence_refs"] for u in units})
    assert evidence["status"] == "BLOCKED"
    assert unit_binding["status"] == "BLOCKED"
    assert "EVIDENCE_NOT_BOUND_TO_SOURCE_UNIT:EV_A" in evidence["errors"]


def test_surface_form_must_bind_exactly_to_at_least_one_bound_evidence():
    units, index, source_fp, _ = units_and_evidence()
    item = candidate(evidence_refs=["EV_A", "EV_B"], source_unit_refs=["UNIT_A", "UNIT_B"])
    assert validate_entity_surface_binding(item, evidence_index=index, unit_evidence_map={u["unit_id"]: u["source_evidence_refs"] for u in units})["status"] == "PASS"
    item["surface_form"] = "Object Alpha"
    assert validate_entity_surface_binding(item, evidence_index=index, unit_evidence_map={u["unit_id"]: u["source_evidence_refs"] for u in units})["status"] == "BLOCKED"


def test_provider_supplied_entity_id_is_blocked_by_strict_schema():
    item = candidate(proposal_entity_ref="PEC_0001")
    payload = {"schema_version": "source_entity_proposal_v1", "entities": [item]}
    compiled = compile_provider_strict_schema(source_entity_proposal_schema())["schema"]
    assert validate_json_schema_subset(payload, compiled)["status"] == "BLOCKED"


def test_program_owned_pec_only_for_valid_unique_candidates():
    first = candidate()
    duplicate = copy.deepcopy(first)
    next_item = candidate(surface_form="object beta", evidence_refs=["EV_B"], source_unit_refs=["UNIT_B"])
    assignment = assign_program_owned_entity_ids([first, duplicate, next_item])
    assert assignment["id_owner"] == "program"
    assert assignment["rows"][0]["proposal_entity_ref"] == "PEC_0001"
    assert assignment["rows"][1]["status"] == "BLOCKED_DUPLICATE"
    assert assignment["rows"][1]["proposal_entity_ref"] is None
    assert assignment["rows"][2]["proposal_entity_ref"] == "PEC_0002"


def test_exact_existing_canonical_duplicate_is_detected_without_fuzzy_matching():
    units, index, _, _ = units_and_evidence()
    registry = {"entities": {"CHAR_A": {"kind": "CHARACTER", "source": "script_ir", "display_forms": ["CHAR_A"], "evidence_refs": ["EV_A"], "evidence_identities": ["HASH_A"]}}}
    assert exact_existing_entity_duplicate(candidate(kind="CHARACTER", surface_form="CHAR_A"), canonical_registry=registry, evidence_index=index)["status"] == "ALREADY_CANONICAL_ENTITY"
    assert exact_existing_entity_duplicate(candidate(kind="CHARACTER", surface_form="char_a"), canonical_registry=registry, evidence_index=index)["status"] == "NOT_CANONICAL_DUPLICATE"
    assert units


def test_existing_registry_is_authority_separated_and_ref_metadata_dynamic():
    ir = {"scenes": [{"scene_id": "SC_A", "display_name": "scene display", "participants": [{"character_id": "CHAR_A", "name": "CHAR_A", "evidence": [{"evidence_id": "EV_A", "sha256": "HASH_A"}]}]}]}
    registry = build_existing_canonical_registry(base_registry={"SC_A": {"kind": "SCENE", "source": "script_ir"}, "CHAR_A": {"kind": "CHARACTER", "source": "script_ir_declared_participant"}}, script_ir=ir, source_units=[])
    assert registry["entities"]["SC_A"]["source"] == "script_ir"
    assert "scene display" in registry["entities"]["SC_A"]["display_forms"]
    assert registry["entities"]["CHAR_A"]["evidence_refs"] == ["EV_A"]
    proposal = proposal_entity_registry(canonical_entities={"CHAR_A": {"kind": "CHARACTER"}}, assigned_entities=assign_program_owned_entity_ids([candidate()]))
    assert proposal["entities"]["CHAR_A"]["authority"] == "CANONICAL_RUNTIME"
    assert proposal["entities"]["PEC_0001"]["authority"] == "UNTRUSTED_PROPOSED"


def test_empty_and_all_blocked_classifications():
    assert classify_entity_proposal_result(candidate_count=0, valid_count=0) == "SOURCE_ENTITY_PROPOSAL_EMPTY_REVIEW_REQUIRED"
    assert classify_entity_proposal_result(candidate_count=2, valid_count=0) == "SOURCE_ENTITY_PROPOSAL_BINDING_BLOCKED"


def test_registry_builder_does_not_promote_canonical_authority():
    assigned = assign_program_owned_entity_ids([candidate()])
    registry = proposal_entity_registry(canonical_entities={"CHAR_A": {"kind": "CHARACTER"}}, assigned_entities=assigned)
    assert registry["entities"]["PEC_0001"]["authority"] == "UNTRUSTED_PROPOSED"
    assert registry["entities"]["PEC_0001"]["authority"] != "CANONICAL_RUNTIME"


def test_claim_v2_union_compiler_remains_blocked():
    from core.source_entity_proposal import claim_v2_schema
    assert compile_provider_strict_schema(claim_v2_schema())["audit"]["status"] == "BLOCKED"


def test_schema_fingerprint_is_deterministic():
    schema = compile_provider_strict_schema(source_entity_proposal_schema())["schema"]
    assert fingerprint(schema) == fingerprint(copy.deepcopy(schema))
