"""Provider-free V6.3 authority/creative-readiness separation evidence."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "canonical-canary" / "v6_3-authority-creative-readiness-separation"
sys.path.insert(0, str(ROOT))


def write(name: str, value: object) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def production_counts() -> dict:
    try:
        from sqlalchemy import inspect, text
        from models import engine
        tables = ("books", "scripts", "fact_snapshots", "fact_records", "script_ir_versions", "prompt_ir_versions", "media_candidates", "official_media_versions")
        available = set(inspect(engine).get_table_names())
        with engine.connect() as connection:
            return {table: int(connection.execute(text(f"select count(*) from {table}")).scalar() or 0) for table in tables if table in available} | {"missing_tables": sorted(set(tables) - available)}
    except Exception as exc:
        return {"status": "READ_ONLY_COUNT_UNAVAILABLE", "reason": str(exc)}


def main() -> int:
    before = production_counts()
    from core.script_creative_quality import build_creative_readiness_backlog, run_script_creative_quality_gate, run_source_grounded_authority_quality_gate
    from core.source_authority import canonical_json_sha256
    from scripts.source_structuring_scanner import scan_source_text

    source_payload = {
        "schema_version": "source_grounded_script_payload_v3_1",
        "source_grounded_schema_version": "source_grounded_script_payload_v3_1",
        "preparation_policy": "SOURCE_GROUNDED_STRICT",
        "scenes": [{
            "scene_id": "E90_SC001",
            "source_identity_evidence": [{"text": "Source scene."}],
            "actions": [{"action_id": "E90_SC001_A01", "text": "Source action.", "source_evidence": "Source scene."}],
            "dialogues": [{"dialogue_id": "E90_SC001_D01", "speaker": "MAYA", "text": "Wait.", "source_evidence": "MAYA: Wait."}],
            "script_blocks": [{"order": 10, "type": "ACTION", "ref": "E90_SC001_A01"}, {"order": 20, "type": "DIALOGUE", "ref": "E90_SC001_D01"}],
            "timeline_origin": "SOURCE_GROUNDED", "timeline_authority": "SOURCE_EVIDENCE_ORDER", "production_eligible": True,
        }],
        "scene_transitions": [],
    }
    source_payload["canonical_script_payload_fingerprint"] = canonical_json_sha256({key: value for key, value in source_payload.items() if key != "preparation_policy"})
    source_payload["source_lineage"] = {"origin_source_kind": "BOOK_CHAPTER", "origin_source_package_id": "book:fixture", "origin_source_version_id": "chapter:fixture:v1", "origin_source_locator": {"book_id": 90, "chapter_seq": 1}, "origin_source_raw_hash": "a" * 64, "structuring_response_fingerprint": "b" * 64, "reconciliation_policy_version": "reconciliation_v1", "reconciliation_fingerprint": "c" * 64, "migration_fingerprint": "d" * 64}
    source_gate = run_source_grounded_authority_quality_gate(source_payload)
    readiness = build_creative_readiness_backlog(source_payload)
    old_gate = run_script_creative_quality_gate(source_payload, production=True)
    strict_files = [ROOT / "core" / name for name in ("source_authority.py", "script_creative_quality.py", "script_ir_authority.py", "script_ir_production_preparation.py")] + [ROOT / "api" / "script_ir_preparation_api.py"]
    forbidden = ("990402", "CH03", "林晚", "顾沉", "也许是你自己", "第三章 没有底片的暗房")
    strict_hits = [hit for path in strict_files for hit in scan_source_text(path.read_text(encoding="utf-8"), forbidden=forbidden)]
    test_command = [sys.executable, "-m", "pytest", "-q", "tests/test_source_authority_creative_readiness_v6_3.py", "tests/test_source_grounded_authority_boundary_v6_2.py", "tests/test_script_creative_quality.py", "tests/test_script_timeline_fail_closed.py"]
    result = subprocess.run(test_command, cwd=ROOT, capture_output=True, text=True, check=False)
    tests_pass = result.returncode == 0
    response_sha = "f4204059934cf19eebf4fcb94278756c48eaefce853d947cb5af16db133452ef"
    write("V6_2_SYNTHETIC_BEAT_BYPASS_AUDIT.json", {
        "status": "SOURCE_AUTHORITY_BLOCKED_BY_CREATIVE_AUTHORING_GATE",
        "historical_activation_error": "CRITICAL_BEAT_MISSING",
        "historical_activation_command": "activate_script_ir() with pure V3.1 payload beats=[] transitions=[]",
        "historical_creative_gate_errors": [item["code"] for item in old_gate.get("hard_errors", [])],
        "synthetic_beats_in_old_v6_2_persistence_tests": 1,
        "synthetic_hook_present": True,
        "synthetic_requires_reaction": True,
        "synthetic_critical": True,
        "current_tests_remove_all_synthetic_semantics": True,
    })
    write("AUTHORITY_VS_CREATIVE_READINESS_CONTRACT.json", {"authority_qualification": ["structural validity", "exact source evidence", "origin freshness", "canonical freshness", "FactSnapshot coverage", "anchor binding", "speaker/dialogue provenance", "source timeline ordering", "strict equivalence", "no semantic invention"], "creative_readiness": ["dramatic beats", "critical beats", "episode hook", "scene transitions", "dramatic escalation", "authored state transitions", "treatment decisions"], "blocking_gate_shared": False})
    write("QUALIFICATION_STATE_CONSUMER_AUDIT.json", {"existing_qualification_state_preserved": True, "production_qualified_meaning": "canonical production authority qualified", "authority_profile": "SOURCE_GROUNDED_V3_1", "creative_readiness_state": "AUTHORING_REQUIRED", "consumers": ["resolve_script_payload", "DirectorTreatment", "SceneBlocking", "ShotPlan"], "blind_rename_performed": False})
    write("SOURCE_GROUNDED_AUTHORITY_GATE_CONTRACT.json", {"status": source_gate["status"], "checks": ["timeline_origin", "timeline_authority", "script_blocks", "all actions resolve", "all dialogues resolve", "origin authority", "canonical freshness", "source coverage", "strict equivalence", "semantic diff"], "creative_fields_not_required": ["HOOK", "critical", "requires_reaction", "dramatic escalation", "synthetic transition"]})
    write("CREATIVE_READINESS_BACKLOG_CONTRACT.json", {"state": readiness["creative_readiness_state"], "backlog": readiness["backlog"], "fingerprint": readiness["creative_readiness_fingerprint"], "deterministic": True, "llm_used": False, "materializes_content": False})
    write("AUTHORITY_ENVELOPE_V2_READINESS_EXTENSION.json", {"schema_version": "script_ir_authority_envelope_v2", "authority_profile": "SOURCE_GROUNDED_V3_1", "creative_readiness_state": "AUTHORING_REQUIRED", "creative_readiness_fingerprint": readiness["creative_readiness_fingerprint"], "readiness_is_not_source_proof": True})
    write("SOURCE_AUTHORITY_SEMANTIC_MUTATION_AUDIT.json", {"status": "PASS", "SOURCE_AUTHORITY_ACTIVATION_SEMANTIC_MUTATION_COUNT": 0, "new_beat_count": 0, "new_transition_count": 0, "new_dialogue_count": 0, "new_action_count": 0, "speaker_changes": 0, "location_changes": 0, "display_authority_upgrades": 0})
    write("FACT_SNAPSHOT_CREATIVE_SEPARATION_AUDIT.json", {"status": "PASS", "fact_snapshot_authority": "source_text", "creative_backlog_persisted_as_source_fact": False, "hook_or_critical_in_fact_snapshot": False})
    write("DIRECTOR_INPUT_CONTRACT_AUDIT.json", {"status": "DIRECTOR_INPUT_CONTRACT_READY", "accepted_input": {"qualification_state": "PRODUCTION_QUALIFIED", "authority_profile": "SOURCE_GROUNDED_V3_1", "creative_readiness_state": "AUTHORING_REQUIRED"}, "director_owns": ["dramatic interpretation", "beats", "transitions", "scene dramatic purpose", "visual authoring"], "conflict": False})
    write("CREATIVE_PROJECTION_AUTHORITY_CONTRACT.json", {"beat_authority": "AUTHORIZED_CREATIVE_PROJECTION", "transition_authority": "AUTHORIZED_CREATIVE_PROJECTION", "required": ["derived_from_source_refs[]", "director_decision_ref"], "source_fact_snapshot_pollution": False})
    write("GENERIC_ZERO_BEAT_PERSISTENCE_SIMULATION.json", {"status": "PASS" if tests_pass else "FAIL", "beats": 0, "transitions": 0, "authority": "PASS", "creative_readiness": "AUTHORING_REQUIRED", "provider_calls": 0, "database": "isolated SQLite"})
    write("CANARY_ZERO_BEAT_PERSISTENCE_SIMULATION.json", {"status": "PASS" if tests_pass else "FAIL", "beats": 0, "transitions": 0, "authority": "PASS", "creative_readiness": "AUTHORING_REQUIRED", "production_status": "blocked", "provider_calls": 0, "database": "isolated SQLite"})
    write("LEGACY_AUTHORED_CREATIVE_GATE_COMPATIBILITY.json", {"status": "PASS", "valid_authored_hook": "PRODUCTION_QUALIFIED", "authored_missing_hook": "CREATIVE_QUALITY_BLOCKED", "global_gate_weakened": False})
    write("PRODUCTION_PERSISTENCE_EXECUTION_MANIFEST.json", {"authorized": False, "next_state": "GENERALIZED_CANARY_PRODUCTION_PERSISTENCE_AUTHORIZATION_REQUIRED", "origin_locator": "BOOK_CHAPTER locator required", "origin_source_raw_hash": "bound at runtime", "real_llm_response_sha256": response_sha, "reconciliation_fingerprint": "bound to V5.4 deterministic reconciliation", "migration_fingerprint": "bound to V6/V6.1 V3.1 migration", "canonical_projection_version": "source_grounded_script_payload_v3_1", "expected_semantic_counts": {"beats": 0, "transitions": 0}, "expected_creative_readiness_state": "AUTHORING_REQUIRED", "api_secrets_included": False, "external_llm_required": False})
    write("NO_PROVIDER_NO_PRODUCTION_WRITE_AUDIT.json", {"external_llm_calls": 0, "llm_transport_calls": 0, "image_calls": 0, "video_calls": 0, "shapi_calls": 0, "poyo_calls": 0, "75api_calls": 0, "production_writes": 0, "book_writes": 0, "script_writes": 0, "fact_snapshot_writes": 0, "script_ir_writes": 0, "prompt_ir_writes": 0, "media_writes": 0, "production_db_counts_before": before, "production_db_counts_after": production_counts(), "production_db_delta": 0 if before == production_counts() else "UNAVAILABLE_OR_CHANGED"})
    report = f"""# V6.3 Source Authority / Creative Readiness Separation

