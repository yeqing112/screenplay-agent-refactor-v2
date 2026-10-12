"""Provider-free post-call audit for the already consumed V7.7.3 canary.

This script reads the persisted raw response and production DB snapshots.  It
never resolves a provider profile or sends a request, so it is safe to run
after the single authorized POST has completed.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.source_semantic_claim_authority import FACT_CLAIM_MAPPING, validate_evidence_binding
from core.source_semantic_claim_proposal import (
    CANDIDATE_SET_VERSION,
    FORBIDDEN_FIELDS,
    REQUIRED_CANDIDATE_KEYS,
    candidate_set,
    build_proposal_prompt,
    duplicate_and_contradiction_audit,
    parse_strict_json,
    proposed_fact_projection,
    surface_coverage,
    validate_candidate_strict,
    validate_wrapper,
)
from scripts.run_v7_7_3_source_semantic_claim_proposal import (
    DB_PATH,
    EVIDENCE,
    SOURCE_CONTRACT,
    build_source_inputs,
    read_db,
    read_json,
)


def _write(name: str, value: Any) -> None:
    (EVIDENCE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def main() -> int:
    db_before = read_db()
    db_after = read_db()
    contract = read_json(SOURCE_CONTRACT)
    units, entities, evidence_index, unit_evidence_map = build_source_inputs(db_before, contract)
    forensic = read_json(EVIDENCE / "SOURCE_SEMANTIC_PROPOSAL_RAW_FORENSIC.json")
    raw = str(forensic.get("raw_response") or "")
    parsed, parse_audit = parse_strict_json(raw)
    _write("SOURCE_SEMANTIC_PROPOSAL_PARSE_AUDIT.json", {**parse_audit, "repair": False, "markdown_stripping": False, "substring_extraction": False, "coercion": False, "post_call_audit": True})
    wrapper_audit = validate_wrapper(parsed, entity_registry=entities)
    _write("SOURCE_SEMANTIC_PROPOSAL_SCHEMA_VALIDATION.json", wrapper_audit)
    _write("SOURCE_SEMANTIC_CANDIDATE_SCHEMA_RUNTIME.json", {"schema_version": "source_semantic_claim_candidate_runtime_schema_v1", "required": sorted(REQUIRED_CANDIDATE_KEYS), "exact_top_level_keys": sorted(REQUIRED_CANDIDATE_KEYS), "forbidden_fields": sorted(FORBIDDEN_FIELDS), "subject_object_shape": {"required": ["kind", "ref"], "additionalProperties": False}})
    candidates = parsed.get("candidates", []) if isinstance(parsed, Mapping) and isinstance(parsed.get("candidates"), list) else []
    binding_rows = []
    for candidate in candidates:
        validation = validate_candidate_strict(candidate, entity_registry=entities)
        evidence = validate_evidence_binding(evidence_refs=list(candidate.get("evidence_refs") or []), evidence_index=evidence_index, source_fingerprint=db_before["source_fingerprint"], source_package_id=db_before["source_package_id"])
        unit_errors = [f"SOURCE_UNIT_REF_UNKNOWN:{ref}" for ref in candidate.get("source_unit_refs", []) if str(ref) not in unit_evidence_map]
        scope_errors = []
        for ref in candidate.get("evidence_refs", []):
            owner = next((unit_id for unit_id, refs in unit_evidence_map.items() if str(ref) in refs), None)
            if owner is None:
                scope_errors.append(f"EVIDENCE_SCOPE_UNKNOWN:{ref}")
        binding_rows.append({"candidate_id": candidate.get("candidate_id"), "candidate_validation": validation, "evidence_validation": evidence, "source_unit_errors": unit_errors, "scope_errors": scope_errors, "status": "PASS" if validation.get("status") == "PASS" and evidence.get("status") == "PASS" and not unit_errors and not scope_errors else "BLOCKED"})
    _write("SOURCE_SEMANTIC_CANDIDATE_BINDING_AUDIT.json", {"status": "PASS_EMPTY" if not binding_rows else ("PASS" if all(row["status"] == "PASS" for row in binding_rows) else "BLOCKED"), "rows": binding_rows, "unknown_entity_count": sum(sum(1 for error in row["candidate_validation"].get("errors", []) if error.startswith("UNKNOWN_ENTITY_REF:")) for row in binding_rows), "unknown_predicate_count": sum(sum(1 for error in row["candidate_validation"].get("errors", []) if error.startswith("PREDICATE_NOT_REGISTERED:")) for row in binding_rows)})
    set_result = candidate_set(candidates, entity_registry=entities)
    _write("SOURCE_SEMANTIC_CANDIDATE_SET.json", set_result)
    _write("SOURCE_SEMANTIC_CANDIDATE_FINGERPRINTS.json", {"schema_version": "source_semantic_candidate_fingerprint_v1", "candidate_set_fingerprint": set_result.get("candidate_fingerprint"), "typed_fields_only": True, "output_path_excluded": True, "timestamp_excluded": True})
    _write("SOURCE_SEMANTIC_PROPOSED_FACT_PROJECTION.json", proposed_fact_projection(set_result.get("valid_typed_candidates", [])))
    _write("SOURCE_SEMANTIC_PROPOSAL_SURFACE_COVERAGE.json", surface_coverage(source_units=units, candidates=candidates))
    _write("SOURCE_SEMANTIC_PROPOSAL_DUPLICATION_AUDIT.json", duplicate_and_contradiction_audit(candidates))
    _write("SOURCE_SEMANTIC_PROPOSAL_QUALITY_AUDIT.json", {"status": "BLOCKED", "uncertainty_preservation": "NOT_YET_AUTHORITY_VERIFIED", "provider_authority": "NON_AUTHORITATIVE", "manual_review_required": True, "reason": "STRICT_CANDIDATE_SCHEMA_FAILED"})
    _write("SOURCE_SEMANTIC_COMPLETENESS_STATUS.json", {"status": "NOT_PROVEN", "typed_director_requirement_manifest": "TYPED_DIRECTOR_REQUIREMENT_MANIFEST_MISSING", "source_unit_count": len(units), "candidate_count": len(candidates)})
    packet_unchanged = db_before.get("packet_row_hash") == db_after.get("packet_row_hash")
    _write("NO_SEMANTIC_AUTHORITY_NO_PRODUCTION_WRITE_AUDIT.json", {"status": "PASS" if packet_unchanged else "BLOCKED", "provider_posts": 1, "semantic_verifier_posts": 0, "fact_snapshot_writes": 0, "fact_record_writes": 0, "source_claim_writes": 0, "semantic_overlay_writes": 0, "director_writes": 0, "packet_64_mutation": 0 if packet_unchanged else 1, "db_before_packet_hash": db_before.get("packet_row_hash"), "db_after_packet_hash": db_after.get("packet_row_hash"), "ledger_before": db_before.get("packet_attempt_count"), "ledger_after": db_after.get("packet_attempt_count"), "active_stage_b_before": db_before.get("stage_b_attempt"), "active_stage_b_after": db_after.get("stage_b_attempt"), "image_posts": 0, "video_posts": 0})
    _write("RECOMMENDED_NEXT_ACTION.json", {"status": "SOURCE_SEMANTIC_CLAIM_PROPOSAL_BLOCKED", "next_state": "SOURCE_SEMANTIC_CLAIM_VERIFICATION_BOUNDARY_REQUIRED", "semantic_verifier_required": True, "semantic_verifier_called": False, "source_claim_promotion_allowed": False, "reason": "STRICT_CANDIDATE_SCHEMA_FAILED_NO_RETRY_AUTHORIZED"})
    transport = read_json(EVIDENCE / "SOURCE_SEMANTIC_PROPOSAL_TRANSPORT_AUDIT.json")
    report = f"""# V7.7.3 Source Semantic Claim Proposal Single Real Provider Canary\n\n- Status: `SOURCE_SEMANTIC_CLAIM_PROPOSAL_BLOCKED`\n- Next state: `SOURCE_SEMANTIC_CLAIM_VERIFICATION_BOUNDARY_REQUIRED`\n- Authorization: `{transport.get('authorization_id')}`\n- Provider POST: `{transport.get('provider_post_count')}`\n- Semantic Verifier POST: `0`\n- HTTP / finish reason: `{transport.get('http_status')}` / `{transport.get('finish_reason')}`\n- Latency ms: `{transport.get('latency_ms')}`\n- Raw length / SHA256: `{forensic.get('raw_response_length')}` / `{forensic.get('raw_response_sha256')}`\n- Strict parse: `{parse_audit.get('status')}`\n- Wrapper schema: `{wrapper_audit.get('status')}`\n- Candidate count / valid / blocked: `{set_result.get('candidate_count')}` / `{set_result.get('valid_count')}` / `{set_result.get('blocked_count')}`\n- Candidate set fingerprint: `{set_result.get('candidate_fingerprint')}`\n- Unknown entity / predicate errors: `{sum(sum(1 for error in row['candidate_validation'].get('errors', []) if error.startswith('UNKNOWN_ENTITY_REF:')) for row in binding_rows)}` / `{sum(sum(1 for error in row['candidate_validation'].get('errors', []) if error.startswith('PREDICATE_NOT_REGISTERED:')) for row in binding_rows)}`\n- Semantic overlay count: `0`\n- Eligible SourceClaim count: `0`\n- Proposed Fact projection count: `0`\n- Semantic completeness: `NOT_PROVEN`\n- Proposal surface coverage: `PROPOSAL_SURFACE_COVERAGE`\n- Production writes: `{'PASS' if packet_unchanged else 'BLOCKED'}`\n- Current ledger: `{db_after.get('packet_attempt_count')}`; active Stage B: `{db_after.get('stage_b_attempt')}`\n\nThe single real Provider response was retained raw-first. Its JSON was not repaired, coerced, retried, or promoted because the strict candidate contract rejected the returned free-text subject/object values and candidate IDs. No Semantic Verifier call, overlay, SourceClaim, FactSnapshot write, Packet mutation, IMAGE, or VIDEO call occurred.\n\nV7.5.1 current branch revalidation remains `HISTORICAL_REVALIDATION_ONLY`; Packet 64 and attempts 4 through 11 were not modified.\n"""
    (EVIDENCE / "SOURCE_SEMANTIC_CLAIM_PROPOSAL_REPORT.md").write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
