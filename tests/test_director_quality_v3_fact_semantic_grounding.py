from __future__ import annotations

import json
from pathlib import Path


ART = Path("artifacts")


def test_semantic_foundation_artifacts_are_provider_free_and_fail_closed():
    readiness = json.loads((ART / "director-quality-v3-fact-semantic-grounding-readiness.json").read_text(encoding="utf-8"))
    authority = json.loads((ART / "director-quality-v3-current-stage-authority.json").read_text(encoding="utf-8"))
    assert readiness["provider_calls"] == 0
    assert readiness["semantic_foundation_ready"] is True
    assert readiness["semantic_verifier_authorized"] is False
    assert readiness["script_ir_authorized"] is False
    assert authority["fact_semantic_grounding"]["script_ir_gate"] == "BLOCKED_PENDING_FACT_COVERAGE"
    assert authority["fact_semantic_grounding"]["runtime_authority"] is True


def test_attempt2_evidence_authority_and_semantic_overlay_are_distinct():
    result = json.loads((ART / "director-quality-v3-fact-evidence-attempt2-result.json").read_text(encoding="utf-8"))
    overlay = json.loads((ART / "director-quality-v3-fact-semantic-grounding-attempt2-overlay.json").read_text(encoding="utf-8"))
    assert result["report"]["status"] == "PASS"
    assert result["report"]["total_facts"] == 7
    assert result["report"]["evidence_invalid"] == 0
    assert overlay["evidence_authority_v2"] == "PASS"
    assert overlay["semantic_grounding_status"] == "NOT_YET_ADJUDICATED"
    assert overlay["script_ir_eligible"] is False
    assert overlay["runtime_authority"] is False


def test_historical_attempt1_and_attempt2_lineage_remain_preserved():
    authority = json.loads((ART / "director-quality-v3-current-stage-authority.json").read_text(encoding="utf-8"))
    evaluation = authority["authorized_ai_evaluation_source"]
    assert evaluation["phase_a_attempt_1_status"] == "FAILED"
    assert evaluation["attempt_1_fact_count"] == 36
    assert evaluation["attempt_1_evidence_invalid"] == 36
    assert evaluation["historical_attempt_2_lineage"] == "FACT_SNAPSHOT_CONFIRMED"
    assert evaluation["effective_lineage_state"] == "FACT_SEMANTICS_ADJUDICATED"
    assert evaluation["semantic_grounding_status"] == "SEMANTIC_GROUNDING_CLOSED_WITH_REVIEW"
