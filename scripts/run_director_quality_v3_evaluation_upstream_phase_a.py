"""Provider-free preflight for the authorized Evaluation Source Phase A.

This runner deliberately stops at SOURCE_ACCEPTED when repository or source
gates are not satisfied.  ``--execute-real`` is only a guarded dispatch path:
it cannot bypass the expected HEAD, clean-worktree, provenance, exposure or
call-budget gates, and it never retries.  No provider client is imported by
the preflight path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"
EVAL_ROOT = ROOT / "work/evaluation/director_v3/SRC79f12d1b7f5eb828/upstream_phase_a"
HISTORICAL_EXPECTED_HEAD = "63c93d6e1f78a4777fff9c3e329f5eeb723846eb"
# Kept as a compatibility alias for historical tests and reports.  New
# executions resolve their exact immutable base from the reconciliation
# artifact instead of silently treating an arbitrary current HEAD as valid.
EXPECTED_HEAD = HISTORICAL_EXPECTED_HEAD
EXPECTED_REMOTE_REF = "origin/codex/unify-formal-workspace"
EXECUTION_BASE_ARTIFACT = ART / "director-quality-v3-phase-a-execution-base-reconciliation.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _d(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_if(enabled: bool, path: Path, value: Any) -> None:
    if enabled:
        _write(path, value)


def _git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _remote_head() -> dict[str, Any]:
    try:
        value = subprocess.check_output(["git", "rev-parse", EXPECTED_REMOTE_REF], cwd=ROOT, text=True, stderr=subprocess.STDOUT).strip()
        return {"status": "PASS", "sha": value}
    except subprocess.CalledProcessError as exc:
        return {"status": "UNAVAILABLE", "sha": "", "error": str(exc.output or "")[:400]}


def _dirty_paths() -> list[str]:
    output = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT, text=True)
    return [line[3:].strip().strip('"') if len(line) >= 4 else line for line in output.splitlines() if line]


def _provider_snapshot() -> dict[str, Any]:
    try:
        from api.model_registry import get_default_profile
        profile = get_default_profile("llm") or {}
        base_url = str(profile.get("base_url") or "")
        from urllib.parse import urlparse
        parsed = urlparse(base_url)
        return {
            "status": "PASS" if profile else "FAIL",
            "provider": str(profile.get("provider") or ""),
            "model": str(profile.get("model_name") or ""),
            "endpoint_class": parsed.hostname or "",
            "profile_id": str(profile.get("id") or ""),
            "api_key_configured": bool(str(profile.get("api_key") or "").strip()),
        }
    except Exception as exc:
        return {"status": "FAIL", "provider": "", "model": "", "endpoint_class": "", "profile_id": "", "api_key_configured": False, "error": str(exc)[:400]}


def _status_code(*, blocked: bool) -> str:
    return "DIRECTOR_V3_EVALUATION_UPSTREAM_PHASE_A_BLOCKED" if blocked else "DIRECTOR_V3_EVALUATION_UPSTREAM_PHASE_A_PREFLIGHT_PASS"


def _request_hash(request: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _execution_base() -> dict[str, Any]:
    """Resolve the explicitly frozen Phase A execution base.

    Before reconciliation exists, the historical HEAD is retained only as a
    label and cannot authorize execution.  A real run requires a committed,
    pushed, exact base recorded by the reconciliation artifact.
    """
    try:
        value = json.loads(EXECUTION_BASE_ARTIFACT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "HISTORICAL_ONLY", "commit": HISTORICAL_EXPECTED_HEAD}
    commit = str(value.get("new_execution_base") or value.get("execution_base_commit") or "").strip()
    if value.get("execution_base_pushed") is True and len(commit) == 40:
        return {"status": "REBASELINED", "commit": commit}
    return {"status": "UNPUSHED", "commit": commit or HISTORICAL_EXPECTED_HEAD}


def _execute_authorized_phase_a(*, source: dict[str, Any], provider: dict[str, Any], eval_root: Path, authorization: dict[str, Any]) -> dict[str, Any]:
    """Dispatch exactly the two bounded Phase A calls after all gates pass.

    The callback is intentionally local so request/response evidence is saved
    before the next stage can run.  ``retries=0`` means one HTTP attempt in
    ``core.llm.call_llm``; a failed FactSnapshot returns immediately and never
    reaches ScriptIR.
    """
    from api.model_registry import get_default_profile
    from core.evaluation_upstream_phase_a import (
        build_fact_request,
        build_script_ir_request,
        run_with_provider_calls,
    )
    from core.llm import call_llm

    profile = get_default_profile("llm") or {}
    requests: list[dict[str, Any]] = []
    responses: list[str] = []
    ledger: list[dict[str, Any]] = []
    attempted_calls = 0
    system = "Return only the JSON object required by the supplied evaluation contract. Do not add directing choices, inferred test answers, retries, or commentary."

    def dispatch(request: dict[str, Any]) -> str:
        nonlocal attempted_calls
        requests.append(request)
        attempted_calls += 1
        stage = str(request.get("task") or "unknown")
        stage_name = "FACT_EXTRACTION" if len(ledger) == 0 else "SCRIPT_IR"
        entry = {
            "stage": stage_name,
            "attempt_number": attempted_calls,
            "dispatched": True,
            "request_hash": _request_hash(request),
            "source_package_id": authorization["source_package_id"],
            "source_version_id": authorization["source_version_id"],
            "execution_base": authorization["authorized_execution_base"],
            "provider": provider.get("provider"),
            "model": provider.get("model"),
            "status": "DISPATCHING",
            "response_received": False,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        ledger.append(entry)
        eval_root.mkdir(parents=True, exist_ok=True)
        _write(eval_root / "dispatch-ledger.json", {"schema_version": "director_v3_phase_a_dispatch_ledger_v1", "entries": ledger})
        (eval_root / f"{stage_name.lower()}-request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        try:
            response = str(call_llm(
                json.dumps(request, ensure_ascii=False),
                system=system,
                model_profile=profile,
                retries=0,
                estimated_tokens=7000,
                max_tokens=12000,
                audit_extra={"phase": "director_v3_evaluation_upstream_phase_a", "stage": stage, "authorization_id": authorization["authorization_id"]},
            ) or "")
        except Exception as exc:
            entry.update({"status": "TRANSPORT_FAILED", "error": str(exc)[:800], "finished_at": datetime.now(timezone.utc).isoformat()})
            _write(eval_root / "dispatch-ledger.json", {"schema_version": "director_v3_phase_a_dispatch_ledger_v1", "entries": ledger})
            raise
        entry.update({
            "status": "RESPONSE_RECEIVED" if response else "RESPONSE_EMPTY",
            "response_received": bool(response),
            "response_sha256": hashlib.sha256(response.encode("utf-8")).hexdigest(),
            "response_length": len(response),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        })
        (eval_root / f"{stage_name.lower()}-response-raw.txt").write_text(response, encoding="utf-8")
        _write(eval_root / "dispatch-ledger.json", {"schema_version": "director_v3_phase_a_dispatch_ledger_v1", "entries": ledger})
        responses.append(response)
        return response

    try:
        result = run_with_provider_calls(source=source, provider_config=provider, call_provider=dispatch)
    except Exception as exc:
        result = {
            "status": "DIRECTOR_V3_AUTHORIZED_EVALUATION_UPSTREAM_PHASE_A_FAILED",
            "provider_calls": attempted_calls,
            "attempted_provider_calls": attempted_calls,
            "provider_exposure": "EXPOSED" if attempted_calls else "NOT_EXPOSED_CONFIRMED",
            "error": str(exc)[:800],
        }
    result["provider_calls"] = attempted_calls
    result["attempted_provider_calls"] = attempted_calls
    result["provider_exposure"] = "EXPOSED" if attempted_calls else "NOT_EXPOSED_CONFIRMED"
    result["dispatch_ledger"] = ledger
    eval_root.mkdir(parents=True, exist_ok=True)
    for index, request in enumerate(requests):
        stage = "fact" if index == 0 else "script-ir"
        _write(eval_root / f"{stage}-request.json", request)
    for index, response in enumerate(responses):
        stage = "fact" if index == 0 else "script-ir"
        (eval_root / f"{stage}-response-raw.txt").write_text(response, encoding="utf-8")
    result["request_count"] = len(requests)
    result["response_count"] = len(responses)
    return result


def _execute_fact_attempt_2(*, source: dict[str, Any], provider: dict[str, Any], eval_root: Path, authorization: dict[str, Any]) -> dict[str, Any]:
    """Run exactly one V2 Fact Extraction dispatch; never invokes ScriptIR."""
    from api.model_registry import get_default_profile
    from core.fact_evidence_authority_v2 import build_fact_request_v2, canonicalize_fact_payload_v2, schema_fingerprint
    from core.source_evidence_index import build_source_evidence_index
    from core.llm import call_llm

    profile = get_default_profile("llm") or {}
    raw_bytes = source["raw_text"].encode("utf-8")
    index = build_source_evidence_index(raw_bytes, source_package_id=authorization["source_package_id"], source_version_id=authorization["source_version_id"], source_raw_hash=source["raw_hash"])
    request = build_fact_request_v2(raw_text=source["raw_text"], source_package_id=authorization["source_package_id"], source_version_id=authorization["source_version_id"], source_raw_hash=source["raw_hash"], source_index=index, provider=provider.get("provider", ""), model=provider.get("model", ""))
    eval_root.mkdir(parents=True, exist_ok=True)
    entry = {"stage": "FACT_EXTRACTION_V2", "attempt_number": 2, "dispatched": True, "request_hash": _request_hash(request), "source_package_id": authorization["source_package_id"], "source_version_id": authorization["source_version_id"], "execution_base": authorization["authorized_execution_base"], "provider": provider.get("provider"), "model": provider.get("model"), "status": "DISPATCHING", "response_received": False, "started_at": datetime.now(timezone.utc).isoformat()}
    ledger = [entry]
    _write(eval_root / "dispatch-ledger-attempt-2.json", {"schema_version": "director_v3_phase_a_dispatch_ledger_v1", "entries": ledger})
    (eval_root / "fact-extraction-v2-request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        response = str(call_llm(json.dumps(request, ensure_ascii=False), system="Return only the JSON object required by the Fact Evidence Authority V2 contract. Use evidence_refs only; never emit evidence text, offsets, authority, status, or fact_id.", model_profile=profile, retries=0, estimated_tokens=7000, max_tokens=12000, audit_extra={"phase": "director_v3_fact_evidence_authority_v2", "attempt": 2, "authorization_id": authorization["authorization_id"]}) or "")
    except Exception as exc:
        entry.update({"status": "TRANSPORT_FAILED", "error": str(exc)[:800], "finished_at": datetime.now(timezone.utc).isoformat()})
        _write(eval_root / "dispatch-ledger-attempt-2.json", {"schema_version": "director_v3_phase_a_dispatch_ledger_v1", "entries": ledger})
        return {"status": "DIRECTOR_V3_FACT_ATTEMPT_2_FAILED", "attempted_provider_calls": 1, "provider_calls": 1, "provider_exposure": "EXPOSED", "dispatch_ledger": ledger, "error": str(exc)[:800], "source_evidence_index": index}
    entry.update({"status": "RESPONSE_RECEIVED" if response else "RESPONSE_EMPTY", "response_received": bool(response), "response_sha256": hashlib.sha256(response.encode("utf-8")).hexdigest(), "response_length": len(response), "finished_at": datetime.now(timezone.utc).isoformat()})
    (eval_root / "fact-extraction-v2-response-raw.txt").write_text(response, encoding="utf-8")
    _write(eval_root / "dispatch-ledger-attempt-2.json", {"schema_version": "director_v3_phase_a_dispatch_ledger_v1", "entries": ledger})
    try:
        parsed = json.loads(response.strip().removeprefix("```json").removesuffix("```").strip())
    except Exception:
        parsed = response
    result = canonicalize_fact_payload_v2(parsed, source_index=index, book_id=900000001, episode=1, source_fingerprint=source["raw_hash"], provenance=source["provenance"])
    result.update({"status": "DIRECTOR_V3_FACT_ATTEMPT_2_CLOSED" if result.get("report", {}).get("status") == "PASS" else "DIRECTOR_V3_FACT_ATTEMPT_2_FAILED", "attempted_provider_calls": 1, "provider_calls": 1, "provider_exposure": "EXPOSED", "dispatch_ledger": ledger, "schema_fingerprint": schema_fingerprint(), "source_evidence_index": index})
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-real", action="store_true", help="guarded provider dispatch; never bypasses gates")
    parser.add_argument("--read-only", action="store_true", help="compute gates without writing tracked evidence")
    parser.add_argument("--authorization-file", default="", help="external runtime authorization JSON; required for --execute-real")
    parser.add_argument("--authorization-preflight", action="store_true", help="validate external authorization and all gates without dispatching")
    parser.add_argument("--fact-attempt-2", action="store_true", help="execute exactly one authorized Fact Evidence Authority V2 call; never runs ScriptIR")
    supplied = argv if argv is not None else sys.argv[1:]
    args = parser.parse_args(argv)
    if any(flag in supplied for flag in ("--force", "--unsafe", "--ignore-authorization", "--no-gate")):
        raise SystemExit("authorization bypass flags are not supported")

    from core.evaluation_upstream_phase_a import (
        PACKAGE_PATH,
        RAW_PATH,
        SOURCE_PACKAGE_ID,
        SOURCE_VERSION_ID,
        build_call_graph,
        load_and_verify_source,
        phase_a_preflight,
    )

    head = _git_head()
    execution_base = _execution_base()
    expected_head = execution_base["commit"]
    remote = _remote_head()
    dirty = _dirty_paths()
    source = load_and_verify_source()
    provider = _provider_snapshot()
    authorization = None
    authorization_error = ""
    requires_runtime_authorization = bool(args.execute_real or args.authorization_preflight or args.fact_attempt_2)
    if requires_runtime_authorization:
        try:
            from core.director_v3_runtime_authorization import load_runtime_authorization
            if not args.authorization_file:
                raise ValueError("authorization_file_required")
            authorization = load_runtime_authorization(args.authorization_file)
        except ValueError as exc:
            authorization_error = str(exc)
    call_graph = build_call_graph(provider_config=provider)
    preflight = phase_a_preflight(source=source, provider_config=provider)
    # The rebaseline evidence is generated at CODE_BASE_COMMIT and then
    # committed as a separate evidence commit.  For the final read-only pass,
    # the immutable execution base is therefore the pushed local/remote HEAD
    # of this clean worktree; no tracked files are changed to make the
    # evidence self-referential.  The normal (write-capable) path remains
    # strict and requires the explicitly recorded code base.
    final_read_only_base = bool(args.read_only and execution_base["status"] == "REBASELINED" and remote.get("status") == "PASS" and remote.get("sha") == head)
    checks = {
        "expected_starting_head": (execution_base["status"] == "REBASELINED" and head == expected_head) or final_read_only_base,
        "remote_head_matches_local": remote.get("status") == "PASS" and remote.get("sha") == head,
        "working_tree_clean": not dirty,
        "source_package_verified": source.get("status") == "PASS",
        "provenance_verified": preflight.get("provenance_verification") == "PASS",
        "provider_resolved": provider.get("status") == "PASS" and bool(provider.get("model")),
        "provider_exposure_not_exposed": source.get("package", {}).get("project_provider_exposure") == "NOT_EXPOSED_CONFIRMED",
        "predicted_calls_within_budget": call_graph["predicted_provider_calls"] <= call_graph["absolute_max_provider_calls"] == 2,
        "no_production_mutation_plan": all(value == 0 for value in preflight["mutation_plan"].values()),
    }
    blocked_reasons = []
    if requires_runtime_authorization:
        if authorization_error:
            blocked_reasons.append("RUNTIME_AUTHORIZATION_INVALID")
        else:
            from core.director_v3_runtime_authorization import authorization_gate, FACT_ATTEMPT_2_SCOPE
            auth_ok, auth_reasons = authorization_gate(
                authorization,
                head=head,
                remote_head=str(remote.get("sha") or ""),
                dirty=dirty,
                source_package_id=SOURCE_PACKAGE_ID,
                source_version_id=SOURCE_VERSION_ID,
                predicted_calls=1 if args.fact_attempt_2 else call_graph["predicted_provider_calls"],
            )
            checks["runtime_authorization"] = auth_ok
            blocked_reasons.extend(auth_reasons)
        # A tracked reconciliation artifact is historical evidence only.  The
        # external authorization is the live authority for a real dispatch.
        if not authorization_error:
            checks["expected_starting_head"] = bool(authorization and authorization.get("authorized_execution_base") == head == remote.get("sha"))
            if not checks["expected_starting_head"] and "RUNTIME_AUTHORIZATION_EXECUTION_BASE_MISMATCH" not in blocked_reasons:
                blocked_reasons.append("RUNTIME_AUTHORIZATION_EXECUTION_BASE_MISMATCH")
            if args.fact_attempt_2 and authorization and authorization.get("scope") != FACT_ATTEMPT_2_SCOPE:
                blocked_reasons.append("RUNTIME_AUTHORIZATION_SCOPE_NOT_FACT_ATTEMPT_2")
    if not checks["expected_starting_head"]:
        blocked_reasons.append("EVALUATION_PHASE_A_EXECUTION_BASE_UNRESOLVED" if execution_base["status"] != "REBASELINED" else "EVALUATION_PHASE_A_HEAD_MISMATCH")
    if not checks["remote_head_matches_local"]:
        blocked_reasons.append("EVALUATION_PHASE_A_REMOTE_HEAD_UNAVAILABLE_OR_MISMATCH")
    if not checks["working_tree_clean"]:
        blocked_reasons.append("WORKTREE_NOT_CLEAN_FOR_REAL_PROVIDER_RUN")
    if not checks["source_package_verified"] or not checks["provenance_verified"]:
        blocked_reasons.append("SOURCE_INTEGRITY_OR_PROVENANCE_FAILED")
    if not checks["provider_resolved"]:
        blocked_reasons.append("PROVIDER_CONFIGURATION_UNRESOLVED")
    if not checks["provider_exposure_not_exposed"]:
        blocked_reasons.append("PROJECT_PROVIDER_EXPOSURE_NOT_FRESH")
    if not checks["predicted_calls_within_budget"]:
        blocked_reasons.append("UPSTREAM_CALL_BUDGET_EXCEEDS_AUTHORIZED_LIMIT")
    execution: dict[str, Any] | None = None
    if args.fact_attempt_2 and not blocked_reasons:
        execution = _execute_fact_attempt_2(source=source, provider=provider, eval_root=EVAL_ROOT, authorization=authorization or {})
        status = execution.get("status", "DIRECTOR_V3_FACT_ATTEMPT_2_FAILED")
        actual_calls = int(execution.get("attempted_provider_calls", 0) or 0)
    elif args.execute_real and not blocked_reasons:
        try:
            execution = _execute_authorized_phase_a(source=source, provider=provider, eval_root=EVAL_ROOT, authorization=authorization or {})
            status = execution.get("status", "DIRECTOR_V3_AUTHORIZED_EVALUATION_UPSTREAM_PHASE_A_FAILED")
            actual_calls = int(execution.get("attempted_provider_calls", execution.get("provider_calls", 0)) or 0)
        except Exception as exc:  # one dispatch failure is terminal; no retry
            status = "DIRECTOR_V3_AUTHORIZED_EVALUATION_UPSTREAM_PHASE_A_FAILED"
            actual_calls = 0
            execution = {"status": status, "provider_calls": 0, "attempted_provider_calls": 0, "provider_exposure": "NOT_EXPOSED_CONFIRMED", "error": str(exc)[:800]}
    elif blocked_reasons:
        status = "DIRECTOR_V3_AUTHORIZED_EVALUATION_UPSTREAM_PHASE_A_BLOCKED"
        actual_calls = 0
    elif args.authorization_preflight and not blocked_reasons:
        status = "DIRECTOR_V3_EVALUATION_PHASE_A_AUTHORIZATION_PREFLIGHT_PASS"
        actual_calls = 0
    else:
        status = "DIRECTOR_V3_EVALUATION_UPSTREAM_PHASE_A_PREFLIGHT_PASS"
        actual_calls = 0

    fact_result = _d((execution or {}).get("fact"))
    if args.fact_attempt_2 and execution:
        fact_result = execution
    fact_report = _d(fact_result.get("report"))
    script_result = _d((execution or {}).get("script"))
    script_report = _d(script_result.get("report"))

    write_evidence = not args.read_only
    if write_evidence:
        EVAL_ROOT.mkdir(parents=True, exist_ok=True)
    _write_if(write_evidence, EVAL_ROOT / "source-manifest-copy.json", source.get("manifest", {}))
    _write_if(write_evidence, EVAL_ROOT / "phase-a-run-manifest.json", {
        "schema_version": "director_v3_evaluation_upstream_phase_a_run_manifest_v1",
        "source_package_id": SOURCE_PACKAGE_ID,
        "source_version_id": SOURCE_VERSION_ID,
        "starting_head": head,
        "remote_head": remote,
        "provider": provider,
        "authorization": {key: value for key, value in (authorization or {}).items() if key not in {"authorization_path"}},
        "predicted_provider_calls": call_graph["predicted_provider_calls"],
        "actual_provider_calls": actual_calls,
        "retries": 0,
        "status": status,
        "blocked_reasons": blocked_reasons,
        "production_db_mutations": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    _write_if(write_evidence, ART / "director-quality-v3-evaluation-upstream-phase-a-callgraph.json", call_graph)
    _write_if(write_evidence, ART / "director-quality-v3-evaluation-upstream-phase-a-contract.json", {
        "schema_version": "director_v3_evaluation_upstream_phase_a_contract_v1",
        "source_package_id": SOURCE_PACKAGE_ID,
        "source_version_id": SOURCE_VERSION_ID,
        "source_authority": "immutable raw source + machine contract + neutral task instructions",
        "provider_calls": {"fact_extraction_max": 1, "script_ir_max": 1, "absolute_max": 2, "retries": 0},
        "isolation": {"evaluation_namespace": str(EVAL_ROOT.relative_to(ROOT)).replace("\\", "/"), "production_db_mutations": 0, "human_fresh_pool_mutations": 0},
        "output_schemas": ["fact_snapshot_v1", "script_ir_v1"],
        "epistemic_rules": ["character claim is not objective truth", "model_observation remains proposed", "confirmed source facts require exact evidence"],
    })
    _write_if(write_evidence, ART / "director-quality-v3-evaluation-upstream-phase-a-preflight.json", {
        "schema_version": "director_v3_evaluation_upstream_phase_a_preflight_v1",
        "status": "BLOCKED" if blocked_reasons else "PASS",
        "status_code": _status_code(blocked=bool(blocked_reasons)),
        "starting_head": head,
        "historical_expected_starting_head": HISTORICAL_EXPECTED_HEAD,
        "expected_starting_head": expected_head,
        "execution_base_status": execution_base["status"],
        "remote_head": remote,
        "working_tree_dirty_count": len(dirty),
        "working_tree_dirty_sample": dirty[:20],
        "source_package": {"package_path": str(PACKAGE_PATH), "raw_path": str(RAW_PATH), "status": source.get("status"), "raw_hash": source.get("raw_hash"), "normalized_hash": source.get("normalized_hash")},
        "provider": provider,
        "checks": checks,
        "blocked_reasons": blocked_reasons,
        "predicted_provider_calls": call_graph["predicted_provider_calls"],
        "provider_calls": actual_calls,
        "real_llm_calls": actual_calls,
        "real_mimo_calls": actual_calls,
    })
    _write_if(write_evidence, ART / "director-quality-v3-evaluation-upstream-phase-a-provider-ledger.json", {"schema_version": "director_v3_evaluation_upstream_phase_a_provider_ledger_v1", "status": status, "fact_extraction_calls": min(actual_calls, 1), "script_ir_calls": max(0, actual_calls - 1), "total_calls": actual_calls, "retries": 0, "entries": _d((execution or {}).get("dispatch_ledger")) if isinstance((execution or {}).get("dispatch_ledger"), dict) else list((execution or {}).get("dispatch_ledger") or [])})
    _write_if(write_evidence, ART / "director-quality-v3-evaluation-upstream-phase-a-fact-validation.json", {"schema_version": "director_v3_evaluation_upstream_phase_a_fact_validation_v1", "status": fact_report.get("status", "NOT_RUN_BLOCKED"), "total_facts": fact_report.get("total_facts", 0), "confirmed": fact_report.get("confirmed", 0), "proposed": fact_report.get("proposed", 0), "conflict": fact_report.get("conflict", 0), "unknown": fact_report.get("unknown", 0), "evidence_verified": fact_report.get("evidence_verified", 0), "evidence_invalid": fact_report.get("evidence_invalid", 0), "claim_objective_promotion_violations": fact_report.get("claim_objective_promotion_violations", 0), "hard_errors": fact_report.get("errors", []), "reason": "provider-free gate blocked before Fact extraction" if not fact_report else ""})
    _write_if(write_evidence, ART / "director-quality-v3-evaluation-upstream-phase-a-script-ir-validation.json", {"schema_version": "director_v3_evaluation_upstream_phase_a_script_ir_validation_v1", "status": script_report.get("status", "NOT_RUN_BLOCKED"), "scene_count": script_report.get("scene_count", 0), "beat_count": script_report.get("beat_count", 0), "dialogue_count": script_report.get("dialogue_count", 0), "invented_hard_events": script_report.get("invented_hard_events", 0), "invented_dialogues": script_report.get("invented_dialogues", 0), "dangling_refs": script_report.get("dangling_refs", []), "director_leakage": script_report.get("director_leakage", 0), "qualification": script_report.get("status", "NOT_RUN"), "reason": "FactSnapshot must pass before ScriptIR call" if not fact_report else ""})
    _write_if(write_evidence, ART / "director-quality-v3-evaluation-upstream-phase-a-grounding-audit.json", {"schema_version": "director_v3_evaluation_upstream_phase_a_grounding_audit_v1", "status": "PASS" if script_report and not script_report.get("invented_hard_events") and not script_report.get("invented_dialogues") else "NOT_RUN_BLOCKED", "source_hash_exact": source.get("status") == "PASS", "evidence_verification": "PASS" if fact_report and not fact_report.get("evidence_invalid") else "NOT_RUN", "invented_events": script_report.get("invented_hard_events", 0), "invented_dialogues": script_report.get("invented_dialogues", 0)})
    _write_if(write_evidence, ART / "director-quality-v3-evaluation-upstream-phase-a-epistemic-audit.json", {"schema_version": "director_v3_evaluation_upstream_phase_a_epistemic_audit_v1", "status": "PASS" if fact_report and not fact_report.get("claim_objective_promotion_violations") and not script_report.get("reported_past_flashback_count") else "NOT_RUN_BLOCKED", "model_observation_auto_confirmed": fact_report.get("claim_objective_promotion_violations", 0), "claim_objective_promotion_violations": fact_report.get("claim_objective_promotion_violations", 0), "reported_past_flashback_auto_created": script_report.get("reported_past_flashback_count", 0), "internal_thought_auto_dialogue": script_report.get("internal_thought_dialogue_count", 0)})
    _write_if(write_evidence, ART / "director-quality-v3-evaluation-upstream-phase-a-human-review.json", {"schema_version": "director_v3_evaluation_upstream_phase_a_human_review_v1", "status": "NOT_RECORDED", "review_required": True, "package_path": str(EVAL_ROOT.relative_to(ROOT)).replace("\\", "/")})
    lineage_state = "SCRIPT_IR_QUALIFIED" if script_report.get("status") == "QUALIFIED" else "FACT_SNAPSHOT_CONFIRMED" if fact_report.get("status") == "PASS" else "SOURCE_ACCEPTED"
    _write_if(write_evidence, ART / "director-quality-v3-evaluation-upstream-phase-a-readiness.json", {"schema_version": "director_v3_evaluation_upstream_phase_a_readiness_v1", "status": status, "lineage_state": lineage_state, "ready_for_treatment_processing": lineage_state == "SCRIPT_IR_QUALIFIED", "treatment_processing_authorized": False, "human_fresh_pool_changed": False, "fresh_pilot_2_ready": False, "fresh_pilot_2_authorized": False, "production_db_mutations": 0, "provider_calls": actual_calls, "blocked_reasons": blocked_reasons})

    report = f"""# Director Quality V3 — Authorized Evaluation Source Upstream Phase A

