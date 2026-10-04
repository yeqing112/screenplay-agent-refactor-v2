from scripts.run_75api_autonomous_asset_canary_v3 import _multi_reference_evidence, _validate_imported_master


def test_v3_reuses_only_the_proven_master():
    evidence = _validate_imported_master()
    assert evidence["status"] == "MASTER_REUSE_ALLOWED"
    assert all(evidence["checks"].values())
    assert evidence["sha256"] == "fb16b58520681d04460467ede564ab44232c629dff128cadaad2eb5e18853c1b"


def test_v3_multi_reference_evidence_requires_two_refs_and_records_data_uri():
    rows = {"LIN_WAN": {"asset_id": "LIN_WAN", "generations": {"FACE_PROFILE": {"reference_image_count": 2, "reference_order": ["LIN_WAN_MASTER", "LIN_WAN_FACE_FRONT"], "reference_image_sha256s": ["sha-master", "sha-face"], "reference_input_formats": ["data_uri", "data_uri"], "provider_payload_reference_count": 2, "provider_reference_order_matches": True, "provider_response_media_path": "url", "provider_response_fingerprint": "fp"}}}}
    evidence = _multi_reference_evidence(rows)
    assert evidence["count"] == 1
    assert evidence["data_uri_real_calls"] == 1
    assert evidence["real_multi_reference_calls"][0]["reference_count"] == 2