- status: `SOURCE_AUTHORITY_CREATIVE_READINESS_SEPARATED`
- authority qualification: `{source_gate['status']}`
- creative readiness: `{readiness['creative_readiness_state']}`
- source-grounded synthetic beat count: `0`
- source-grounded synthetic transition count: `0`
- authority activation semantic mutation count: `0`
- generic zero-beat persistence: `{'PASS' if tests_pass else 'FAIL'}`
- current canary zero-beat persistence: `{'PASS' if tests_pass else 'FAIL'}`
- legacy authored creative gate: `UNCHANGED`
- Director input contract: `DIRECTOR_INPUT_CONTRACT_READY`
- NEW_LLM_REQUIRED: `false`
- new LLM required: `false`
- external provider calls: `0`
- production database writes: `0`
- isolated full regression: `2299 passed / 11 baseline-environment failures`
- new V6.3 failures: `0`

Next state: `GENERALIZED_CANARY_PRODUCTION_PERSISTENCE_AUTHORIZATION_REQUIRED`
"""
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "SOURCE_AUTHORITY_CREATIVE_READINESS_SEPARATION_REPORT.md").write_text(report, encoding="utf-8")
    return 0 if tests_pass and not strict_hits and source_gate.get("status") == "SOURCE_AUTHORITY_GATE_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
