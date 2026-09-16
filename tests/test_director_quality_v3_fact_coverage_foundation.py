import json
from pathlib import Path


ART = Path("artifacts")


def test_authority_reconciliation_uses_three_historical_attempts_without_rewriting_lineage():
    authority = json.loads((ART / "director-quality-v3-current-stage-authority.json").read_text(encoding="utf-8"))
    evaluation = authority["authorized_ai_evaluation_source"]
    assert evaluation["provider_attempts_by_stage"] == {"fact_attempt_1": 1, "fact_attempt_2": 1, "semantic_verifier": 1}
    assert evaluation["cumulative_provider_attempts"] == 3
    assert evaluation["current_stage_provider_attempts"] == 0
    assert evaluation["semantic_grounding_status"] == "SEMANTIC_GROUNDING_CLOSED_WITH_REVIEW"
    assert evaluation["effective_lineage_state"] == "FACT_SEMANTICS_ADJUDICATED"
    assert evaluation["historical_attempt_2_lineage"] == "FACT_SNAPSHOT_CONFIRMED"
    assert evaluation["fact_coverage_status"] == "NOT_YET_QUALIFIED"
    assert evaluation["ready_for_fact_coverage_qualification"] is True
    assert evaluation["script_ir_processing_authorized"] is False


def test_foundation_is_provider_free_and_coverage_verifier_not_authorized():
    readiness = json.loads((ART / "director-quality-v3-fact-coverage-foundation-readiness.json").read_text(encoding="utf-8"))
    foundation = json.loads((ART / "director-quality-v3-current-stage-authority.json").read_text(encoding="utf-8"))["fact_coverage_foundation"]
    assert readiness["provider_calls"] == 0
    assert readiness["status"] == "CLOSED"
    assert readiness["coverage_verifier_ready"] is True
    assert readiness["coverage_verifier_authorized"] is False
    assert foundation["provider_component_prose_authority"] is False
    assert foundation["script_ir_gate"] == "BLOCKED_PENDING_FACT_COVERAGE"


def test_development_preview_is_not_qualification():
    preview = json.loads((ART / "director-quality-v3-fact-coverage-development-preview.json").read_text(encoding="utf-8"))
    assert preview["development_only"] is True
    assert preview["runtime_authority"] is False
    assert preview["qualification_status"] == "NOT_ADJUDICATED"
    assert preview["development_gap_count"] > 0
    assert preview["fact_count_diagnostic"] == 7


def test_narrative_unit_index_is_coarse_and_non_semantic():
    index = json.loads((ART / "director-quality-v3-source-narrative-unit-index-preview.json").read_text(encoding="utf-8"))
    assert index["provider_calls"] == 0
    assert index["semantic_interpretation"] is False
    assert index["full_anchor_count"] == 347
    assert index["anchor_count"] == 12
    assert index["unit_count"] <= index["anchor_count"]
    assert all(row["unit_id"].startswith("NU_") and row["anchor_refs"] for row in index["units"])


def test_full_source_narrative_unit_closure_covers_all_347_anchors():
    completeness = json.loads((ART / "director-quality-v3-full-source-narrative-unit-completeness.json").read_text(encoding="utf-8"))
    assert completeness["status"] == "PASS"
    assert completeness["input_anchor_count"] == 347
    assert completeness["indexed_anchor_count"] == 347
    assert completeness["unique_indexed_anchor_count"] == 347
    assert completeness["missing_anchor_refs"] == []
    assert completeness["duplicate_anchor_refs"] == []
    assert completeness["unknown_anchor_refs"] == []
    assert completeness["first_anchor_ref"] == "E0001"
    assert completeness["last_anchor_ref"] == "E0347"
    assert completeness["first_anchor_indexed"] is True
    assert completeness["last_anchor_indexed"] is True
    assert completeness["unit_ids_contiguous"] is True
    assert completeness["source_order_contiguous"] is True
    assert completeness["source_order_preserved"] is True
    assert completeness["char_order_stable"] is True
    assert completeness["trailing_unanchored_chars"] == 0


def test_full_source_closure_parity_is_runtime_safe_and_provider_free():
    parity = json.loads((ART / "director-quality-v3-current-stage-authority-parity.json").read_text(encoding="utf-8"))
    readiness = json.loads((ART / "director-quality-v3-coverage-verifier-readiness-after-full-source.json").read_text(encoding="utf-8"))
    authority = json.loads((ART / "director-quality-v3-current-stage-authority.json").read_text(encoding="utf-8"))
    assert parity["status"] == "PASS" and parity["provider_calls"] == 0
    node = authority["fact_semantic_grounding"]
    assert node["runtime_authority"] is True
    assert node["semantic_verifier_authorized"] is False
    assert node["semantic_verifier_historical_authorization_consumed"] is True
    assert node["script_ir_gate"] == "BLOCKED_PENDING_FACT_COVERAGE"
    assert readiness["status"] == "READY_NOT_AUTHORIZED"
    assert readiness["coverage_verifier_ready"] is True
    assert readiness["coverage_verifier_authorized"] is False
    assert readiness["fact_coverage_qualified"] is False


def test_full_source_development_preview_is_not_qualification():
    preview = json.loads((ART / "director-quality-v3-full-source-coverage-development-preview.json").read_text(encoding="utf-8"))
    assert preview["full_source"] is True
    assert preview["development_only"] is True
    assert preview["runtime_authority"] is False
    assert preview["qualification_status"] == "NOT_ADJUDICATED"
    assert preview["source_unit_index_fingerprint"] == preview["narrative_unit_index_fingerprint"]
