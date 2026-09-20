"""Regression evidence for the Phase D reuse and stale immutability closure."""
from __future__ import annotations

import json
from pathlib import Path


ART = Path(__file__).resolve().parents[1] / "artifacts" / "e2e-production-pilot"


def _trace():
    return json.loads((ART / "episode_01_phase_d_trace.json").read_text(encoding="utf-8"))


def test_untouched_fresh_set_reuses_identity_without_duplicates():
    evidence = _trace()["idempotency"]
    assert evidence["same_set"] is True
    assert evidence["same_pointer"] is True
    assert evidence["no_duplicate_storyboard_shots"] is True
    assert all(call["reused"] is True for call in evidence["calls"])


def test_direct_materialization_tamper_cases_fail_closed_and_remain_stale():
    cases = {item["case"]: item for item in _trace()["negative_cases"]}
    for name in (
        "semantic_tamper_then_materialize",
        "prompt_tamper_then_materialize",
        "projection_tamper_then_materialize",
        "handoff_tamper_then_materialize",
        "set_fingerprint_tamper_then_materialize",
    ):
        result = cases[name]["result"]
        assert result["status_code"] == 409
        assert result["detail"]["reused"] is False
        assert cases[name]["set_after"]["stale_status"] == "STALE"


def test_resolver_stale_then_materialize_cannot_reactivate_or_replace_set():
    case = next(item for item in _trace()["negative_cases"] if item["case"] == "resolver_stale_then_materialize")
    assert case["result"]["materialize"]["status_code"] == 409
    assert case["result"]["materialize"]["detail"]["code"] == "STORYBOARD_MATERIALIZATION_STALE"
    assert case["set_after"]["stale_status"] == "STALE"
    assert case["before"]["set_count"] == case["after"]["set_count"]
    assert case["set_id_after"] == case["set_id_before"]
    assert case["stale_status_after"] == "STALE"


def test_pointer_recovery_only_attaches_a_fully_validated_fresh_set():
    cases = {item["case"]: item for item in _trace()["negative_cases"]}
    fresh = cases["pointer_recovery_fresh"]
    assert fresh["materialize_result"]["reused"] is True
    assert fresh["set_id_after"] == fresh["set_id_before"]
    assert fresh["pointer_after"] != fresh["pointer_before"]
    assert fresh["stale_status_after"] == "FRESH"

    tampered = cases["tampered_set_pointer_deleted"]
    assert tampered["materialize_result"]["status_code"] == 409
    assert tampered["materialize_result"]["detail"]["reused"] is False
    assert tampered["set_id_after"] is None
    assert tampered["stale_status_after"] == "STALE"


def test_reuse_path_uses_shared_validator_and_has_no_stale_reactivation_assignment():
    api = (Path(__file__).resolve().parents[1] / "api" / "storyboard_materializer_api.py").read_text(encoding="utf-8")
    assert "validate_current_materialization_authority" in api
    assert 'set_row.status = "MATERIALIZED"' not in api
    assert 'set_row.stale_status = "FRESH"' not in api
    assert 'set_row.stale_reasons = "[]"' not in api