**Status:** `{status}`

## Baseline Audit

- Historical expected HEAD: `{HISTORICAL_EXPECTED_HEAD}`; resolved execution base: `{expected_head}` (`{execution_base['status']}`); observed `{head}`.
- Remote `{EXPECTED_REMOTE_REF}`: `{remote.get('sha') or remote.get('status')}`.
- Immutable source package: `{SOURCE_PACKAGE_ID}` / `{SOURCE_VERSION_ID}`.
- Raw hash verification: `{'PASS' if source.get('status') == 'PASS' else 'FAIL'}`; provenance: `{'PASS' if checks['provenance_verified'] else 'FAIL'}`.
- Working tree dirty entries: `{len(dirty)}`; no files were reset, stashed, deleted or overwritten.

## Final As-Built Verification

- Provider/model resolution: `{provider.get('provider') or 'unresolved'}` / `{provider.get('model') or 'unresolved'}`; secrets omitted.
- Predicted provider calls: `{call_graph['predicted_provider_calls']}` (absolute max `2`); actual calls: `{actual_calls}`; retries: `0`.
- Evaluation isolation: production DB `0`, Book/Scene/FactSnapshot/ScriptIR production mutations `0`, Human Fresh Pool `0`.
- FactSnapshot: `{fact_report.get('status', 'NOT_RUN_BLOCKED')}`; ScriptIR: `{script_report.get('status', 'NOT_RUN_BLOCKED')}`. The fail-closed boundary prevents ScriptIR dispatch unless FactSnapshot passes.
- Treatment, Blocking, Strategy, Spine, Topology, ShotPlan, Storyboard and media actions: `0`.

## Blocking Reasons

{chr(10).join('- ' + reason for reason in blocked_reasons) or '- none'}

## Decision

`{status}`

Lineage remains `SOURCE_ACCEPTED`; no Treatment processing is authorized. Human review is `NOT_RECORDED`.
"""
    if write_evidence:
        _write(ART / "director-quality-v3-evaluation-upstream-phase-a-report.md", report)
    print(json.dumps({"status": status, "starting_head": head, "execution_base_commit": head if final_read_only_base else expected_head, "remote_head": remote, "provider_calls": actual_calls, "blocked_reasons": blocked_reasons}, ensure_ascii=False, indent=2))
    return 2 if blocked_reasons else 0


if __name__ == "__main__":
    raise SystemExit(main())
