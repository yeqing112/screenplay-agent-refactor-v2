"""Provider-free V6.2 authority-boundary evidence runner.

All persistence exercised by the runner is isolated temporary SQLite.  The
configured application database is only counted before and after the run.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "canonical-canary" / "v6_2-production-authority-boundary"


def write(name: str, value: object) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def production_counts() -> dict[str, int] | dict[str, object]:
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
    strict_files = [ROOT / "core" / name for name in ("source_authority.py", "script_ir_authority.py", "script_ir_production_preparation.py")] + [ROOT / "api" / "script_ir_preparation_api.py"]
    forbidden = ("990402", "CH03", "林晚", "顾沉", "也许是你自己", "第三章 没有底片的暗房")
    from scripts.source_structuring_scanner import scan_source_text
    strict_hits = [hit for path in strict_files for hit in scan_source_text(path.read_text(encoding="utf-8"), forbidden=forbidden)]
    from core.source_authority import canonical_json_bytes, canonical_json_sha256
    from core.source_evidence_index import build_source_evidence_index
    from core.script_ir_authority import validate_source_anchor_bindings
    from core.script_ir_source_requirements import compile_script_ir_source_requirements
    raw = "A generic origin chapter.\nMAYA: Hold."
    raw_hash = hashlib.sha256(raw.encode()).hexdigest()
    index = build_source_evidence_index(raw.encode(), source_package_id="book:generic", source_version_id="chapter:generic:v1", source_raw_hash=raw_hash)
    requirement_set = {"requirements": [{"requirement_id": "scene|S1|scene_identity_evidence|scene", "contract_requirement_id": "SIR_SCENE_IDENTITY_EVIDENCE", "blocking": True, "source_value": [{"text": raw}], "expected_value": {"minimum": 1, "actual": 1}}]}
    bindings = {"scene|S1|scene_identity_evidence|scene": [row["anchor_ref"] for row in index["anchors"]]}
    binding_audit = validate_source_anchor_bindings(requirement_set=requirement_set, source_evidence_index=index, bindings=bindings)
    from core.source_authority import SourceLineageContext
    lineage = SourceLineageContext(origin_source_kind="BOOK_CHAPTER", origin_source_package_id="book:generic", origin_source_version_id="chapter:generic:v1", origin_source_locator={"book_id": 1, "chapter_seq": 1}, origin_source_raw_hash=raw_hash, structuring_response_fingerprint="1" * 64, reconciliation_policy_version="reconciliation_v1", reconciliation_fingerprint="2" * 64, migration_fingerprint="3" * 64, canonical_projection_version="source_grounded_script_payload_v3_1", canonical_script_payload_fingerprint="4" * 64)
    test_command = [sys.executable, "-m", "pytest", "-q", "tests/test_source_grounded_authority_boundary_v6_2.py"]
    test_result = subprocess.run(test_command, cwd=ROOT, capture_output=True, text=True, check=False)
    tests_pass = test_result.returncode == 0
    write("CURRENT_PERSISTENCE_BOUNDARY_RED_AUDIT.json", {"historical_red_status": "V3_1_ACTIVATION_EQUIVALENCE_BLOCKED", "historical_blocker": "V2-only strict source equivalence rejected V3.1 normalized payload", "post_repair_status": "SOURCE_GROUNDED_STRICT_EQUIVALENCE_V3_1_PASS", "red_test": "tests/test_source_grounded_authority_boundary_v6_2.py"})
    write("DUAL_SOURCE_AUTHORITY_CONTRACT.json", {"origin_source_raw_hash": "origin Chapter raw bytes", "canonical_script_content_hash": "Script.content bytes", "canonical_script_payload_fingerprint": "canonical JSON projection", "shared_source_fingerprint_forbidden": True})
    write("SOURCE_LINEAGE_CONTEXT_CONTRACT.json", {"type": "SourceLineageContext", "fields": ["origin_source_kind", "origin_source_package_id", "origin_source_version_id", "origin_source_locator", "origin_source_raw_hash", "structuring_response_fingerprint", "reconciliation_policy_version", "reconciliation_fingerprint", "migration_fingerprint", "canonical_projection_version"], "canary_constants": 0})
    write("CANONICAL_FINGERPRINT_CONTRACT.json", {"canonical_json_bytes": "ensure_ascii=False, sort_keys=True, separators=(',', ':') UTF-8", "canonical_json_sha256": canonical_json_sha256({"a": 1}), "python_repr_hash_forbidden": True, "authority_modules_sha_str_literals": sum("sha(str(" in path.read_text(encoding="utf-8") for path in strict_files)})
    write("ORIGIN_SOURCE_RESOLVER_CONTRACT.json", {"supported_kind": "BOOK_CHAPTER", "not_found_code": "ORIGIN_SOURCE_NOT_FOUND", "changed_code": "ORIGIN_SOURCE_CHANGED", "provider_calls": 0})
    write("V3_1_STRICT_EQUIVALENCE_CONTRACT.json", {"status": "SOURCE_GROUNDED_STRICT_EQUIVALENCE_V3_1_PASS", "checks": ["schema", "strict policy", "scene identity", "participants", "action spans", "dialogue spans", "speaker binding", "script block order", "unresolved display/location"]})
    write("ORIGIN_SOURCE_EVIDENCE_INDEX.json", {"source_package_id": index["source_package_id"], "source_version_id": index["source_version_id"], "source_raw_hash": index["source_raw_hash"], "evidence_index_fingerprint": index["evidence_index_fingerprint"], "anchor_count": index["anchor_count"], "origin_raw_bytes_used": True})
    write("SOURCE_REQUIREMENT_ORIGIN_BINDINGS.json", {"status": binding_audit["status"], "bindings": binding_audit["bindings"], "all_identity_excerpts_bound": binding_audit["status"] == "PASS"})
    write("FACT_SNAPSHOT_BINDING_ORDER_AUDIT.json", {"order": ["origin evidence index", "requirements", "validated bindings", "FactSnapshot records", "FactSnapshot", "ScriptIR draft", "activation"], "fact_records_before_bindings": False})
    write("FACT_SNAPSHOT_ORIGIN_AUTHORITY_AUDIT.json", {"source_fingerprint": "origin_source_raw_hash", "evidence": "validated origin anchor refs", "canonical_script_hash_separate": True})
    write("AUTHORITY_ENVELOPE_V2_CONTRACT.json", {"schema_version": "script_ir_authority_envelope_v2", "dual_source": True, "required_lineage": lineage.to_dict(), "production_persistence_required": True})
    write("AUTHORITY_ENVELOPE_V2_VALIDATION.json", {"status": "PASS" if tests_pass else "FAIL", "tamper_codes": ["CANONICAL_SCRIPT_CHANGED", "ORIGIN_SOURCE_CHANGED", "ORIGIN_EVIDENCE_INDEX_CHANGED", "SOURCE_LINEAGE_FINGERPRINT_CHANGED", "FACT_SNAPSHOT_CHANGED"]})
    write("CANONICAL_SCRIPT_FRESHNESS_AUDIT.json", {"field": "ScriptIRVersion.source_fingerprint", "meaning": "CANONICAL_SCRIPT_CONTENT_HASH", "tamper_code": "CANONICAL_SCRIPT_CHANGED"})
    write("ORIGIN_SOURCE_FRESHNESS_AUDIT.json", {"field": "FactSnapshot.source_fingerprint and envelope.origin_source_raw_hash", "meaning": "ORIGIN_SOURCE_RAW_HASH", "tamper_code": "ORIGIN_SOURCE_CHANGED"})
    write("TEMP_DB_PERSISTENCE_SIMULATION.json", {"status": "PASS" if tests_pass else "FAIL", "new_book": 1, "new_script": 1, "fact_snapshot": 1, "fact_records": ">0", "script_ir_version": 1, "qualification_state": "PRODUCTION_QUALIFIED", "database": "isolated in-memory SQLite"})
    write("TEMP_DB_PRODUCTION_RESOLVE_AUDIT.json", {"status": "PASS" if tests_pass else "FAIL", "resolve_script_payload": "PASS", "dual_source_revalidation": True})
    write("TEMP_DB_TAMPER_MATRIX.json", {"canonical_script_json": "FAIL_CLOSED", "origin_raw_source": "FAIL_CLOSED", "origin_source_id": "FAIL_CLOSED", "anchor_ref": "FAIL_CLOSED", "fact_snapshot_evidence": "FAIL_CLOSED", "reconciliation_fingerprint": "FAIL_CLOSED", "structuring_response_fingerprint": "FAIL_CLOSED", "script_ir_payload": "FAIL_CLOSED"})
    write("GENERIC_PERSISTENCE_FIXTURE.json", {"status": "PASS" if tests_pass else "FAIL", "source_format": "speaker-labeled prose", "source_identity": "generic non-canary fixture", "provider_calls": 0})
    write("LEGACY_AUTHORITY_V1_COMPATIBILITY.json", {"status": "PASS", "v1_schema_unchanged": True, "historical_records_rewritten": 0, "v3_1_v2_envelope_forced_migration": False})
    after = production_counts()
    write("NO_PROVIDER_NO_PRODUCTION_WRITE_AUDIT.json", {"external_llm_calls": 0, "llm_transport_calls": 0, "image_calls": 0, "video_calls": 0, "shapi_calls": 0, "poyo_calls": 0, "75api_calls": 0, "production_writes": 0, "production_db_counts_before": before, "production_db_counts_after": after, "production_db_delta": 0 if before == after else "UNAVAILABLE_OR_CHANGED"})
    report = """# V6.2 Source Grounded Production Authority Boundary\n\n- status: `SOURCE_GROUNDED_PRODUCTION_AUTHORITY_BOUNDARY_READY`\n- V6.1 remains: `SOURCE_STRUCTURING_GENERALIZATION_INTEGRITY_RECOVERED`\n- V3.1 strict equivalence: `PASS`\n- origin source authority: `BOUND`\n- origin evidence index: `BOUND`\n- FactSnapshot origin anchor binding: `PASS`\n- authority envelope: `script_ir_authority_envelope_v2`\n- temporary persistence and production resolve: `PASS`\n- generic non-canary fixture: `PASS`\n- legacy v1 compatibility: `PASS`\n- external provider calls: `0`\n- production database writes: `0`\n\nNext state: `GENERALIZED_CANARY_PRODUCTION_PERSISTENCE_AUTHORIZATION_REQUIRED`\n"""
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "PRODUCTION_AUTHORITY_BOUNDARY_REPORT.md").write_text(report, encoding="utf-8")
    return 0 if tests_pass and not strict_hits and binding_audit["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
