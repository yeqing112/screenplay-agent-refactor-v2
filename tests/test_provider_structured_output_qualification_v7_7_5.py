import copy

from core.provider_structured_output_qualification import (
    ANNOTATION_KEYWORDS,
    PROBE_SCHEMA_VERSION,
    STRUCTURAL_KEYWORDS,
    classify_probe,
    compile_provider_strict_schema,
    fingerprint,
    is_explicit_schema_rejection,
    minimal_probe_schema,
    provider_identity,
    qualification_fingerprint,
    strict_probe_response_format,
    validate_json_schema_subset,
)


def test_minimal_capability_schema_is_valid_and_minimal():
    schema = minimal_probe_schema()
    assert validate_json_schema_subset({"probe": "STRICT_SCHEMA_OK", "ordinal": 7}, schema)["status"] == "PASS"
    assert set(schema) == {"type", "additionalProperties", "required", "properties"}
    assert not ({"$schema", "$id", "title", "description", "$ref", "$defs"} & set(schema))


def test_strict_response_format_construction():
    response_format = strict_probe_response_format()
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == PROBE_SCHEMA_VERSION
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"] == minimal_probe_schema()


def test_additional_properties_false_enforced():
    result = validate_json_schema_subset({"probe": "STRICT_SCHEMA_OK", "ordinal": 7, "forbidden_extra": True}, minimal_probe_schema())
    assert result["status"] == "BLOCKED"
    assert "ADDITIONAL_PROPERTY:$.forbidden_extra" in result["errors"]


def test_required_field_validation_failure():
    result = validate_json_schema_subset({"probe": "STRICT_SCHEMA_OK"}, minimal_probe_schema())
    assert result["status"] == "BLOCKED"
    assert "REQUIRED_MISSING:$.ordinal" in result["errors"]


def test_wrong_enum_validation_failure():
    result = validate_json_schema_subset({"probe": "NOT_OK", "ordinal": 7}, minimal_probe_schema())
    assert result["status"] == "BLOCKED"
    assert "ENUM_MISMATCH:$.probe" in result["errors"]


def test_wrong_type_validation_failure():
    result = validate_json_schema_subset({"probe": "STRICT_SCHEMA_OK", "ordinal": True}, minimal_probe_schema())
    assert result["status"] == "BLOCKED"
    assert "TYPE_MISMATCH:$.ordinal:integer" in result["errors"]


def test_classifier_json_object_only_on_explicit_rejection():
    assert is_explicit_schema_rejection(400, "unsupported response_format json_schema")
    result = classify_probe(http_status=400, raw="unsupported json_schema", response_format_rejected=True)
    assert result["capability"] == "JSON_OBJECT_ONLY"


def test_classifier_json_schema_supported_when_response_violates_schema():
    result = classify_probe(http_status=200, finish_reason="stop", raw='{"probe":"STRICT_SCHEMA_OK","ordinal":7,"forbidden_extra":true}')
    assert result["capability"] == "JSON_SCHEMA_SUPPORTED"
    assert result["status"] == "PROVIDER_JSON_SCHEMA_STRICT_CAPABILITY_NOT_PROVEN"
    assert result["forbidden_extra_present"] is True


def test_classifier_strict_only_when_conflict_is_suppressed_and_exact_schema_passes():
    result = classify_probe(http_status=200, finish_reason="stop", raw='{"ordinal":7,"probe":"STRICT_SCHEMA_OK"}')
    assert result["capability"] == "JSON_SCHEMA_STRICT_SUPPORTED"
    assert result["strict_proven"] is True


def test_http_200_and_parseability_alone_do_not_qualify_strict():
    result = classify_probe(http_status=200, finish_reason="length", raw='{"ordinal":7,"probe":"STRICT_SCHEMA_OK"}')
    assert result["capability"] == "JSON_SCHEMA_SUPPORTED"
    assert result["strict_proven"] is False


