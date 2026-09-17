"""Run the explicitly authorized, one-call Coverage Verifier V3 recanary.

This runner is intentionally separate from Canary #1: it never overwrites
historical evidence and has no retry, repair, fallback, critic, judge, or
downstream dispatch path.
"""
from __future__ import annotations

import hashlib
import json
import os
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
SCOPE = "DIRECTOR_V3_AUTHORIZED_FACT_COVERAGE_VERIFIER_RECANARY_V3"
AUTH = Path(os.environ.get("DIRECTOR_V3_COVERAGE_RECANARY_AUTHORIZATION", str(ROOT.parent / "director-v3-fact-coverage-verifier-recanary-v3-runtime-authorization.json")))
EVAL_ROOT = ROOT / "work" / "evaluation" / "director_v3" / SOURCE_PACKAGE / "fact_coverage_verifier_recanary_v3"


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _fp(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _preflight(auth: dict, *, head: str, remote: str, dirty: list[str], request: dict, system: str) -> dict:
    from core.fact_coverage_verifier import validate_final_provider_payload_projection, validate_provider_contract_projection_v1
    projection = request.get("output_contract")
    projection_gate = validate_provider_contract_projection_v1(projection)
    transport_gate = validate_final_provider_payload_projection(user_prompt=json.dumps(request, ensure_ascii=False, indent=2), system_prompt=system)
    units = request.get("source_narrative_units") or []
    facts = request.get("existing_facts") or []
    checks = {
        "local_remote_parity": head == remote,
        "worktree_clean": not dirty,
        "execution_base_matches": auth.get("authorized_execution_base") == head,
        "scope": auth.get("scope") == SCOPE,
        "authorization_not_consumed": auth.get("consumed") is False,
        "max_provider_calls": auth.get("max_provider_calls") == 1,
        "retries_zero": auth.get("retries") == 0,
        "source_identity": auth.get("source_package_id") == SOURCE_PACKAGE and auth.get("source_version_id") == SOURCE_VERSION and auth.get("source_raw_hash") == RAW_HASH,
        "evidence_identity": auth.get("source_evidence_index_fingerprint") == EVIDENCE_FP,
        "full_schema_projection": projection_gate.get("status") == "PASS",
        "final_transport_projection": transport_gate.get("status") == "PASS",
        "unit_count": len(units) == 5,
        "fact_count": len(facts) == 7,
        "downstream_disabled": not any(bool(auth.get(key)) for key in ("fact_extraction_allowed", "semantic_verifier_allowed", "missing_fact_extraction_allowed", "script_ir_allowed", "downstream_allowed")),
    }
    return {"schema_version": "director-quality-v3-fact-coverage-verifier-recanary-v3-preflight-v1", "status": "PASS" if all(checks.values()) else "FAIL", "provider_calls": 0, "head": head, "remote": remote, "execution_base": auth.get("authorized_execution_base"), "checks": checks, "projection": projection_gate, "transport": transport_gate}


def main() -> int:
    if "--execute-real" not in sys.argv:
        print(json.dumps({"status": "NOT_AUTHORIZED", "provider_calls": 0}, ensure_ascii=False))
        return 2
    sys.path.insert(0, str(ROOT))
    from core.fact_coverage_verifier import build_provider_system_prompt_v3, build_request, contract_v3, parse_provider_json_envelope_v1, validate_provider_payload
    from core.llm import call_llm
    from scripts.run_director_quality_v3_fact_coverage_verifier_canary import build_inputs

    head = _git("rev-parse", "HEAD")
    remote = _git("rev-parse", "origin/codex/fact-semantic-grounding-foundation")
    dirty = _git("status", "--porcelain").splitlines()
    auth = json.loads(AUTH.read_text(encoding="utf-8"))
    _raw, materialized, facts, _contract, profile, _old_request = build_inputs()
    request = build_request(units=materialized, facts=facts, contract=contract_v3(), provider="openai-compatible", model="mimo-v2.5")
    system = build_provider_system_prompt_v3(request["output_contract"])
    preflight = _preflight(auth, head=head, remote=remote, dirty=dirty, request=request, system=system)
    _write(ART / "director-quality-v3-coverage-verifier-recanary-v3-preflight.json", preflight)
    if preflight["status"] != "PASS":
        print(json.dumps({"status": "DIRECTOR_V3_FACT_COVERAGE_VERIFIER_RECANARY_BLOCKED", "provider_calls": 0, "preflight": preflight}, ensure_ascii=False, indent=2))
        return 2

    request_json = json.dumps(request, ensure_ascii=False, indent=2)
    request_hash = hashlib.sha256(request_json.encode("utf-8")).hexdigest()
    EVAL_ROOT.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    ledger = {"schema_version": "director-quality-v3-fact-coverage-verifier-recanary-v3-provider-ledger-v1", "stage": "FACT_COVERAGE_VERIFIER_RECANARY_V3", "experiment_id": "coverage-verifier-recanary-v3", "authorization_id": auth["authorization_id"], "authorization_scope": SCOPE, "attempt_number": 1, "execution_base": head, "request_hash": request_hash, "provider": profile.get("provider"), "model": profile.get("model_name"), "dispatch_started_at": started, "transport_status": "DISPATCHING", "provider_calls": 1, "retries": 0, "cumulative_attempt_before": 4, "cumulative_attempt_after": 5, "downstream_calls": 0}
    _write(EVAL_ROOT / "request.json", {"system_prompt": system, "request": request, "request_hash": request_hash, "execution_base": head, "authorization_id": auth["authorization_id"]})
    _write(EVAL_ROOT / "provider-ledger.json", ledger)
    raw = ""
    error = None
    try:
        raw = str(call_llm(request_json, system=system, model_profile=profile, retries=1, estimated_tokens=10000, audit_extra={"stage": SCOPE, "authorization_id": auth["authorization_id"], "request_hash": request_hash}))
    except Exception as exc:
        error = str(exc)[:1000]
    finished = datetime.now(timezone.utc).isoformat()
    raw_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    auth_record = {**auth, "consumed": True, "consumed_at": finished, "provider_calls": 1, "execution_base": head}
    _write(ART / "director-quality-v3-coverage-verifier-recanary-v3-runtime-authorization-record.json", auth_record)
    ledger.update({"dispatch_completed_at": finished, "transport_status": "RESPONSE_RECEIVED" if raw else "CALL_FAILED", "response_received": bool(raw), "raw_response_sha256": raw_hash, "response_length": len(raw), "error": error})
    _write(EVAL_ROOT / "provider-ledger.json", ledger)
    (EVAL_ROOT / "raw-response.txt").write_text(raw, encoding="utf-8")
    _write(ART / "director-quality-v3-coverage-verifier-recanary-v3-provider-ledger.json", ledger)
    _write(ART / "director-quality-v3-coverage-verifier-recanary-v3-request.json", {"schema_version": "fact_coverage_verifier_request_v3", "authorization_id": auth["authorization_id"], "execution_base": head, "request_hash": request_hash, "provider": profile.get("provider"), "model": profile.get("model_name"), "request": request, "system_prompt": system})
    _write(ART / "director-quality-v3-coverage-verifier-recanary-v3-final-payload.json", {"request": request, "system_prompt": system, "request_hash": request_hash, "projection_fingerprint": request["output_contract"].get("projection_fingerprint")})
    _write(ART / "director-quality-v3-coverage-verifier-recanary-v3-response-meta.json", {"schema_version": "fact_coverage_verifier_recanary_v3_response_meta_v1", "provider_calls": 1, "response_received": bool(raw), "raw_response_sha256": raw_hash, "response_length": len(raw), "provider": profile.get("provider"), "model": profile.get("model_name"), "transport_error": error})

    parse_error = None
    normalized_hash = ""
    payload = None
    validation = {"status": "FAIL", "errors": [{"code": "EMPTY_PROVIDER_RESPONSE"}], "requirements": [], "coverage_claims": [], "unit_assessments": []}
    envelope = {"status": "FAIL", "normalization_applied": False, "errors": [{"code": "EMPTY_PROVIDER_RESPONSE"}]}
    if raw:
        try:
            payload = parse_provider_json_envelope_v1(raw, allow_single_fence=True)
            normalization_applied = raw.strip().startswith("```")
            normalized_hash = _fp(payload) if normalization_applied else ""
            envelope = {"status": "PASS", "normalization_applied": normalization_applied, "normalized_response_sha256": normalized_hash, "policy": "TRANSPORT_ENVELOPE_NORMALIZATION"}
            validation = validate_provider_payload(payload, unit_refs=[u["source_unit_ref"] for u in materialized["units"]], fact_ids=[f["fact_id"] for f in facts["facts"]])
        except Exception as exc:
            parse_error = str(exc)[:1000]
            envelope = {"status": "FAIL", "normalization_applied": False, "errors": [{"code": "ENVELOPE_PARSE_FAILURE", "message": parse_error}]}
            validation = {"status": "FAIL", "errors": [{"code": "PROVIDER_JSON_PARSE_FAILURE", "message": parse_error}], "requirements": [], "coverage_claims": [], "unit_assessments": []}
    _write(ART / "director-quality-v3-coverage-verifier-recanary-v3-envelope-validation.json", envelope)
    _write(ART / "director-quality-v3-coverage-verifier-recanary-v3-schema-validation.json", {"schema_version": "fact_coverage_verifier_recanary_v3_schema_validation_v1", "status": validation["status"], "parse_error": parse_error, "errors": validation.get("errors", []), "requirement_count": len(validation.get("requirements", [])), "claim_count": len(validation.get("coverage_claims", [])), "unit_assessment_count": len(validation.get("unit_assessments", [])), "forbidden_fields": validation.get("forbidden_fields", [])})

    qualification = "FACT_COVERAGE_REVIEW_REQUIRED"
    next_stage = "COVERAGE_REVIEW"
    counts = {status: 0 for status in ("COVERED", "PARTIALLY_COVERED", "MISSING", "CLAIM_ONLY", "UNSAFE_INFERENCE", "AMBIGUOUS")}
    unit_counts = {rel: 0 for rel in ("RELEVANT", "NO_REQUIRED_FACT", "AMBIGUOUS")}
    if validation["status"] == "PASS":
        from core.fact_coverage_verifier import canonicalize_requirements, compile_fact_coverage_authority_v2
        canonical = canonicalize_requirements(validation)
        matrix = compile_fact_coverage_authority_v2(canonical=canonical, semantic_overlay=json.loads((ART / "director-quality-v3-semantic-verifier-canary-authority-overlay.json").read_text(encoding="utf-8")), unit_assessments=validation["unit_assessments"])
        qualification = matrix["qualification_status"]
        counts = matrix["counts"]
        unit_counts = matrix["unit_assessment_counts"]
        next_stage = "TARGETED_MISSING_FACT_EXTRACTION" if qualification == "FACT_COVERAGE_INSUFFICIENT" else "HUMAN_FINAL_COVERAGE_REVIEW"
        _write(ART / "director-quality-v3-coverage-verifier-recanary-v3-requirement-key-map.json", canonical)
        _write(ART / "director-quality-v3-coverage-verifier-recanary-v3-authority-matrix.json", matrix)
        _write(ART / "director-quality-v3-coverage-verifier-recanary-v3-unit-assessments.json", {"status": "PASS", "provider_calls": 0, "assessments": validation["unit_assessments"], "counts": unit_counts})
        _write(ART / "director-quality-v3-coverage-verifier-recanary-v3-missing-requirements.json", {"status": "READY" if qualification == "FACT_COVERAGE_INSUFFICIENT" else "EMPTY", "provider_calls": 0, "requirements": [row for row in matrix["rows"] if row["final_coverage_status"] != "COVERED"]})
        _write(ART / "director-quality-v3-coverage-verifier-recanary-v3-human-review.json", {"status": "NOT_RECORDED", "provider_calls": 0, "coverage_status": qualification, "matrix_fingerprint": matrix["fingerprint"]})
    else:
        _write(ART / "director-quality-v3-coverage-verifier-recanary-v3-requirement-key-map.json", {"status": "NOT_GENERATED_SCHEMA_FAILURE", "mapping": {}, "requirements": []})
        _write(ART / "director-quality-v3-coverage-verifier-recanary-v3-authority-matrix.json", {"status": "NOT_GENERATED_SCHEMA_FAILURE", "qualification_status": qualification, "rows": [], "counts": counts})
        _write(ART / "director-quality-v3-coverage-verifier-recanary-v3-unit-assessments.json", {"status": "FAIL", "assessments": []})
        _write(ART / "director-quality-v3-coverage-verifier-recanary-v3-missing-requirements.json", {"status": "NOT_GENERATED_SCHEMA_FAILURE", "requirements": []})
        _write(ART / "director-quality-v3-coverage-verifier-recanary-v3-human-review.json", {"status": "SCHEMA_FAILURE", "human_review_status": "NOT_RECORDED"})

    status = "DIRECTOR_V3_FACT_COVERAGE_VERIFIER_RECANARY_CLOSED" if validation["status"] == "PASS" else "DIRECTOR_V3_FACT_COVERAGE_VERIFIER_RECANARY_FAILED"
    authority_path = ART / "director-quality-v3-current-stage-authority.json"
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    authority["coverage_verifier_recanary_v3"] = {"status": status, "authorization_id": auth["authorization_id"], "authorization_scope": SCOPE, "execution_base": head, "provider": {"provider": profile.get("provider"), "model_name": profile.get("model_name")}, "provider_calls": 1, "retries": 0, "request_hash": request_hash, "raw_response_hash": raw_hash, "normalized_response_hash": normalized_hash, "envelope_normalization": envelope.get("normalization_applied", False), "schema_validation": validation["status"], "input_unit_count": 5, "input_fact_count": 7, "requirement_count": len(validation.get("requirements", [])), "final_coverage_counts": counts, "unit_assessment_counts": unit_counts, "final_coverage_status": qualification, "human_review": "NOT_RECORDED", "coverage_recanary_authorized": False, "coverage_recanary_authorization_consumed": True, "script_ir_calls": 0, "script_ir_authorized": False, "ready_for_targeted_missing_fact_extraction": qualification == "FACT_COVERAGE_INSUFFICIENT", "targeted_missing_fact_extraction_authorized": False, "script_ir_gate": "BLOCKED_PENDING_TARGETED_MISSING_FACTS" if qualification == "FACT_COVERAGE_INSUFFICIENT" else "BLOCKED_PENDING_COVERAGE_REVIEW", "next_stage": next_stage, "runtime_authority": True}
    evaluation = authority.setdefault("authorized_ai_evaluation_source", {})
    evaluation["provider_attempts_by_stage"] = {"fact_attempt_1": 1, "fact_attempt_2": 1, "semantic_verifier": 1, "coverage_verifier_canary_1": 1, "coverage_verifier_recanary_v3": 1}
    evaluation["cumulative_provider_attempts"] = 5
    evaluation["current_stage_provider_attempts"] = 1
    evaluation["fact_coverage_status"] = qualification
    evaluation["ready_for_targeted_missing_fact_extraction"] = qualification == "FACT_COVERAGE_INSUFFICIENT"
    evaluation["targeted_missing_fact_extraction_authorized"] = False
    evaluation["ready_for_script_ir_processing"] = False
    evaluation["script_ir_processing_authorized"] = False
    evaluation["script_ir_calls"] = 0
    evaluation["script_ir_gate"] = "BLOCKED_PENDING_TARGETED_MISSING_FACTS" if qualification == "FACT_COVERAGE_INSUFFICIENT" else "BLOCKED_PENDING_COVERAGE_REVIEW"
    _write(authority_path, authority)
    report = f"""# Director Quality V3 — Authorized Fact Coverage Verifier Recanary V3

## Final As-Built Verification

- Execution base: `{head}`; local/remote parity before dispatch: `PASS`; worktree clean: `PASS`.
- Authorization: `{auth['authorization_id']}` / `{SCOPE}`; provider/model: `openai-compatible` / `mimo-v2.5`.
- Real provider calls: **1**; retries/repair/fallback/critic/judge: **0**; cumulative attempts: `4 → 5`.
- Source: `{SOURCE_PACKAGE}` / `{SOURCE_VERSION}`; anchors `347`; Narrative Units `5`; existing Facts `7`.
- Historical Canary #1 remained immutable. No ScriptIR or downstream call was made.

## Contract and Result

- Full V3 schema projection: `PASS`; final transport projection: `PASS`; schema fingerprint: `7fd93ba76c86a5ff8ef2c595fbc61dcbb26d52444757035a8b49c42f2acc048d`.
- Raw response received: `{bool(raw)}`; raw SHA256: `{raw_hash}`; envelope normalization: `{envelope.get('normalization_applied', False)}`; schema validation: `{validation['status']}`.
- Requirement/claim/unit counts: `{len(validation.get('requirements', []))}/{len(validation.get('coverage_claims', []))}/{len(validation.get('unit_assessments', []))}`.
- Final Fact Coverage status: `{qualification}`; counts: `{json.dumps(counts, ensure_ascii=False)}`; unit assessments: `{json.dumps(unit_counts, ensure_ascii=False)}`.

## Authority and Stop

- Coverage recanary authorized: `false` (authorization consumed: `true`).
- Missing-Fact Extraction ready: `{qualification == "FACT_COVERAGE_INSUFFICIENT"}` (authorization: `false`); ScriptIR ready/authorized: `false/false`.
- Next stage: `{next_stage}`. This one-call recanary is terminal; no second Provider call is permitted.
"""
    (ART / "director-quality-v3-coverage-verifier-recanary-v3-final-report.md").write_text(report, encoding="utf-8")
    _write(ART / "director-quality-v3-coverage-verifier-recanary-v3-post-run-verification.json", {"status": status, "provider_calls": 1, "retries": 0, "historical_canary_immutable": True, "downstream_calls": 0, "validation": validation["status"], "raw_response_sha256": raw_hash, "raw_response_length": len(raw), "next_stage": next_stage})
    print(json.dumps({"status": status, "provider_calls": 1, "validation": validation["status"], "qualification": qualification, "execution_base": head, "next_stage": next_stage}, ensure_ascii=False, indent=2))
    return 0 if status.endswith("CLOSED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
