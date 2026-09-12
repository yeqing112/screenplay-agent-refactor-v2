from core.local_repair import apply_local_repair, rollback_local_repair


def test_local_repair_records_before_after_fingerprints():
    result = apply_local_repair({"shots": [{"duration": 4}]}, {"target_layer": "SHOT_PLAN", "patch": [{"op": "replace", "path": "/shots/0/duration", "value": 6}]})
    assert result["changed"] is True
    assert result["issue_code"] == ""
    assert result["patch"][0]["op"] == "replace"
    assert result["before_fingerprint"] != result["after_fingerprint"]
    assert result["candidate"]["shots"][0]["duration"] == 6
    restored = rollback_local_repair(result, expected_fingerprint=result["after_fingerprint"])
    assert restored["candidate"]["shots"][0]["duration"] == 4
