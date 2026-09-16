from __future__ import annotations

from core.fresh_upstream_completion_audit import audit_candidate, audit_lineage, rank_candidates
from scripts.run_director_quality_v3_fresh_upstream_completion_audit import _exposure_state


def _row(**overrides):
    source = {
        "scene_id": "book1:e1:Scene",
        "book_id": 1,
        "episode": 1,
        "scene_name": "Scene",
        "source_real": True,
        "source_text": '{"name":"Scene","beats":[{"id":"B1","event":"act"}]}',
        "fingerprints": {"source_fingerprint": "SRC", "normalized_source_text_hash": "TXT", "beat_sequence_fingerprint": "BEAT"},
        "upstream": {
            "fact_snapshot": {"status": "confirmed", "id": 1, "source_fingerprint": "SRC"},
            "script_ir": {"status": "qualified", "qualified": True, "id": 2, "source_fingerprint": "SRC"},
            "director_treatment": {"status": "approved", "id": 3, "source_script_hash": "SRC"},
            "scene_blocking": {"status": "approved", "id": 4, "source_script_hash": "SRC"},
        },
    }
    source.update(overrides)
    return source


def test_exact_source_lineage_passes():
    assert audit_lineage(_row())["status"] == "EXACT"


def test_source_hash_mismatch_fails():
    row = _row(); row["upstream"]["director_treatment"]["source_script_hash"] = "OLD"
    assert audit_lineage(row)["status"] == "MISMATCH"


def test_missing_upstream_link_detected():
    row = _row(); row["upstream"]["fact_snapshot"] = {"status": "missing"}
    assert "MISSING" in [edge["lineage_status"] for edge in audit_lineage(row)["edges"]]


def test_stale_treatment_source_detected():
    row = _row(); row["upstream"]["director_treatment"]["source_script_hash"] = "OLD"
    assert "MISMATCH" in [edge["lineage_status"] for edge in audit_lineage(row)["edges"]]


def test_stale_blocking_source_detected():
    row = _row(); row["upstream"]["scene_blocking"]["source_script_hash"] = "OLD"
    assert "MISMATCH" in [edge["lineage_status"] for edge in audit_lineage(row)["edges"]]


def test_missing_creative_record_requires_provider():
    row = _row(); row["upstream"]["director_treatment"] = {"status": "missing"}; row["upstream"]["scene_blocking"] = {"status": "missing"}
    result = audit_candidate(row)
    assert result["requires_new_provider_generation"] is True


def test_missing_approval_requires_human_approval():
    row = _row(); row["upstream"]["director_treatment"] = {"status": "draft"}
    result = audit_candidate(row)
    assert result["requires_human_approval"] is True


def test_stale_source_hash_is_not_deterministically_recoverable():
    row = _row(); row["upstream"]["director_treatment"]["source_script_hash"] = "OLD"
    result = audit_candidate(row)
    assert result["completion_tier"] == "TIER_D"


def test_orphaned_downstream_record_detected():
    row = _row(); row["upstream"]["fact_snapshot"] = {"status": "missing"}; row["upstream"]["script_ir"] = {"status": "missing", "qualified": False}
    result = audit_candidate(row)
    assert "ORPHANED_DOWNSTREAM_RECORD" in result["recovery_classifications"]


def test_unknown_recovery_is_not_promoted_to_tier_a():
    row = _row(); row["upstream"]["fact_snapshot"]["source_fingerprint"] = "UNKNOWN"
    result = audit_candidate(row, exposure_resolution="EXPOSURE_UNKNOWN")
    assert result["completion_tier"] != "TIER_A"


def test_deterministic_candidate_ranking():
    a = {"scene_id": "a", "requires_new_provider_generation": False, "requires_human_approval": False, "provenance_risk": "EXACT", "deterministic_recovery_steps": [], "missing_requirements": []}
    b = {"scene_id": "b", "requires_new_provider_generation": True, "requires_human_approval": True, "provenance_risk": "MISMATCH", "deterministic_recovery_steps": [1], "missing_requirements": [1]}
    assert [x["scene_id"] for x in rank_candidates([b, a])] == ["a", "b"]


def test_no_provider_candidate_ranked_above_equivalent_deterministic_candidate():
    no_provider = {"scene_id": "a", "requires_new_provider_generation": False, "requires_human_approval": True, "provenance_risk": "EXACT", "deterministic_recovery_steps": [1], "missing_requirements": [1]}
    provider = {"scene_id": "b", "requires_new_provider_generation": True, "requires_human_approval": False, "provenance_risk": "EXACT", "deterministic_recovery_steps": [], "missing_requirements": []}
    assert rank_candidates([provider, no_provider])[0]["scene_id"] == "a"


def test_no_human_approval_candidate_ranked_above_equivalent_no_approval_candidate():
    no_approval = {"scene_id": "a", "requires_new_provider_generation": False, "requires_human_approval": False, "provenance_risk": "EXACT", "deterministic_recovery_steps": [], "missing_requirements": [1]}
    approval = {"scene_id": "b", "requires_new_provider_generation": False, "requires_human_approval": True, "provenance_risk": "EXACT", "deterministic_recovery_steps": [], "missing_requirements": [1]}
    assert rank_candidates([approval, no_approval])[0]["scene_id"] == "a"


def test_stable_hash_tie_breaker():
    a = {"scene_id": "a", "requires_new_provider_generation": False, "requires_human_approval": False, "provenance_risk": "EXACT", "deterministic_recovery_steps": [], "missing_requirements": []}
    b = {"scene_id": "b", "requires_new_provider_generation": False, "requires_human_approval": False, "provenance_risk": "EXACT", "deterministic_recovery_steps": [], "missing_requirements": []}
    assert rank_candidates([a, b]) == rank_candidates([b, a])


def test_provider_ledger_confirms_exposure():
    state, evidence, _ = _exposure_state("book1:e1:Scene", {"scenes": {"book1:e1:Scene": {"status": "EXPOSED", "evidence": [{"evidence_path": "ledger.json"}]}}})
    assert state == "EXPOSED_CONFIRMED" and evidence


def test_report_mention_alone_does_not_confirm_exposure():
    state, _, _ = _exposure_state("book1:e1:Scene", {"scenes": {"book1:e1:Scene": {"status": "EXPOSED", "evidence": []}, "report_mention": {"status": "EXPOSED"}}})
    assert state == "NOT_EXPOSED_CONFIRMED"


def test_absence_of_search_hit_does_not_prove_not_exposed():
    state, _, _ = _exposure_state("book990402:e2:unknown", {"scenes": {}})
    assert state == "EXPOSURE_UNKNOWN"


def test_exposure_unknown_remains_unknown_without_complete_coverage():
    state, _, _ = _exposure_state("book990402:e3:unknown", {"scenes": {"book990402:e3:unknown": {"status": "NOT_EXPOSED", "evidence": []}}})
    assert state == "EXPOSURE_UNKNOWN"
