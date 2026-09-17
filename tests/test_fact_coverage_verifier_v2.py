from core.fact_coverage_verifier import (
    build_request,
    canonicalize_requirements,
    compile_fact_coverage_authority_v2,
    contract_v2,
    materialize_units,
    provider_schema_v2,
    validate_provider_payload,
)


def _units():
    raw = b"alpha\nbeta"
    return materialize_units(narrative_index={"units": [{"unit_id": "NU_0001", "source_order": 1, "char_start": 0, "char_end": 11, "anchor_refs": ["E0001"], "exact_text_hash": ""}]}, raw_bytes=raw, source_raw_hash="h")


def _valid_payload():
    return {
        "requirements": [{"proposal_key": "P001", "requirement_type": "EVENT_OCCURRENCE", "description": "An event must be ordered.", "source_unit_refs": ["NU_0001"]}],
        "coverage_claims": [{"requirement_key": "P001", "fact_refs": ["FACT_0001"], "coverage_verdict": "COVERED"}],
        "unit_assessments": [{"source_unit_ref": "NU_0001", "relevance": "RELEVANT", "requirement_keys": ["P001"]}],
    }


def test_schema_v2_uses_temporary_keys_and_provider_cannot_own_req_ids():
    contract = contract_v2()
    assert contract["schema_version"] == "fact_coverage_verifier_v2"
    assert contract["temporary_proposal_key_pattern"] == r"^P[0-9]{3}$"
    assert "canonical_requirement_id" in contract["program_owns"]
    assert "canonical_requirement_id" in contract["forbidden_provider_fields"]
    assert provider_schema_v2()["required"] == ["requirements", "coverage_claims", "unit_assessments"]


def test_valid_payload_canonicalizes_deterministically_and_requires_all_units():
    payload = _valid_payload()
    validation = validate_provider_payload(payload, unit_refs=["NU_0001"], fact_ids=["FACT_0001"])
    assert validation["status"] == "PASS"
    canonical = canonicalize_requirements(validation)
    assert canonical["mapping"] == {"P001": "REQ_0001"}
    assert canonical["requirements"][0]["requirement_id"] == "REQ_0001"


def test_unit_materialization_is_exact_and_hash_bound():
    raw = b"alpha\nbeta"
    import hashlib
    expected = hashlib.sha256(raw.decode("utf-8").encode("utf-8")).hexdigest()
    result = materialize_units(narrative_index={"units": [{"unit_id": "NU_0001", "source_order": 1, "char_start": 0, "char_end": len(raw), "anchor_refs": ["E0001"], "exact_text_hash": expected}]}, raw_bytes=raw, source_raw_hash="raw-hash")
    assert result["status"] == "PASS"
    assert result["units"][0]["exact_text"] == "alpha\nbeta"
    assert result["units"][0]["source_raw_hash"] == "raw-hash"


def test_provider_cannot_emit_canonical_ids_or_unknown_refs():
    payload = _valid_payload()
    payload["requirements"][0]["canonical_requirement_id"] = "REQ_0001"
    payload["coverage_claims"][0]["fact_refs"] = ["FACT_0099"]
    payload["unit_assessments"][0]["source_unit_ref"] = "NU_0002"
    validation = validate_provider_payload(payload, unit_refs=["NU_0001"], fact_ids=["FACT_0001"])
    codes = {error["code"] for error in validation["errors"]}
    assert "FORBIDDEN_PROVIDER_FIELDS" in codes
    assert "UNKNOWN_FACT_REF" in codes
    assert "UNKNOWN_UNIT_ASSESSMENT" in codes


def test_missing_claim_and_duplicate_unit_assessment_fail_closed():
    payload = _valid_payload()
    payload["coverage_claims"] = []
    payload["unit_assessments"].append(dict(payload["unit_assessments"][0]))
    validation = validate_provider_payload(payload, unit_refs=["NU_0001"], fact_ids=["FACT_0001"])
    codes = {error["code"] for error in validation["errors"]}
    assert "COVERAGE_CLAIMS_DO_NOT_MATCH_PROPOSALS" in codes
    assert "DUPLICATE_UNIT_ASSESSMENT" in codes


def test_authority_compiler_applies_semantic_ceiling():
    validation = validate_provider_payload(_valid_payload(), unit_refs=["NU_0001"], fact_ids=["FACT_0001"])
    canonical = canonicalize_requirements(validation)
    matrix = compile_fact_coverage_authority_v2(canonical=canonical, semantic_overlay={"facts": [{"fact_id": "FACT_0001", "semantic_disposition": "CLAIM_SUPPORTED"}]}, unit_assessments=validation["unit_assessments"])
    assert matrix["rows"][0]["final_coverage_status"] == "CLAIM_ONLY"
    assert matrix["qualification_status"] == "FACT_COVERAGE_INSUFFICIENT"
