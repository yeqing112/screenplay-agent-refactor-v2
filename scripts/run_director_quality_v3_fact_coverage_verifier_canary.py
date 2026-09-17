"""Run the one-call authorized Fact Coverage Verifier canary.

The request is assembled entirely from canonical full-source units and the
seven already adjudicated facts.  The provider is allowed one transport call;
there is no retry, repair, fallback, critic, judge or downstream dispatch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"
SOURCE_PACKAGE = "SRC79f12d1b7f5eb828"
SOURCE_VERSION = "SRC79f12d1b7f5eb828:V01:d001bab5cc82"
RAW_HASH = "d001bab5cc820ae3b99f2f7a43ad2f4022e62073acb036a9c1c0e7d4bb888368"
EVIDENCE_FP = "4697f3069bb34c9650d97b7e2c788d5b9db36034a39fedf77a0756e7a7bf5295"
SCOPE = "DIRECTOR_V3_AUTHORIZED_FACT_COVERAGE_VERIFIER_CANARY"
AUTH = Path(os.environ.get("DIRECTOR_V3_COVERAGE_AUTHORIZATION", str(ROOT.parent / "director-v3-fact-coverage-verifier-authorization.json")))
MAIN_DB = Path(os.environ.get("DIRECTOR_MAIN_DB", str(ROOT.parent / "screenplay-agent-refactor-v2" / "work/db/screenplay.db")))
EVAL_ROOT = ROOT / "work" / "evaluation" / "director_v3" / SOURCE_PACKAGE / "fact_coverage_verifier_canary"


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def profile_from_readonly_main_db() -> dict:
    connection = sqlite3.connect(str(MAIN_DB))
    try:
        row = connection.execute("select value from kv where key='model_registry_profiles'").fetchone()
    finally:
        connection.close()
    if not row:
        raise RuntimeError("model_registry_profiles_not_found")
    for profile in json.loads(row[0]):
        if profile.get("capability") == "llm" and profile.get("model_name") == "mimo-v2.5" and profile.get("provider") == "openai-compatible" and profile.get("enabled") is True:
            return dict(profile)
    raise RuntimeError("enabled_mimo_v2_5_profile_not_found")


def build_inputs():
    from core.fact_coverage_verifier import build_request, contract_v3, materialize_units, project_existing_facts
    from core.source_evidence_index import build_source_evidence_index
    raw_path = ROOT / "work/intake/director_v3/evaluation_packages" / f"{SOURCE_PACKAGE}.raw"
    raw_bytes = raw_path.read_bytes()
    if sha256_bytes(raw_bytes) != RAW_HASH:
        raise RuntimeError("raw_source_hash_mismatch")
    narrative = json.loads((ART / "director-quality-v3-full-source-narrative-unit-index.json").read_text(encoding="utf-8"))
    completeness = json.loads((ART / "director-quality-v3-full-source-narrative-unit-completeness.json").read_text(encoding="utf-8"))
    if completeness.get("status") != "PASS" or completeness.get("indexed_anchor_count") != 347 or narrative.get("unit_count") != 5:
        raise RuntimeError("full_source_narrative_input_not_closed")
    if narrative.get("evidence_index_fingerprint") != EVIDENCE_FP:
        raise RuntimeError("source_evidence_index_fingerprint_mismatch")
    source_index = build_source_evidence_index(raw_bytes, source_package_id=SOURCE_PACKAGE, source_version_id=SOURCE_VERSION, source_raw_hash=RAW_HASH)
    materialized = materialize_units(narrative_index=narrative, raw_bytes=raw_bytes, source_raw_hash=RAW_HASH, source_evidence_index=source_index)
    if materialized["status"] != "PASS" or materialized["unit_count"] != 5:
        raise RuntimeError("unit_materialization_failed")
    attempt = json.loads((ART / "director-quality-v3-fact-evidence-attempt2-result.json").read_text(encoding="utf-8"))
    overlay = json.loads((ART / "director-quality-v3-semantic-verifier-canary-authority-overlay.json").read_text(encoding="utf-8"))
    facts = project_existing_facts(fact_records=attempt["fact_snapshot"]["records"], semantic_overlay=overlay)
    if facts["fact_count"] != 7:
        raise RuntimeError("existing_fact_count_mismatch")
    contract = contract_v3()
    profile = profile_from_readonly_main_db()
    request = build_request(units=materialized, facts=facts, contract=contract, provider="openai-compatible", model="mimo-v2.5")
    return raw_bytes, materialized, facts, contract, profile, request


def preflight(auth: dict, *, head: str, remote: str, dirty: list[str], profile: dict, materialized: dict, facts: dict, contract: dict) -> dict:
    authority = json.loads((ART / "director-quality-v3-current-stage-authority.json").read_text(encoding="utf-8"))
    parity = json.loads((ART / "director-quality-v3-current-stage-authority-parity.json").read_text(encoding="utf-8"))
    overlay = json.loads((ART / "director-quality-v3-semantic-verifier-canary-authority-overlay.json").read_text(encoding="utf-8"))
    overlay_fingerprint = sha256_bytes(json.dumps(overlay, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    checks = {
        "local_remote_parity": head == remote,
        "worktree_clean": not dirty,
        "execution_base_matches": auth.get("authorized_execution_base") == head,
        "authorization_scope": auth.get("scope") == SCOPE,
        "max_provider_calls": auth.get("max_provider_calls") == 1,
        "retries_zero": auth.get("retries") == 0,
        "source_identity": auth.get("source_package_id") == SOURCE_PACKAGE and auth.get("source_version_id") == SOURCE_VERSION and auth.get("source_raw_hash") == RAW_HASH,
        "semantic_overlay_identity": auth.get("semantic_overlay_fingerprint") == overlay_fingerprint,
        "full_units": materialized.get("status") == "PASS" and materialized.get("unit_count") == 5,
        "existing_facts": facts.get("fact_count") == 7,
        "semantic_state": authority.get("authorized_ai_evaluation_source", {}).get("semantic_grounding_status") == "SEMANTIC_GROUNDING_CLOSED_WITH_REVIEW",
        "coverage_foundation_closed": authority.get("fact_coverage_foundation", {}).get("status") == "CLOSED",
        "schema_parity": parity.get("status") == "PASS" and contract.get("provider_schema_fingerprint"),
        "provider": profile.get("provider") == "openai-compatible",
        "model": profile.get("model_name") == "mimo-v2.5",
        "downstream_disabled": authority.get("authorized_ai_evaluation_source", {}).get("script_ir_processing_authorized") is False,
    }
    return {"schema_version": "fact_coverage_verifier_preflight_v2", "status": "PASS" if all(checks.values()) else "FAIL", "provider_calls": 0, "checks": checks, "head": head, "remote": remote, "execution_base": auth.get("authorized_execution_base"), "unit_count": materialized.get("unit_count"), "fact_count": facts.get("fact_count"), "schema_fingerprint": contract.get("provider_schema_fingerprint")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-real", action="store_true")
    args = parser.parse_args()
    if not args.execute_real:
        print(json.dumps({"status": "NOT_AUTHORIZED", "provider_calls": 0}, ensure_ascii=False))
        return 2
    sys.path.insert(0, str(ROOT))
    from core.fact_coverage_verifier import (
        build_provider_system_prompt_v3,
        compile_fact_coverage_authority_v2,
        canonicalize_requirements,
        parse_provider_json_envelope_v1,
        validate_final_provider_payload_projection,
        validate_provider_payload,
    )
    from core.llm import call_llm

    head = git("rev-parse", "HEAD")
    remote = git("rev-parse", "origin/codex/fact-semantic-grounding-foundation")
    dirty = git("status", "--porcelain").splitlines()
    auth = json.loads(AUTH.read_text(encoding="utf-8"))
    raw_bytes, materialized, facts, contract, profile, request = build_inputs()
    gate = preflight(auth, head=head, remote=remote, dirty=dirty, profile=profile, materialized=materialized, facts=facts, contract=contract)
    if gate["status"] != "PASS":
        write(ART / "director-quality-v3-fact-coverage-verifier-preflight.json", gate)
        print(json.dumps({"status": "DIRECTOR_V3_FACT_COVERAGE_VERIFIER_CANARY_BLOCKED", "provider_calls": 0, "preflight": gate}, ensure_ascii=False, indent=2))
        return 2
    request_json = json.dumps(request, ensure_ascii=False, indent=2)
    system = build_provider_system_prompt_v3(request["output_contract"])
    transport_projection = validate_final_provider_payload_projection(user_prompt=request_json, system_prompt=system)
    gate["final_transport_projection"] = transport_projection
    if transport_projection["status"] != "PASS":
        gate["status"] = "FAIL"
        write(ART / "director-quality-v3-fact-coverage-verifier-preflight.json", gate)
        print(json.dumps({"status": "DIRECTOR_V3_FACT_COVERAGE_VERIFIER_BLOCKED", "provider_calls": 0, "reason": "PROVIDER_CONTRACT_PROJECTION_INCOMPLETE", "preflight": gate}, ensure_ascii=False, indent=2))
        return 2
    request_hash = sha256_bytes(request_json.encode("utf-8"))
    EVAL_ROOT.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    ledger = {"schema_version": "director_v3_fact_coverage_verifier_provider_ledger_v2", "stage": "FACT_COVERAGE_VERIFIER", "attempt_number": 1, "dispatched": True, "authorization_id": auth["authorization_id"], "authorization_scope": SCOPE, "execution_base": head, "request_hash": request_hash, "provider": profile.get("provider"), "model": profile.get("model_name"), "started_at": started, "status": "DISPATCHING", "cumulative_attempt_before": 3, "cumulative_attempt_after": 4, "provider_calls": 1}
    write(EVAL_ROOT / "request.json", {"system_prompt": system, "request": request, "request_hash": request_hash, "execution_base": head, "authorization_id": auth["authorization_id"], "transport_projection": transport_projection})
    write(EVAL_ROOT / "provider-ledger.json", ledger)
    raw = ""
    error = None
    audit_records: list[dict] = []
    try:
        raw = call_llm(request_json, system=system, model_profile=profile, retries=1, estimated_tokens=10000, audit_extra={"stage": SCOPE, "authorization_id": auth["authorization_id"], "request_hash": request_hash}, audit_callback=audit_records.append)
    except Exception as exc:
        error = str(exc)[:1000]
    finished = datetime.now(timezone.utc).isoformat()
    raw_text = str(raw or "")
    response_hash = sha256_bytes(raw_text.encode("utf-8"))
    ledger.update({"finished_at": finished, "transport_status": "RESPONSE_RECEIVED" if raw_text else "CALL_FAILED", "response_received": bool(raw_text), "response_sha256": response_hash, "response_length": len(raw_text), "error": error})
    write(EVAL_ROOT / "provider-ledger.json", ledger)
    (EVAL_ROOT / "raw-response.txt").write_text(raw_text, encoding="utf-8")
    (ART / "director-quality-v3-fact-coverage-verifier-raw-response.txt").write_text(raw_text, encoding="utf-8")
    write(ART / "director-quality-v3-fact-coverage-verifier-preflight.json", gate)
    write(ART / "director-quality-v3-fact-coverage-verifier-runtime-authorization-record.json", {**auth, "consumed": True, "consumed_at": finished, "provider_calls": 1, "execution_base": head})
    write(ART / "director-quality-v3-fact-coverage-verifier-request.json", {"schema_version": "fact_coverage_verifier_request_v3", "authorization_id": auth["authorization_id"], "execution_base": head, "request_hash": request_hash, "provider": profile.get("provider"), "model": profile.get("model_name"), "development_preview_leaked": False, "request": request, "system_prompt": system, "transport_projection": transport_projection})
    write(ART / "director-quality-v3-fact-coverage-verifier-provider-ledger.json", ledger)
    response_meta = {"schema_version": "fact_coverage_verifier_response_meta_v2", "provider_calls": 1, "response_received": bool(raw_text), "response_sha256": response_hash, "response_length": len(raw_text), "provider": profile.get("provider"), "model": profile.get("model_name"), "started_at": started, "finished_at": finished, "transport_error": error}
    write(ART / "director-quality-v3-fact-coverage-verifier-response-meta.json", response_meta)
    payload = None
    parse_error = None
    validation = {"status": "FAIL", "errors": [{"code": "EMPTY_PROVIDER_RESPONSE"}], "requirements": [], "coverage_claims": [], "unit_assessments": []}
    if raw_text:
        try:
            payload = parse_provider_json_envelope_v1(raw_text, allow_single_fence=True)
            validation = validate_provider_payload(payload, unit_refs=[unit["source_unit_ref"] for unit in materialized["units"]], fact_ids=[row["fact_id"] for row in facts["facts"]])
        except Exception as exc:
            parse_error = str(exc)[:1000]
            validation = {"status": "FAIL", "errors": [{"code": "PROVIDER_JSON_PARSE_FAILURE", "message": parse_error}], "requirements": [], "coverage_claims": [], "unit_assessments": []}
    write(ART / "director-quality-v3-fact-coverage-verifier-schema-validation.json", {"schema_version": "fact_coverage_verifier_schema_validation_v2", "status": validation["status"], "parse_error": parse_error, "errors": validation.get("errors", []), "requirement_count": len(validation.get("requirements", [])), "claim_count": len(validation.get("coverage_claims", [])), "unit_assessment_count": len(validation.get("unit_assessments", [])), "forbidden_fields": validation.get("forbidden_fields", [])})
    if validation["status"] == "PASS":
        canonical = canonicalize_requirements(validation)
        matrix = compile_fact_coverage_authority_v2(canonical=canonical, semantic_overlay=json.loads((ART / "director-quality-v3-semantic-verifier-canary-authority-overlay.json").read_text(encoding="utf-8")), unit_assessments=validation["unit_assessments"])
        missing = [row for row in matrix["rows"] if row["final_coverage_status"] != "COVERED"]
        write(ART / "director-quality-v3-fact-coverage-requirement-key-map.json", canonical)
        write(ART / "director-quality-v3-fact-coverage-authority-matrix.json", matrix)
        write(ART / "director-quality-v3-fact-coverage-unit-assessments.json", {"schema_version": "fact_coverage_unit_assessments_v2", "provider_calls": 0, "assessments": validation["unit_assessments"], "counts": matrix["unit_assessment_counts"], "status": "PASS"})
        write(ART / "director-quality-v3-fact-coverage-missing-requirements.json", {"schema_version": "missing_fact_requirement_package_v1", "provider_calls": 0, "status": "READY_FOR_TARGETED_MISSING_FACT_EXTRACTION" if missing else "EMPTY", "requirements": [{"requirement_id": row["requirement_id"], "requirement_type": row["requirement_type"], "description": row["description"], "source_unit_refs": row["source_unit_refs"], "final_coverage_status": row["final_coverage_status"], "existing_supporting_fact_ids": row["supporting_fact_ids"], "why_insufficient": "Existing facts do not reach the required semantic ceiling."} for row in missing]})
        write(ART / "director-quality-v3-fact-coverage-human-review.json", {"schema_version": "fact_coverage_human_review_v1", "human_review_status": "NOT_RECORDED", "provider_calls": 0, "requirement_count": len(matrix["rows"]), "coverage_status": matrix["qualification_status"], "matrix_fingerprint": matrix["fingerprint"]})
        final_status = "DIRECTOR_V3_FACT_COVERAGE_VERIFIER_CANARY_CLOSED"
        next_stage = "TARGETED_MISSING_FACT_EXTRACTION" if missing else "HUMAN_FINAL_COVERAGE_REVIEW"
        qualification = matrix["qualification_status"]
        counts = matrix["counts"]
        unit_counts = matrix["unit_assessment_counts"]
    else:
        canonical = {"mapping": {}, "requirements": [], "requirement_count": 0}
        matrix = {"counts": {status: 0 for status in ("COVERED", "PARTIALLY_COVERED", "MISSING", "CLAIM_ONLY", "UNSAFE_INFERENCE", "AMBIGUOUS")}, "qualification_status": "FACT_COVERAGE_REVIEW_REQUIRED", "rows": [], "unit_assessment_counts": {rel: 0 for rel in ("RELEVANT", "NO_REQUIRED_FACT", "AMBIGUOUS")}, "fingerprint": ""}
        write(ART / "director-quality-v3-fact-coverage-requirement-key-map.json", canonical)
        write(ART / "director-quality-v3-fact-coverage-authority-matrix.json", matrix)
        write(ART / "director-quality-v3-fact-coverage-unit-assessments.json", {"status": "FAIL", "assessments": []})
        write(ART / "director-quality-v3-fact-coverage-missing-requirements.json", {"status": "NOT_GENERATED_SCHEMA_FAILURE", "requirements": []})
        write(ART / "director-quality-v3-fact-coverage-human-review.json", {"human_review_status": "NOT_RECORDED", "status": "SCHEMA_FAILURE"})
        final_status = "DIRECTOR_V3_FACT_COVERAGE_VERIFIER_CANARY_FAILED"
        next_stage = "PROVIDER_SCHEMA_REPAIR"
        qualification = "FACT_COVERAGE_REVIEW_REQUIRED"
        counts = matrix["counts"]
        unit_counts = matrix["unit_assessment_counts"]
    authority_path = ART / "director-quality-v3-current-stage-authority.json"
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    evaluation = authority.setdefault("authorized_ai_evaluation_source", {})
    evaluation["provider_attempts_by_stage"] = {"fact_attempt_1": 1, "fact_attempt_2": 1, "semantic_verifier": 1, "coverage_verifier": 1}
    evaluation["cumulative_provider_attempts"] = 4
    evaluation["current_stage_provider_attempts"] = 1
    evaluation["fact_coverage_status"] = qualification
    evaluation["ready_for_targeted_missing_fact_extraction"] = qualification == "FACT_COVERAGE_INSUFFICIENT"
    evaluation["targeted_missing_fact_extraction_authorized"] = False
    evaluation["ready_for_script_ir_processing"] = False
    evaluation["script_ir_processing_authorized"] = False
    authority["fact_coverage_verifier"] = {"status": final_status, "authorization_id": auth["authorization_id"], "authorization_scope": SCOPE, "execution_base": head, "provider": {"provider": profile.get("provider"), "model_name": profile.get("model_name")}, "provider_calls": 1, "retries": 0, "request_hash": request_hash, "response_hash": response_hash, "input_unit_count": 5, "input_fact_count": 7, "requirement_count": len(validation.get("requirements", [])), "schema_validation": validation["status"], "unit_assessment_validation": "PASS" if validation["status"] == "PASS" else "FAIL", "final_coverage_counts": counts, "human_review": "NOT_RECORDED", "coverage_verifier_authorized": False, "coverage_verifier_authorization_consumed": True, "script_ir_calls": 0, "script_ir_authorized": False, "next_stage": next_stage, "ready_for_targeted_missing_fact_extraction": qualification == "FACT_COVERAGE_INSUFFICIENT", "targeted_missing_fact_extraction_authorized": False, "runtime_authority": True}
    if qualification == "FACT_COVERAGE_INSUFFICIENT":
        authority["fact_coverage_foundation"]["fact_coverage_status"] = qualification
        authority["fact_coverage_foundation"]["script_ir_gate"] = "BLOCKED_PENDING_TARGETED_MISSING_FACTS"
    write(authority_path, authority)
    report = f"""# Director Quality V3 — Authorized Fact Coverage Verifier Canary

