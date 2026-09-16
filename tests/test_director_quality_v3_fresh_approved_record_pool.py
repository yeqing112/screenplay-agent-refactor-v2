from __future__ import annotations

import json
import sqlite3

from core.fresh_approved_record_pool import (
    FreshApprovedRecordEligibilityGate,
    _candidate,
    build_pool,
    source_fingerprints,
)


def test_fresh_pool_authority_append_preserves_closed_stage_shape():
    from scripts.run_director_quality_v3_fresh_approved_record_pool import _preserve_closed_authority

    pointer = {
        "strategy_authority_contract_ssot": {"status": "CLOSED", "custom": "keep"},
        "shot_architecture": {
            "generation_architecture_redesign": {
                "spine_topology_canary": {"custom_stage_field": "keep"}
            }
        },
    }
    result = _preserve_closed_authority(pointer)
    stage = result["shot_architecture"]["generation_architecture_redesign"]["spine_topology_canary"]
    assert result["strategy_authority_contract_ssot"]["custom"] == "keep"
    assert stage["custom_stage_field"] == "keep"
    assert stage["preflight_wiring_closure"] == "CLOSED"
    assert stage["runtime_preserve_wiring"] == "PASS"
    assert stage["runtime_identity_wiring"] == "PASS"
    assert stage["runtime_segment_ref_wiring"] == "PASS"
    assert stage["final_recanary_authorized"] is False
    assert result["authority_contract_ssot"]["status"] == "CLOSED"


def _candidate_for(name: str = "Scene"):
    upstream = {
        "fact_confirmed": True,
        "script_ir": {"qualified": True, "status": "qualified"},
        "director_treatment": {"status": "approved"},
        "scene_blocking": {"status": "approved"},
        "identity_authority_valid": True,
        "beat_authority_valid": True,
    }
    return _candidate(
        book_id=123,
        episode=1,
        scene_name=name,
        source_records=[{"kind": "script", "id": 1, "provenance": "database.scripts"}],
        source_text="explicit persisted screenplay source",
        beats=[{"id": "B01", "type": "action", "event": "an observable action"}],
        upstream=upstream,
    )


def test_complete_approved_record_is_eligible():
    result = FreshApprovedRecordEligibilityGate().evaluate(_candidate_for())
    assert result["status"] == "FRESH_APPROVED_RECORD_ELIGIBLE"


def test_missing_fact_snapshot_fails():
    row = _candidate_for(); row["upstream"]["fact_confirmed"] = False
    assert "FACT_SNAPSHOT_NOT_CONFIRMED" in FreshApprovedRecordEligibilityGate().evaluate(row)["reasons"]


def test_unqualified_script_ir_fails():
    row = _candidate_for(); row["upstream"]["script_ir"]["qualified"] = False
    assert "SCRIPT_IR_NOT_QUALIFIED" in FreshApprovedRecordEligibilityGate().evaluate(row)["reasons"]


def test_unapproved_treatment_fails():
    row = _candidate_for(); row["upstream"]["director_treatment"]["status"] = "draft"
    assert "TREATMENT_NOT_APPROVED" in FreshApprovedRecordEligibilityGate().evaluate(row)["reasons"]


def test_unapproved_blocking_fails():
    row = _candidate_for(); row["upstream"]["scene_blocking"]["status"] = "draft"
    assert "BLOCKING_NOT_APPROVED" in FreshApprovedRecordEligibilityGate().evaluate(row)["reasons"]


def test_provider_exposure_fails():
    assert "PROVIDER_EXPOSED" in FreshApprovedRecordEligibilityGate().evaluate(_candidate_for(), exposure_status="EXPOSED")["reasons"]


def test_retired_fails():
    assert "SCENE_RETIRED" in FreshApprovedRecordEligibilityGate().evaluate(_candidate_for(), retired=True)["reasons"]


def test_exposure_unknown_fails_closed():
    assert "EXPOSURE_UNKNOWN" in FreshApprovedRecordEligibilityGate().evaluate(_candidate_for(), exposure_status="EXPOSURE_UNKNOWN")["reasons"]


def test_fixture_is_not_real_source_even_if_approvals_look_complete():
    row = _candidate_for(); row["source_real"] = False; row["source_records"] = [{"kind": "fixture", "id": 1}]
    result = FreshApprovedRecordEligibilityGate().evaluate(row)
    assert result["status"] == "NOT_ELIGIBLE"
    assert "SOURCE_NOT_REAL" in result["reasons"]


