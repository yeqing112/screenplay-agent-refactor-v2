from core.fact_semantic_verifier import (
    FORBIDDEN_FIELDS,
    build_verifier_request,
    compile_semantic_authority,
    parse_verifier_payload,
    schema_fingerprint,
    validate_verifier_payload,
)


def _facts():
    return [
        {
            "fact_id": "FACT_0001",
            "subject_id": "宋知夏",
            "predicate": "escaped through fire pipe shaft",
            "value": "to apartment 1203",
            "evidence": [{"anchor_ref": "E0001"}],
        },
        {
            "fact_id": "FACT_0002",
            "subject_id": "宋知夏",
            "predicate": "hid storage card in umbrella handle",
            "value": "evidence from six years ago",
            "evidence": [{"anchor_ref": "E0002"}],
        },
    ]


def test_request_is_exact_fact_and_resolved_evidence_projection():
    request = build_verifier_request(
        facts=_facts(),
        machine_context=[
            {
                "fact_id": "FACT_0001",
                "resolved_evidence": [{"anchor_ref": "E0001", "excerpt": "她走进门。"}],
                "anchor_surface_classes": ["NARRATIVE_PROSE"],
                "machine_guard_findings": [],
            }
        ],
    )
    assert [row["fact_id"] for row in request["facts"]] == ["FACT_0001", "FACT_0002"]
    assert request["facts"][0]["resolved_evidence"][0]["anchor_ref"] == "E0001"
    serialized = str(request["facts"])
    assert "raw_text" not in serialized
    assert "development_forensic" not in serialized.lower()
    assert "anchors" not in request
    assert request["contract"]["schema_fingerprint"] == schema_fingerprint()


def test_validator_requires_exact_ids_and_rejects_forbidden_or_unknown_fields():
    payload = {
        "results": [
            {
                "fact_id": "FACT_0001",
                "verdict": "ENTAILED",
                "supported_components": ["escape"],
                "unsupported_components": [],
                "rationale": "supported",
                FORBIDDEN_FIELDS[0]: "must not be accepted",
            },
            {
                "fact_id": "FACT_9999",
                "verdict": "ENTAILED",
                "supported_components": [],
                "unsupported_components": [],
                "rationale": "unknown",
            },
        ]
    }
    result = validate_verifier_payload(payload, ["FACT_0001", "FACT_0002"])
    assert result["status"] == "FAIL"
    codes = {error["code"] for error in result["errors"]}
    assert "VERIFIER_FORBIDDEN_FIELD" in codes
    assert "VERIFIER_UNKNOWN_FACT_ID" in codes
    assert "VERIFIER_MISSING_FACT_ID" in codes


def test_parser_is_strict_and_does_not_repair_prose_wrapped_json():
    assert parse_verifier_payload('{"results": []}') == {"results": []}
    try:
        parse_verifier_payload("Here is the JSON: {\"results\": []}")
    except ValueError as exc:
        assert str(exc) == "VERIFIER_OUTPUT_JSON_INVALID"
    else:
        raise AssertionError("prose-wrapped provider output must fail closed")


def test_authority_compiler_keeps_deterministic_guard_precedence():
    facts = _facts()
    overlay = compile_semantic_authority(
        facts=facts,
        verifier_results=[
            {
                "fact_id": "FACT_0001",
                "verdict": "ENTAILED",
                "supported_components": ["escape"],
                "unsupported_components": [],
                "rationale": "provider observation",
            },
            {
                "fact_id": "FACT_0002",
                "verdict": "CONTRADICTED",
                "supported_components": [],
                "unsupported_components": ["intent"],
                "rationale": "contradiction",
            },
        ],
        machine_guards={"FACT_0001": {"hard_blockers": ["COMPOSITE_ATOMICITY_REVIEW_REQUIRED"]}},
    )
    assert overlay["status"] == "SEMANTIC_GROUNDING_CLOSED_WITH_REVIEW"
    assert overlay["facts"][0]["semantic_disposition"] == "AMBIGUOUS_REVIEW"
    assert overlay["facts"][0]["downstream_eligible"] is False
    assert overlay["facts"][1]["semantic_disposition"] == "CONTRADICTED_REJECTED"
    assert overlay["ready_for_script_ir_processing"] is False


def test_authority_compiler_requires_evidence_pass_before_world_confirmation():
    overlay = compile_semantic_authority(
        facts=[_facts()[0]],
        verifier_results=[{
            "fact_id": "FACT_0001",
            "verdict": "ENTAILED",
            "supported_components": ["escape"],
            "unsupported_components": [],
            "rationale": "provider observation",
        }],
        evidence_authority_status="REVIEW_REQUIRED",
    )
    row = overlay["facts"][0]
    assert row["semantic_disposition"] == "CLAIM_SUPPORTED"
    assert row["downstream_eligible"] is False
    assert "EVIDENCE_AUTHORITY_NOT_PASS" in row["machine_guard_overrides"]