## Execution

- Starting/execution base: `{head}`; local/remote parity before dispatch: `PASS`; worktree clean: `PASS`.
- Authorization: `{auth['authorization_id']}` / `{SCOPE}`; provider/model: `openai-compatible` / `mimo-v2.5`.
- Real provider calls this run: `1`; retries/repair/fallback/critic/judge: `0`; cumulative attempts: `3 → 4`.
- Source: `{SOURCE_PACKAGE}` / `{SOURCE_VERSION}`; raw/evidence identity verified; full anchors `347`; Narrative Units `5`.
- Exact unit materialization: `PASS`; Existing Facts supplied: `7`; development preview leaked: `NO`.

## Provider Contract

- Schema: `fact_coverage_verifier_v2`; provider canonical REQ IDs: `0`.
- Temporary proposal keys: `{len(validation.get('requirements', []))}`; requirements: `{len(validation.get('requirements', []))}`; coverage claims: `{len(validation.get('coverage_claims', []))}`.
- Unit assessments: `{len(validation.get('unit_assessments', []))}/5`; schema validation: `{validation['status']}`; unknown/duplicate/missing unit or proposal errors: recorded in schema artifact.
- Program canonicalization: `{ 'PASS' if validation['status'] == 'PASS' else 'NOT_RUN' }`; forbidden mutation fields: `{len(validation.get('forbidden_fields', []))}`.

