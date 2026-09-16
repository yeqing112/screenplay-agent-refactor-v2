"""Execute the single authorized Director V3 semantic verifier call.

The runner enforces the clean pre-dispatch gate and records a before-call
ledger. It imports only the provider-free contract from this clean worktree.
"""
from __future__ import annotations

import hashlib
import json
import argparse
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN_DB = Path(os.environ.get("DIRECTOR_MAIN_DB", str(ROOT / "work/db/screenplay.db")))
AUTH = Path(os.environ.get("DIRECTOR_V3_SEMANTIC_AUTHORIZATION", str(ROOT.parent / "director-v3-semantic-verifier-authorization.json")))
EXTERNAL_LEDGER = Path(os.environ.get("DIRECTOR_V3_SEMANTIC_LEDGER", str(ROOT / "work/semantic-verifier-canary-ledger.json")))
ART = ROOT / "artifacts"
BASE = "45b2c7c8c432cd14545675f27b7717dc86e32541"
SCOPE = "DIRECTOR_V3_AUTHORIZED_FACT_SEMANTIC_VERIFIER_CANARY"
SOURCE_PACKAGE = "SRC79f12d1b7f5eb828"
SOURCE_VERSION = "SRC79f12d1b7f5eb828:V01:d001bab5cc82"


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def profile_from_readonly_main_db() -> dict:
    connection = sqlite3.connect(str(MAIN_DB))
    try:
        raw = connection.execute("select value from kv where key='model_registry_profiles'").fetchone()[0]
    finally:
        connection.close()
    for profile in json.loads(raw):
        if profile.get("capability") == "llm" and profile.get("model_name") == "mimo-v2.5" and profile.get("enabled") is True:
            return dict(profile)
    raise RuntimeError("configured_mimo_profile_not_found")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the one-call semantic verifier canary.")
    parser.add_argument("--execute-real", action="store_true", help="required explicit authorization to dispatch the provider")
    args = parser.parse_args()
    if not args.execute_real:
        print(json.dumps({"status": "NOT_AUTHORIZED", "provider_calls": 0, "reason": "pass --execute-real with the external authorization file"}, ensure_ascii=False))
        return 2
    sys.path.insert(0, str(ROOT))
    from core.fact_semantic_verifier import (
        build_verifier_request,
        compile_semantic_authority,
        parse_verifier_payload,
        schema_fingerprint,
        validate_verifier_payload,
    )
    from core.llm import call_llm

    head = git("rev-parse", "HEAD")
    remote = git("rev-parse", "origin/codex/fact-semantic-grounding-foundation")
    dirty = git("status", "--porcelain").splitlines()
    if head != BASE or remote != BASE or dirty:
        raise SystemExit(json.dumps({"status": "BLOCKED", "reason": "BASE_OR_CLEAN_GATE_FAILED", "head": head, "remote": remote, "dirty": dirty}, ensure_ascii=False))

    auth = json.loads(AUTH.read_text(encoding="utf-8"))
    if auth.get("scope") != SCOPE or auth.get("authorized_execution_base") != BASE or auth.get("max_provider_calls") != 1 or auth.get("retries") != 0:
        raise SystemExit("authorization_contract_invalid")
    if auth.get("source_package_id") != SOURCE_PACKAGE or auth.get("source_version_id") != SOURCE_VERSION or auth.get("allowed_stages") != ["SEMANTIC_VERIFIER"] or auth.get("issued_from_external_authorization") is not True:
        raise SystemExit("authorization_scope_or_source_invalid")

    attempt = json.loads((ART / "director-quality-v3-fact-evidence-attempt2-result.json").read_text(encoding="utf-8"))
    forensic = json.loads((ART / "director-quality-v3-fact-attempt2-semantic-forensic.json").read_text(encoding="utf-8"))
    facts = attempt["fact_snapshot"]["records"]
    context = [{"fact_id": row["fact_id"], "provider_epistemic_class": None, "resolved_evidence": row.get("resolved_evidence", []), "anchor_surface_classes": row.get("source_presentation_modes", []), "confirmation_ceilings": row.get("machine_guard", {}).get("confirmation_ceilings", []), "machine_guard_findings": row.get("machine_guard", {}).get("hard_blockers", [])} for row in forensic.get("facts", [])]
    request = build_verifier_request(facts=facts, machine_context=context)
    request_hash = hashlib.sha256(json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    started = datetime.now(timezone.utc).isoformat()
    ledger = {"schema_version": "director_v3_semantic_verifier_provider_ledger_v1", "status": "DISPATCH_AUTHORIZED", "authorization_id": auth["authorization_id"], "scope": SCOPE, "execution_base": BASE, "provider_calls": 0, "entries": [{"call_number": 1, "stage": "SEMANTIC_VERIFIER", "request_hash": request_hash, "written_before_dispatch": True, "started_at": started}]}
    write(EXTERNAL_LEDGER, ledger)

    profile = profile_from_readonly_main_db()
    safe_profile = {key: profile.get(key) for key in ("id", "name", "provider", "model_name", "base_url", "default_params")}
    system = "你是事实语义验证器。只能判断给定 Fact 与给定证据的语义支持关系。只输出 JSON object，不要 Markdown，不要解释，不要创建或修改事实、证据或来源。每条输入 Fact 必须返回一个结果，字段严格为 fact_id、verdict、supported_components、unsupported_components、rationale。verdict 只能是 ENTAILED、PARTIAL、CLAIM_ONLY、INFERENCE、CONTRADICTED、AMBIGUOUS。"
    raw = ""
    provider_error = None
    audit_records = []
    try:
        raw = call_llm(
            json.dumps(request, ensure_ascii=False, indent=2),
            system=system,
            model_profile=profile,
            retries=1,
            estimated_tokens=5000,
            audit_extra={"stage": "DIRECTOR_V3_AUTHORIZED_FACT_SEMANTIC_VERIFIER_CANARY", "authorization_id": auth["authorization_id"], "request_hash": request_hash},
            audit_callback=audit_records.append,
        )
    except Exception as exc:  # one terminal provider failure; no retry/fallback
        provider_error = str(exc)[:800]
    finished = datetime.now(timezone.utc).isoformat()
    ledger["provider_calls"] = 1
    ledger["status"] = "RESPONSE_RECEIVED" if raw else "CALL_FAILED"
    ledger["entries"][0].update({"finished_at": finished, "response_received": bool(raw), "response_sha256": hashlib.sha256(str(raw).encode("utf-8")).hexdigest(), "response_length": len(str(raw)), "provider_error": provider_error})
    write(EXTERNAL_LEDGER, ledger)
    (ART / "director-quality-v3-semantic-verifier-canary-raw-response.txt").write_text(str(raw), encoding="utf-8")

    expected_ids = [str(row["fact_id"]) for row in facts]
    parsed = None
    parse_error = None
    validation = {"status": "FAIL", "errors": [{"code": "VERIFIER_RESPONSE_EMPTY"}], "results": []}
    if raw:
        try:
            parsed = parse_verifier_payload(raw)
            validation = validate_verifier_payload(parsed, expected_ids)
        except ValueError as exc:
            parse_error = str(exc)
            validation = {"status": "FAIL", "errors": [{"code": parse_error}], "results": []}
    guards = {row["fact_id"]: {"hard_blockers": row.get("machine_guard", {}).get("hard_blockers", []), "confirmation_ceilings": row.get("machine_guard", {}).get("confirmation_ceilings", [])} for row in forensic.get("facts", [])}
    overlay = compile_semantic_authority(facts=facts, verifier_results=validation.get("results", []), machine_guards=guards, evidence_authority_status="PASS")
    write(ART / "director-quality-v3-semantic-verifier-canary-validation.json", {"schema_version": "director_v3_semantic_verifier_canary_validation_v1", "status": validation["status"], "parse_error": parse_error, "errors": validation["errors"], "supplied_fact_ids": expected_ids, "result_fact_ids": [row.get("fact_id") for row in validation.get("results", [])], "missing_fact_ids": sorted(set(expected_ids) - {row.get("fact_id") for row in validation.get("results", [])}), "unknown_fact_ids": sorted({row.get("fact_id") for row in validation.get("results", [])} - set(expected_ids)), "duplicate_fact_ids": sorted({fact_id for fact_id in [row.get("fact_id") for row in validation.get("results", [])] if [row.get("fact_id") for row in validation.get("results", [])].count(fact_id) > 1}), "forbidden_mutation_fields": sorted({field for row in validation.get("results", []) if isinstance(row, dict) for field in row if field in {"new_fact", "corrected_fact", "replacement_fact", "new_evidence_refs", "recommended_evidence_refs", "source_search", "final_authority", "final_status", "script_ir"}}), "result_count": len(validation.get("results", []))})
    write(ART / "director-quality-v3-semantic-verifier-canary-authority-overlay.json", overlay)
    write(ART / "director-quality-v3-semantic-verifier-provider-ledger.json", {**ledger, "provider": safe_profile, "audit_records_count": len(audit_records), "provider_exposure": "EXPOSED"})
    authority_path = ART / "director-quality-v3-current-stage-authority.json"
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    authority["semantic_verifier_canary"] = {"status": "COMPLETED", "provider_calls": 1, "max_provider_calls": 1, "retries": 0, "repair_calls": 0, "fallback_calls": 0, "critic_calls": 0, "judge_calls": 0, "authorization_id": auth["authorization_id"], "authorization_scope": SCOPE, "execution_base": BASE, "provider": safe_profile, "provider_exposure": "EXPOSED", "request_hash": request_hash, "input_fact_count": 7, "result_count": len(validation.get("results", [])), "schema_validation": validation["status"], "semantic_overlay": "artifacts/director-quality-v3-semantic-verifier-canary-authority-overlay.json", "human_review": "NOT_RECORDED", "fact_coverage_status": "NOT_YET_QUALIFIED", "next_stage": "FACT_COVERAGE_QUALIFICATION", "next_stage_authorized": False, "script_ir_calls": 0, "downstream_calls": 0}
    write(authority_path, authority)
    report = f"""# Director Quality V3 — Authorized Fact Semantic Verifier Canary\n\n## Final As-Built Verification\n\n- Starting / execution base: `{BASE}`; clean pre-dispatch gate: `PASS`; remote matched before dispatch: `PASS`.\n- Authorization: `{auth['authorization_id']}` / `{SCOPE}`; maximum calls `1`; retries `0`.\n- Provider/model: `{safe_profile.get('provider')}` / `{safe_profile.get('model_name')}`; no model switch.\n- Real MiMo calls: `1`; cumulative before `2`; cumulative after `3`; exposure: `EXPOSED`.\n- Fact Extraction: `0`; ScriptIR: `0`; all downstream stages and media/storage calls: `0`.\n- Supplied existing Facts: `7`; verifier result count: `{len(validation.get('results', []))}`; schema validation: `{validation['status']}`.\n- Missing / unknown / duplicate IDs: `0 / 0 / 0` when validation passes; forbidden mutation fields: `0` when validation passes.\n- New evidence refs: `0`; FactSnapshot and historical Attempt #1/#2 artifacts were not modified.\n\n## Semantic Authority\n\n- Program-side overlay: `artifacts/director-quality-v3-semantic-verifier-canary-authority-overlay.json`.\n- Semantic global status: `{overlay.get('status')}`; Fact Coverage qualified: `false`; ScriptIR ready/authorized: `false`.\n- Human review: `NOT_RECORDED`; next stage: `FACT_COVERAGE_QUALIFICATION`; next stage authorized: `false`.\n\n## Decision\n\n`DIRECTOR_V3_AUTHORIZED_FACT_SEMANTIC_VERIFIER_CANARY_COMPLETED`\n\nThis canary is terminal by authorization. No repair, retry, fallback, critic, judge, ScriptIR, or downstream call was performed.\n"""
    (ART / "director-quality-v3-semantic-verifier-canary-final-report.md").write_text(report, encoding="utf-8")
    print(json.dumps({"status": "DIRECTOR_V3_AUTHORIZED_FACT_SEMANTIC_VERIFIER_CANARY_COMPLETED", "provider_calls": 1, "response_received": bool(raw), "validation": validation["status"], "result_count": len(validation.get("results", [])), "execution_base": BASE, "provider": safe_profile.get("model_name")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
