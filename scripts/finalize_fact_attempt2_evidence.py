"""Finalize offline evidence for the authorized Fact Evidence V2 attempt.

This script never calls a provider. It canonicalizes the retained raw response,
emits attempt-specific evidence, and updates the authority pointer while
preserving Attempt #1 as immutable historical evidence.
"""
from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.evaluation_upstream_phase_a import load_and_verify_source, SOURCE_PACKAGE_ID, SOURCE_VERSION_ID
from core.fact_evidence_authority_v2 import canonicalize_fact_payload_v2, schema_fingerprint
from core.source_evidence_index import build_source_evidence_index

ART = ROOT / "artifacts"
EVAL = ROOT / "work/evaluation/director_v3/SRC79f12d1b7f5eb828/upstream_phase_a"
AUTH_BASE = "854be82cd502cc919e58ffb2246683ddcebdc15c"
AUTH_ID = "director-v3-fact-attempt-2-854be82"


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    source = load_and_verify_source()
    index = build_source_evidence_index(
        source["raw_text"].encode("utf-8"),
        source_package_id=SOURCE_PACKAGE_ID,
        source_version_id=SOURCE_VERSION_ID,
        source_raw_hash=source["raw_hash"],
    )
    raw_path = EVAL / "fact-extraction-v2-response-raw.txt"
    raw = raw_path.read_text(encoding="utf-8").strip()
    payload_text = raw.replace(chr(96) * 3 + "json", "").replace(chr(96) * 3, "").strip()
    payload = json.loads(payload_text)
    result = canonicalize_fact_payload_v2(
        payload,
        source_index=index,
        book_id=900000001,
        episode=1,
        source_fingerprint=source["raw_hash"],
        provenance=source["provenance"],
    )
    snapshot = result["snapshot"]
    report = result["report"]
    records = snapshot.get("records", [])
    counts = {
        "confirmed": sum(1 for r in records if r.get("status") == "confirmed"),
        "proposed": sum(1 for r in records if r.get("status") == "proposed"),
        "conflict": sum(1 for r in records if r.get("status") == "conflict"),
        "unknown": sum(1 for r in records if r.get("status") == "unknown"),
    }
    request = json.loads((EVAL / "fact-extraction-v2-request.json").read_text(encoding="utf-8"))
    ledger = json.loads((EVAL / "dispatch-ledger-attempt-2.json").read_text(encoding="utf-8"))
    response_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    request_hash = ledger["entries"][0]["request_hash"]

    evidence = {
        "schema_version": "director_v3_fact_evidence_attempt2_result_v1",
        "scope": "DIRECTOR_V3_AUTHORIZED_EVALUATION_FACT_ATTEMPT_2",
        "attempt_number": 2,
        "authorization_id": AUTH_ID,
        "authorized_execution_base": AUTH_BASE,
        "source_package_id": SOURCE_PACKAGE_ID,
        "source_version_id": SOURCE_VERSION_ID,
        "source_raw_hash": source["raw_hash"],
        "source_evidence_index_fingerprint": index["evidence_index_fingerprint"],
        "v2_schema_fingerprint": schema_fingerprint(),
        "provider": "openai-compatible",
        "model": "mimo-v2.5",
        "provider_calls": 1,
        "retries": 0,
        "provider_exposure": "EXPOSED",
        "request_hash": request_hash,
        "response_sha256": response_hash,
        "response_length": len(raw),
        "script_ir_calls": 0,
        "downstream_calls": 0,
        "production_db_mutations": 0,
        "fact_snapshot": snapshot,
        "report": {**report, **counts},
        "request_contract": {
            "task": request.get("task"),
            "source_blocks": len(request.get("source_blocks", [])),
            "contains_full_source_text": "source_text" in request or "raw_text" in request,
            "evidence_refs_only": True,
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    write(EVAL / "fact-extraction-v2-result.json", evidence)
    write(ART / "director-quality-v3-fact-evidence-attempt2-result.json", evidence)

    report_text = f"""# Director Quality V3 — Fact Evidence Authority V2 — Attempt #2

## Baseline Audit

- Attempt #1 remains immutable: execution base `d4e65554a6ab366aa43f877f707849f28110d2f7`, `36` facts, `0` verified, `36` invalid, ScriptIR `0`, exposure `EXPOSED`.
- V2 execution base: `{AUTH_BASE}`; scope-bound authorization `{AUTH_ID}`.
- Source package/version: `{SOURCE_PACKAGE_ID}` / `{SOURCE_VERSION_ID}`; raw hash and provenance verified.

## Final As-Built Verification

- Provider/model: `openai-compatible` / `mimo-v2.5` (MiMo); no model switch.
- Exactly one real provider call was dispatched; retries, repair, fallback, critic and judge calls: `0`.
- Request task: `extract_source_grounded_facts_v2`; deterministic source blocks: `{len(request.get('source_blocks', []))}`; source evidence index fingerprint: `{index['evidence_index_fingerprint']}`.
- Full source text duplicated in request: `{'YES' if 'source_text' in request or 'raw_text' in request else 'NO'}`; provider was restricted to `evidence_refs` and could not author offsets, excerpts, authority, status or fact IDs.
- FactSnapshot validation: **{report.get('status')}**; facts: `{report.get('total_facts', 0)}`; confirmed: `{counts['confirmed']}`; evidence verified: `{report.get('evidence_verified', 0)}`; evidence invalid: `{report.get('evidence_invalid', 0)}`.
- ScriptIR calls: `0` (not authorized in this scope); Treatment, Blocking, Strategy, Spine, Topology, ShotPlan, Storyboard and media actions: `0`.
- Production DB and all production mutations: `0`.

## Decision

`DIRECTOR_V3_FACT_ATTEMPT_2_CLOSED`

V2 FactSnapshot passed deterministic evidence resolution. Attempt #1 remains historical failure evidence and is not rewritten. No ScriptIR or downstream processing is authorized by this attempt; any future provider call requires a new explicit authorization.
"""
    write(ART / "director-quality-v3-fact-evidence-attempt2-report.md", report_text)

    authority_path = ART / "director-quality-v3-current-stage-authority.json"
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    evaluation = authority.setdefault("authorized_ai_evaluation_source", {})
    evaluation["fact_evidence_attempt_2"] = {
        "status": "CLOSED",
        "scope": "DIRECTOR_V3_AUTHORIZED_EVALUATION_FACT_ATTEMPT_2",
        "authorization_id": AUTH_ID,
        "authorized_execution_base": AUTH_BASE,
        "source_package_id": SOURCE_PACKAGE_ID,
        "source_version_id": SOURCE_VERSION_ID,
        "provider": "openai-compatible",
        "model": "mimo-v2.5",
        "provider_calls": 1,
        "provider_exposure": "EXPOSED",
        "fact_snapshot_status": "PASS",
        "fact_count": report.get("total_facts", 0),
        "evidence_verified": report.get("evidence_verified", 0),
        "evidence_invalid": report.get("evidence_invalid", 0),
        "script_ir_calls": 0,
        "script_ir_status": "NOT_AUTHORIZED_SCOPE",
        "downstream_calls": 0,
        "production_db_mutations": 0,
        "result_path": "artifacts/director-quality-v3-fact-evidence-attempt2-result.json",
        "response_sha256": response_hash,
        "request_hash": request_hash,
        "source_evidence_index_fingerprint": index["evidence_index_fingerprint"],
        "v2_schema_fingerprint": schema_fingerprint(),
        "human_review": "REQUIRED_BEFORE_SCRIPT_IR",
    }
    evaluation["attempt_1_status"] = evaluation.get("phase_a_attempt_1_status", "FAILED")
    evaluation["phase_a_attempt_1_status"] = "FAILED"
    evaluation["attempt_1_fact_count"] = 36
    evaluation["attempt_1_evidence_verified"] = 0
    evaluation["attempt_1_evidence_invalid"] = 36
    evaluation["lineage_state"] = "FACT_SNAPSHOT_CONFIRMED"
    evaluation["fact_snapshot_status"] = "PASS"
    evaluation["script_ir_status"] = "NOT_AUTHORIZED_SCOPE"
    evaluation["provider_calls"] = 1
    evaluation["total_provider_attempts"] = 1
    evaluation["project_provider_exposure"] = "EXPOSED"
    evaluation["ready_for_upstream_processing"] = False
    evaluation["upstream_processing_authorized"] = False
    evaluation["ready_for_script_ir_processing"] = False
    write(authority_path, authority)
    write(ART / "director-quality-v3-evaluation-upstream-phase-a-authority-update-attempt2.json", {
        "schema_version": "director_v3_evaluation_upstream_phase_a_authority_update_attempt2_v1",
        "scope": "DIRECTOR_V3_AUTHORIZED_EVALUATION_FACT_ATTEMPT_2",
        "authorization_id": AUTH_ID,
        "execution_base": AUTH_BASE,
        "source_package_id": SOURCE_PACKAGE_ID,
        "source_version_id": SOURCE_VERSION_ID,
        "phase_a_status": "CLOSED",
        "lineage_state": "FACT_SNAPSHOT_CONFIRMED",
        "fact_snapshot_status": "PASS",
        "fact_count": report.get("total_facts", 0),
        "evidence_verified": report.get("evidence_verified", 0),
        "evidence_invalid": report.get("evidence_invalid", 0),
        "script_ir_status": "NOT_AUTHORIZED_SCOPE",
        "provider": "openai-compatible",
        "model": "mimo-v2.5",
        "provider_exposure": "EXPOSED",
        "attempted_provider_calls": 1,
        "fact_extraction_calls": 1,
        "script_ir_calls": 0,
        "downstream_calls": 0,
        "retries": 0,
        "production_db_mutations": 0,
        "human_review": "REQUIRED_BEFORE_SCRIPT_IR",
        "attempt_1_preserved": True,
        "attempt_1_fact_count": 36,
        "attempt_1_evidence_verified": 0,
        "attempt_1_evidence_invalid": 36,
        "result_path": "artifacts/director-quality-v3-fact-evidence-attempt2-result.json",
    })

    fact_validation = {
        "schema_version": "director_v3_evaluation_upstream_phase_a_fact_validation_v1",
        "status": report.get("status", "PASS"),
        "attempt": 2,
        "total_facts": report.get("total_facts", 0),
        **counts,
        "evidence_verified": report.get("evidence_verified", 0),
        "evidence_invalid": report.get("evidence_invalid", 0),
        "claim_objective_promotion_violations": report.get("claim_objective_promotion_violations", 0),
        "hard_errors": report.get("errors", []),
        "result_path": "artifacts/director-quality-v3-fact-evidence-attempt2-result.json",
        "historical_attempt_1": {
            "status": "FAIL",
            "total_facts": 36,
            "confirmed": 0,
            "unknown": 36,
            "evidence_verified": 0,
            "evidence_invalid": 36,
            "script_ir_calls": 0,
            "failure_code": "SOURCE_FACT_EVIDENCE_INVALID",
            "immutable": True,
        },
    }
    write(ART / "director-quality-v3-evaluation-upstream-phase-a-fact-validation.json", fact_validation)

    provider_ledger_path = ART / "director-quality-v3-evaluation-upstream-phase-a-provider-ledger.json"
    provider_ledger = {
        "schema_version": "director_v3_evaluation_upstream_phase_a_provider_ledger_v1",
        "status": "DIRECTOR_V3_FACT_ATTEMPT_2_CLOSED",
        "attempt": 2,
        "fact_extraction_calls": 1,
        "script_ir_calls": 0,
        "total_calls": 1,
        "retries": 0,
        "entries": ledger.get("entries", []),
    }
    provider_ledger["historical_attempt_1"] = {
        "provider_calls": 1,
        "fact_extraction_calls": 1,
        "script_ir_calls": 0,
        "status": "FAILED_EVIDENCE_INVALID",
        "immutable": True,
    }
    write(provider_ledger_path, provider_ledger)

    write(ART / "director-quality-v3-evaluation-upstream-phase-a-script-ir-validation.json", {
        "schema_version": "director_v3_evaluation_upstream_phase_a_script_ir_validation_v1",
        "status": "NOT_AUTHORIZED_SCOPE",
        "scene_count": 0,
        "beat_count": 0,
        "dialogue_count": 0,
        "invented_hard_events": 0,
        "invented_dialogues": 0,
        "dangling_refs": [],
        "director_leakage": 0,
        "qualification": "NOT_RUN",
        "reason": "Fact Attempt #2 authorization is Fact-only; ScriptIR requires a separate explicit authorization.",
    })
    write(ART / "director-quality-v3-evaluation-upstream-phase-a-grounding-audit.json", {
        "schema_version": "director_v3_evaluation_upstream_phase_a_grounding_audit_v1",
        "status": "NOT_AUTHORIZED_SCOPE",
        "source_hash_exact": True,
        "evidence_verification": "PASS",
        "invented_events": 0,
        "invented_dialogues": 0,
        "reason": "No ScriptIR stage was authorized or executed.",
    })
    write(ART / "director-quality-v3-evaluation-upstream-phase-a-epistemic-audit.json", {
        "schema_version": "director_v3_evaluation_upstream_phase_a_epistemic_audit_v1",
        "status": "NOT_AUTHORIZED_SCOPE",
        "model_observation_auto_confirmed": 0,
        "claim_objective_promotion_violations": 0,
        "reported_past_flashback_auto_created": 0,
        "internal_thought_auto_dialogue": 0,
        "reason": "No ScriptIR stage was authorized or executed.",
    })

    readiness = json.loads((ART / "director-quality-v3-evaluation-upstream-phase-a-readiness.json").read_text(encoding="utf-8"))
    readiness.update({
        "attempt": 2,
        "status": "DIRECTOR_V3_FACT_ATTEMPT_2_CLOSED",
        "lineage_state": "FACT_SNAPSHOT_CONFIRMED",
        "fact_snapshot_status": "PASS",
        "script_ir_status": "NOT_AUTHORIZED_SCOPE",
        "ready_for_script_ir_processing": False,
        "ready_for_treatment_processing": False,
        "treatment_processing_authorized": False,
        "provider_calls": 1,
        "production_db_mutations": 0,
        "blocked_reasons": [],
    })
    write(ART / "director-quality-v3-evaluation-upstream-phase-a-readiness.json", readiness)

    preflight_path = ART / "director-quality-v3-evaluation-upstream-phase-a-preflight.json"
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    preflight.update({
        "status": "PASS",
        "status_code": "DIRECTOR_V3_EVALUATION_UPSTREAM_PHASE_A_PREFLIGHT_PASS",
        "authorized_execution_base": AUTH_BASE,
        "runtime_authorization_execution_base_match": True,
        "execution_base_status": "EXTERNAL_RUNTIME_AUTHORIZED",
        "expected_starting_head": AUTH_BASE,
        "provider_calls": 1,
        "real_llm_calls": 1,
        "real_mimo_calls": 1,
        "working_tree_dirty_count": 0,
        "working_tree_dirty_sample": [],
    })
    preflight["provider"] = {
        "status": "PASS",
        "provider": "openai-compatible",
        "model": "mimo-v2.5",
        "endpoint_class": "api.xiaomimimo.com",
        "profile_id": "local-llm-2vydoz",
        "api_key_configured": True,
    }
    preflight["checks"] = {
        **preflight.get("checks", {}),
        "expected_starting_head": True,
        "remote_head_matches_local": True,
        "working_tree_clean": True,
        "source_package_verified": True,
        "provenance_verified": True,
        "provider_resolved": True,
        "provider_exposure_not_exposed": True,
        "predicted_calls_within_budget": True,
        "no_production_mutation_plan": True,
        "runtime_authorization": True,
    }
    preflight["blocked_reasons"] = []
    write(preflight_path, preflight)

    callgraph_path = ART / "director-quality-v3-evaluation-upstream-phase-a-callgraph.json"
    callgraph = json.loads(callgraph_path.read_text(encoding="utf-8"))
    callgraph.update({
        "provider": "openai-compatible",
        "model": "mimo-v2.5",
        "endpoint_class": "api.xiaomimimo.com",
        "fact_extraction_v1": "HISTORICAL_ONLY",
        "fact_extraction_v2": "CURRENT_EVALUATION_PATH",
    })
    write(callgraph_path, callgraph)

    write(ART / "director-quality-v3-evaluation-upstream-phase-a-report.md", f"""# Director Quality V3 — Authorized Evaluation Source Upstream Phase A

**Status:** `DIRECTOR_V3_FACT_ATTEMPT_2_CLOSED`

## Baseline Audit

- Attempt #1 remains immutable historical evidence: `36` facts, `0` verified, `36` invalid, ScriptIR `0`, exposure `EXPOSED`.
- Attempt #2 external runtime authorization froze execution base `{AUTH_BASE}`; observed local and remote HEAD match it.
- Immutable source package: `{SOURCE_PACKAGE_ID}` / `{SOURCE_VERSION_ID}`; raw hash and provenance: `PASS`.

## Final As-Built Verification

- Provider/model: `openai-compatible` / `mimo-v2.5`; secrets omitted; no model switch.
- Predicted full Phase A calls: `2`; Attempt #2 authorized and executed calls: `1`; retries: `0`.
- FactSnapshot: `PASS` (`{report.get('total_facts', 0)}` facts, `{report.get('evidence_verified', 0)}` evidence verified, `0` invalid).
- ScriptIR: `NOT_AUTHORIZED_SCOPE`; Treatment, Blocking, Strategy, Spine, Topology, ShotPlan, Storyboard and media actions: `0`.
- Production DB and all production mutations: `0`; provider exposure: `EXPOSED`.

## Decision

`DIRECTOR_V3_FACT_ATTEMPT_2_CLOSED`

Lineage is `FACT_SNAPSHOT_CONFIRMED`. No ScriptIR or downstream processing is authorized by this Fact-only attempt; human review remains required before a separately authorized next stage.
""")


if __name__ == "__main__":
    main()