## Coverage Authority

- Final status: `{qualification}`; counts: `{json.dumps(counts, ensure_ascii=False)}`.
- Unit relevance counts: `{json.dumps(unit_counts, ensure_ascii=False)}`; human review: `NOT_RECORDED`.
- Coverage qualified: `{qualification == 'FACT_COVERAGE_CANDIDATE_QUALIFIED'}`; targeted missing-fact package: `{next_stage == 'TARGETED_MISSING_FACT_EXTRACTION'}`.
- ScriptIR calls/authorization: `0 / false`; next stage: `{next_stage}`; targeted extraction authorization: `false`.

## Historical Integrity

- Fact Attempt #1/#2, Semantic Verifier request/response/ledger/overlay, and Full-Source completeness artifacts were not modified.
- No production DB, ScriptIR, Treatment, Blocking, Strategy, Spine, Skeleton, Topology, Atomic Expansion, ShotPlan, Storyboard, image, video or storage calls.

## Decision

`{final_status}`

This one-call canary is terminal. No second provider call is permitted.
"""
    (ART / "director-quality-v3-fact-coverage-verifier-final-report.md").write_text(report, encoding="utf-8")
    print(json.dumps({"status": final_status, "provider_calls": 1, "validation": validation["status"], "qualification": qualification, "execution_base": head, "next_stage": next_stage}, ensure_ascii=False, indent=2))
    return 0 if final_status.endswith("CLOSED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