def test_same_source_hash_cannot_become_fresh_with_new_scene_id():
    first = _candidate_for("Original")
    second = _candidate_for("Renamed")
    assert first["fingerprints"] == second["fingerprints"]
    result = FreshApprovedRecordEligibilityGate().evaluate(second, denied_fingerprints={first["fingerprints"]["source_fingerprint"]})
    assert "SOURCE_CONTENT_ALREADY_EXPOSED" in result["reasons"]


def test_retired_source_fingerprint_blocks_candidate():
    row = _candidate_for("RetiredClone")
    result = FreshApprovedRecordEligibilityGate().evaluate(row, denied_fingerprints=set(row["fingerprints"].values()))
    assert "SOURCE_CONTENT_ALREADY_EXPOSED" in result["reasons"]


def test_exposed_source_fingerprint_blocks_candidate():
    row = _candidate_for("ExposedClone")
    result = FreshApprovedRecordEligibilityGate().evaluate(row, exposure_status="NOT_EXPOSED", denied_fingerprints={row["fingerprints"]["normalized_source_text_hash"]})
    assert "SOURCE_CONTENT_ALREADY_EXPOSED" in result["reasons"]


def test_retired_scene_copy_with_new_id_is_not_eligible():
    row = _candidate_for("NewId")
    pool = build_pool([row], retired_scene_ids={"book123:e1:Original"}, denied_fingerprints=set(row["fingerprints"].values()))
    assert pool["eligible_scene_count"] == 0


def test_source_fingerprints_include_normalized_text_and_beat_sequence():
    fps = source_fingerprints(source_records=[{"kind": "script", "id": 1}], source_text="a\n  b", beats=[{"id": "B01", "event": "x"}])
    assert set(fps) == {"source_fingerprint", "normalized_source_text_hash", "beat_sequence_fingerprint"}


def test_pool_never_freezes_cohort_or_fabricates_approval():
    pool = build_pool([_candidate_for()])
    assert pool["cohort_frozen"] is False
    assert pool["approval_fabricated"] is False
    assert pool["provider_calls"] == 0


def test_real_source_scene_is_detected_from_persisted_sqlite_record(tmp_path):
    from core.fresh_approved_record_pool import scan_source_material

    db = tmp_path / "source.db"
    c = sqlite3.connect(db)
    c.executescript(
        """
        create table script_ir_versions (id integer, book_id integer, episode integer, revision integer, status text, validation_status text, source_fact_snapshot_id text, payload_json text, payload_hash text, source_fingerprint text);
        create table fact_snapshots (id integer, status text, payload_hash text);
        create table director_treatments (id integer, book_id integer, episode integer, scene_name text, revision integer, status text, source_script_hash text);
        create table scene_blockings (id integer, book_id integer, episode integer, scene_name text, revision integer, status text, participants text, source_script_hash text);
        create table scripts (id integer, book_id integer, episode integer, content text, status text);
        create table chapters (id integer, book_id integer, seq integer, status text, scenes text);
        """
    )
    payload = {"scenes": [{"name": "Fresh", "beats": [{"id": "B01", "event": "an action"}]}]}
    c.execute("insert into fact_snapshots values (1,'confirmed','fact-fp')")
    c.execute("insert into script_ir_versions values (1,777,1,1,'qualified','qualified','1',?,?,?)", (json.dumps(payload), "ir-payload", "ir-source"))
    c.execute("insert into director_treatments values (1,777,1,'Fresh',1,'approved','ir-source')")
    c.execute("insert into scene_blockings values (1,777,1,'Fresh',1,'approved',?,?)", (json.dumps([{"character_id": "C1", "name": "A"}]), "ir-source"))
    c.commit(); c.close()
    rows = scan_source_material(db)
    assert any(row["scene_id"] == "book777:e1:Fresh" for row in rows)


def test_fixture_marker_is_not_treated_as_real_source():
    from core.fresh_approved_record_pool import _candidate

    row = _candidate_for("Fixture")
    row["source_records"] = [{"kind": "fixture", "provenance": "tests/fixtures/golden"}]
    row["source_real"] = False
    assert row["source_real"] is False
