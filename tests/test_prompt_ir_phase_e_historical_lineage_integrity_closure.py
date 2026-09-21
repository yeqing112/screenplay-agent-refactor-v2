"""Evidence-backed Phase E historical lineage and CI execution closure tests."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts" / "e2e-production-pilot"


def _trace() -> dict:
    return json.loads((ART / "episode_01_phase_e_trace.json").read_text(encoding="utf-8"))


def _audit() -> dict:
    return json.loads((ART / "phase_e_historical_lineage_integrity_audit.json").read_text(encoding="utf-8"))


def test_clean_historical_integrity_and_obsolete_asset_revision_are_valid():
    result = _audit()["historical_integrity"]
    assert result["clean_current"] == "PASS"
    assert result["clean_obsolete_asset_revision"] == "PASS"


def test_semantic_tamper_plus_asset_revision_fails_closed_without_writes():
    result = _trace()["historical_integrity_validation"]["semantic_tamper_plus_asset_revision"]
    assert result["status"] == "FAIL_CLOSED"
    assert result["result"]["status_code"] == 409
    assert result["result"]["detail"]["code"] == "PROMPT_IR_HISTORICAL_SEMANTIC_MISMATCH"
    assert result["counts_unchanged"] is True
    assert result["pointers_unchanged"] is True
    assert result["historical_probe"]["integrity_valid"] is False
    assert result["historical_probe"]["tamper_camera_after_commit"]["movement"] == "HISTORICAL_TAMPER"


def test_semantic_tamper_plus_policy_revision_fails_closed_without_writes():
    result = _trace()["historical_integrity_validation"]["semantic_tamper_plus_policy_revision"]
    assert result["status"] == "FAIL_CLOSED"
    assert result["result"]["status_code"] == 409
    assert result["counts_unchanged"] is True
    assert result["pointers_unchanged"] is True


def test_missing_and_fingerprinted_historical_objects_fail_closed():
    result = _audit()["historical_integrity"]
    assert result["historical_asset_missing"] == "FAIL_CLOSED"
    assert result["historical_asset_tamper"] == "FAIL_CLOSED"
    assert result["historical_storyboard_tamper"] == "FAIL_CLOSED"


def test_historical_lookup_is_exact_and_never_latest_fallback():
    audit = _audit()
    assert audit["historical_latest_fallback"] is False
    source = (ROOT / "core" / "prompt_ir_phase_e.py").read_text(encoding="utf-8")
    validator = source.split("def validate_prompt_ir_historical_integrity", 1)[1].split("def compare_prompt_ir_lineage_to_current", 1)[0]
    assert "filter_by(id=int(set_id)" in validator
    assert "filter_by(id=version_id" in validator


def test_historical_probe_has_no_provider_side_effects():
    audit = _audit()
    assert audit["provider_calls"] == 0
    assert audit["llm_calls"] == 0
    assert audit["image_calls"] == 0
    assert audit["video_calls"] == 0
    assert audit["db_migration_added"] == 0


def test_ci_installs_pytest_before_production_regression():
    workflow = (ROOT / ".github" / "workflows" / "production-regression.yml").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements-test.txt").read_text(encoding="utf-8")
    assert "pip install -r requirements-test.txt" in workflow
    assert "pytest==8.4.2" in requirements

