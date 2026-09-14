from core.director_contract_failure import aggregate_contract_failures, classify_contract_failure


def test_contract_failure_taxonomy_maps_known_codes_and_unknowns():
    assert classify_contract_failure({"code": "DIRECTOR_FACT_OVERRIDE"}) == "FACT_OVERRIDE_ATTEMPT"
    assert classify_contract_failure({"code": "DIRECTOR_PATCH_PATH_FORBIDDEN"}) == "FORBIDDEN_PATCH_PATH"
    assert classify_contract_failure({"code": "DIRECTOR_PATCH_SCHEMA_INVALID"}) == "ENVELOPE_SCHEMA_ERROR"
    assert classify_contract_failure({"code": "PROVIDER_NEW_CODE"}) == "OTHER_KNOWN"
    assert classify_contract_failure({}) == "UNKNOWN_CONTRACT_FAILURE"


def test_contract_failure_aggregate_preserves_patch_identity():
    result = aggregate_contract_failures([
        {"code": "UNKNOWN_PLAN_SHOT_ID", "plan_shot_id": "S9", "path": "shots/S9"},
        {"code": "INVALID_PATCH_VALUE", "plan_shot_id": "S1", "path": "camera.angle"},
    ])
    assert result["total"] == 2
    assert result["counts"] == {"UNKNOWN_PLAN_SHOT_ID": 1, "INVALID_PATCH_VALUE": 1}
    assert result["failures"][0]["plan_shot_id"] == "S9"