def test_unknown_and_ambiguous_classification():
    ambiguous = classify_probe(http_status=None, raw="", transport_error="ReadTimeout")
    assert ambiguous["status"] == "PROVIDER_STRUCTURED_OUTPUT_QUALIFICATION_SUBMISSION_AMBIGUOUS"
    not_json_schema = classify_probe(http_status=200, finish_reason="stop", raw="not json")
    assert not_json_schema["capability"] == "JSON_SCHEMA_SUPPORTED"
    unknown_status = classify_probe(http_status=503, raw="unavailable")
    assert unknown_status["capability"] == "UNKNOWN"


def test_provider_identity_fingerprint_binds_profile_model_and_host():
    identity = provider_identity(profile_id="p1", provider="openai-compatible", model="m1", base_host="https://host-a")
    same = provider_identity(profile_id="p1", provider="openai-compatible", model="m1", base_host="https://host-a")
    other_host = provider_identity(profile_id="p1", provider="openai-compatible", model="m1", base_host="https://host-b")
    assert identity == same
    assert identity["provider_identity_fingerprint"] != other_host["provider_identity_fingerprint"]


def test_qualification_record_binds_identity_and_excludes_timestamp():
    identity = provider_identity(profile_id="p1", provider="openai-compatible", model="m1", base_host="https://host-a")
    args = {"identity": identity, "capability": "JSON_SCHEMA_STRICT_SUPPORTED", "probe_schema_fingerprint": fingerprint(minimal_probe_schema()), "request_fingerprint": "req", "raw_response_sha256": "raw", "qualified": True}
    first = qualification_fingerprint(**args)
    second = qualification_fingerprint(**args)
    assert first == second
    assert first["qualified"] is True
    assert first["profile_id"] == "p1"
    assert "timestamp" not in first


def test_schema_compiler_strips_internal_annotations_and_preserves_structure():
    internal = {"title": "Internal", "trust": "UNTRUSTED_PROPOSED", "type": "object", "required": ["items"], "additionalProperties": False, "properties": {"items": {"type": "array", "items": {"type": "string", "enum": ["x"]}}}}
    before = copy.deepcopy(internal)
    result = compile_provider_strict_schema(internal)
    assert result["audit"]["status"] == "PASS"
    assert result["schema"] == {"type": "object", "required": ["items"], "additionalProperties": False, "properties": {"items": {"type": "array", "items": {"type": "string", "enum": ["x"]}}}}
    assert internal == before
    assert result["audit"]["input_unchanged"] is True
    assert result["audit"]["removed_annotation_paths"]


def test_schema_compiler_is_deterministic_and_preserves_required_enum_const():
    internal = {"type": "object", "required": ["kind"], "additionalProperties": False, "properties": {"kind": {"type": "string", "enum": ["OBJECT"], "const": "OBJECT"}}}
    first = compile_provider_strict_schema(internal)
    second = compile_provider_strict_schema(internal)
    assert first["schema"] == second["schema"]
    assert first["audit"]["output_fingerprint"] == second["audit"]["output_fingerprint"]
    assert first["schema"]["required"] == ["kind"]
    assert first["schema"]["properties"]["kind"]["enum"] == ["OBJECT"]
    assert first["schema"]["properties"]["kind"]["const"] == "OBJECT"


def test_schema_compiler_rejects_dangling_refs_and_unions():
    assert compile_provider_strict_schema({"type": "object", "properties": {"x": {"$ref": "#/missing"}}})["audit"]["status"] == "BLOCKED"
    assert compile_provider_strict_schema({"type": "object", "properties": {"x": {"type": ["string", "boolean"]}}})["audit"]["status"] == "BLOCKED"


def test_schema_compiler_contract_sets_are_disjoint_and_explicit():
    assert "type" in STRUCTURAL_KEYWORDS
    assert "$schema" in ANNOTATION_KEYWORDS

