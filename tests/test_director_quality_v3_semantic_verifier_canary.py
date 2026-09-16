import json
from pathlib import Path


ART = Path("artifacts")


def test_authorized_canary_is_terminal_and_exactly_one_call():
    report = (ART / "director-quality-v3-semantic-verifier-canary-final-report.md").read_text(encoding="utf-8")
    ledger = json.loads((ART / "director-quality-v3-semantic-verifier-provider-ledger.json").read_text(encoding="utf-8"))
    validation = json.loads((ART / "director-quality-v3-semantic-verifier-canary-validation.json").read_text(encoding="utf-8"))
    assert "DIRECTOR_V3_AUTHORIZED_FACT_SEMANTIC_VERIFIER_CANARY_COMPLETED" in report
    assert ledger["provider_calls"] == 1
    assert ledger["entries"][0]["written_before_dispatch"] is True
    assert validation["status"] == "PASS"
    assert validation["result_count"] == 7
    assert validation["missing_fact_ids"] == []
    assert validation["unknown_fact_ids"] == []
    assert validation["duplicate_fact_ids"] == []


def test_canary_overlay_keeps_fact_coverage_and_script_ir_blocked():
    overlay = json.loads((ART / "director-quality-v3-semantic-verifier-canary-authority-overlay.json").read_text(encoding="utf-8"))
    pointer = json.loads((ART / "director-quality-v3-current-stage-authority.json").read_text(encoding="utf-8"))
    assert overlay["fact_coverage_status"] == "NOT_YET_QUALIFIED"
    assert overlay["ready_for_script_ir_processing"] is False
    assert overlay["script_ir_processing_authorized"] is False
    assert pointer["semantic_verifier_canary"]["script_ir_calls"] == 0
    assert pointer["semantic_verifier_canary"]["downstream_calls"] == 0
