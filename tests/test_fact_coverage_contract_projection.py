import json

import pytest

from core.fact_coverage_verifier import (
    build_provider_contract_projection_v1,
    build_provider_system_prompt_v3,
    build_request,
    contract_v3,
    parse_provider_json_envelope_v1,
    provider_schema_v3,
    validate_final_provider_payload_projection,
    validate_provider_contract_projection_v1,
    validate_provider_payload,
)


def _inputs():
    units = {"units": [{"source_unit_ref": "NU_0001", "exact_text": "example"}, {"source_unit_ref": "NU_0002", "exact_text": "example 2"}]}
    facts = {"facts": [{"fact_id": "FACT_0001", "semantic_disposition": "WORLD_FACT_CONFIRMED"}]}
    return units, facts


def test_full_schema_is_projected_to_provider_request():
    units, facts = _inputs()
    request = build_request(units=units, facts=facts, contract=contract_v3(), provider="openai-compatible", model="mimo-v2.5")
    projection = request["output_contract"]
    assert validate_provider_contract_projection_v1(projection)["status"] == "PASS"
    assert projection["json_schema"] == provider_schema_v3()
    assert projection["json_schema"]["additionalProperties"] is False


@pytest.mark.parametrize("top_key, fields", [
    ("requirements", {"proposal_key", "requirement_type", "description", "source_unit_refs"}),
    ("coverage_claims", {"requirement_key", "fact_refs", "coverage_verdict"}),
    ("unit_assessments", {"source_unit_ref", "relevance", "requirement_keys"}),
])
def test_provider_request_contains_nested_schema_fields(top_key, fields):
    projection = build_provider_contract_projection_v1(contract=contract_v3(), unit_count=5, fact_count=7)
    nested = projection["json_schema"]["properties"][top_key]["items"]
    assert set(nested["required"]) == fields
    assert nested["additionalProperties"] is False


def test_schema_fingerprint_matches_projected_schema():
    projection = build_provider_contract_projection_v1(contract=contract_v3(), unit_count=5, fact_count=7)
    assert validate_provider_contract_projection_v1(projection)["status"] == "PASS"
    projection["json_schema"]["properties"]["requirements"]["items"]["properties"]["description"]["minLength"] = 2
    assert validate_provider_contract_projection_v1(projection)["status"] == "FAIL"


def test_final_transport_payload_retains_full_schema():
    units, facts = _inputs()
    request = build_request(units=units, facts=facts, contract=contract_v3(), provider="openai-compatible", model="mimo-v2.5")
    system = build_provider_system_prompt_v3(request["output_contract"])
    result = validate_final_provider_payload_projection(user_prompt=json.dumps(request, ensure_ascii=False), system_prompt=system)
    assert result["status"] == "PASS"
    assert result["visible_unit_count"] == 2
    assert result["visible_fact_count"] == 1


def test_prompt_requires_single_json_object_and_synthetic_shape():
    projection = build_provider_contract_projection_v1(contract=contract_v3(), unit_count=5, fact_count=7)
    prompt = build_provider_system_prompt_v3(projection)
    assert "OUTPUT FORMAT IS A HARD CONTRACT" in prompt
    assert "Do not use Markdown fences" in prompt
    assert "synthetic" in prompt.lower()
    assert "FACT_0001" in prompt  # shape only, not source-specific content


def test_envelope_raw_json_object_parses():
    payload = {"requirements": [], "coverage_claims": [], "unit_assessments": []}
    assert parse_provider_json_envelope_v1(json.dumps(payload)) == payload


def test_single_json_fence_can_be_unwrapped_without_semantic_repair():
    payload = {"requirements": [], "coverage_claims": [], "unit_assessments": []}
    raw = "```json\n" + json.dumps(payload) + "\n```"
    assert parse_provider_json_envelope_v1(raw) == payload


@pytest.mark.parametrize("raw", [
    "prefix\n```json\n{}\n```",
    "```json\n{}\n```\nsuffix",
    "```json\n{}\n```\n```json\n{}\n```",
])
def test_envelope_with_extra_prose_or_multiple_fences_rejected(raw):
    with pytest.raises(ValueError):
        parse_provider_json_envelope_v1(raw)


def test_historical_legacy_shape_fails_v2_schema_without_auto_conversion():
    legacy = {
        "requirements": [{"proposal_key": "P001", "requirement_type": "EVENT_OCCURRENCE", "description": "x", "source_unit_refs": ["NU_0001"]}],
        "coverage_claims": [{"claim": "x", "status": "covered", "evidence_units": ["NU_0001"]}],
        "unit_relevances": [{"unit": "NU_0001", "status": "relevant"}],
    }
    result = validate_provider_payload(legacy, unit_refs=["NU_0001"], fact_ids=["FACT_0001"])
    assert result["status"] == "FAIL"
    assert not result["requirements"] or result["coverage_claims"] == []


def test_missing_fact_refs_and_unit_assessments_are_not_filled():
    payload = {"requirements": [{"proposal_key": "P001", "requirement_type": "EVENT_OCCURRENCE", "description": "x", "source_unit_refs": ["NU_0001"]}], "coverage_claims": [{"requirement_key": "P001", "fact_refs": [], "coverage_verdict": "MISSING"}], "unit_assessments": []}
    result = validate_provider_payload(payload, unit_refs=["NU_0001"], fact_ids=["FACT_0001"])
    codes = {error["code"] for error in result["errors"]}
    assert "UNIT_ASSESSMENTS_DO_NOT_MATCH_ALL_UNITS" in codes


def test_final_transport_gate_fails_when_schema_is_dropped():
    result = validate_final_provider_payload_projection(
        user_prompt=json.dumps({"source_narrative_units": [], "existing_facts": []}),
        system_prompt="OUTPUT FORMAT IS A HARD CONTRACT",
    )
    assert result["status"] == "FAIL"
    assert any(error["code"] == "PROJECTION_NOT_OBJECT" for error in result["errors"])

