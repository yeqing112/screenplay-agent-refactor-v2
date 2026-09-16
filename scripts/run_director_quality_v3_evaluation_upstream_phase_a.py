"""Provider-free preflight for the authorized Evaluation Source Phase A.

This runner deliberately stops at SOURCE_ACCEPTED when repository or source
gates are not satisfied.  ``--execute-real`` is only a guarded dispatch path:
it cannot bypass the expected HEAD, clean-worktree, provenance, exposure or
call-budget gates, and it never retries.  No provider client is imported by
the preflight path.
"""
from __future__ import annotations

import argparse
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


def _execute_authorized_phase_a(*, source: dict[str, Any], provider: dict[str, Any], eval_root: Path) -> dict[str, Any]:
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
    system = "Return only the JSON object required by the supplied evaluation contract. Do not add directing choices, inferred test answers, retries, or commentary."

    def dispatch(request: dict[str, Any]) -> str:
        requests.append(request)
        response = str(call_llm(
            json.dumps(request, ensure_ascii=False),
            system=system,
            model_profile=profile,
            retries=0,
            estimated_tokens=7000,
            max_tokens=12000,
            audit_extra={"phase": "director_v3_evaluation_upstream_phase_a", "stage": request.get("task")},
        ) or "")
        responses.append(response)
        return response

    result = run_with_provider_calls(source=source, provider_config=provider, call_provider=dispatch)
    eval_root.mkdir(parents=True, exist_ok=True)
    for index, request in enumerate(requests):
        stage = "fact" if index == 0 else "script-ir"
        _write(eval_root / f"{stage}-request.json", request)
    for index, response in enumerate(responses):
        stage = "fact" if index == 0 else "script-ir"
        (eval_root / f"{stage}-response-raw.txt").write_text(response, encoding="utf-8")
    result["request_count"] = len(requests)
    result["response_count"] = len(responses)
    result["provider_exposure"] = "EXPOSED" if responses else "NOT_EXPOSED_CONFIRMED"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-real", action="store_true", help="guarded provider dispatch; never bypasses gates")
    parser.add_argument("--read-only", action="store_true", help="compute gates without writing tracked evidence")
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
    call_graph = build_call_graph(provider_config=provider)
    preflight = phase_a_preflight(source=source, provider_config=provider)
    checks = {
        "expected_starting_head": execution_base["status"] == "REBASELINED" and head == expected_head,
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
    if args.execute_real and not blocked_reasons:
        try:
            execution = _execute_authorized_phase_a(source=source, provider=provider, eval_root=EVAL_ROOT)
            status = execution.get("status", "DIRECTOR_V3_AUTHORIZED_EVALUATION_UPSTREAM_PHASE_A_FAILED")
            actual_calls = int(execution.get("provider_calls", 0) or 0)
        except Exception as exc:  # one dispatch failure is terminal; no retry
            status = "DIRECTOR_V3_AUTHORIZED_EVALUATION_UPSTREAM_PHASE_A_FAILED"
            actual_calls = 0
            execution = {"status": status, "provider_calls": 0, "error": str(exc)[:800]}
    elif blocked_reasons:
        status = "DIRECTOR_V3_AUTHORIZED_EVALUATION_UPSTREAM_PHASE_A_BLOCKED"
        actual_calls = 0
    else:
        status = "DIRECTOR_V3_EVALUATION_UPSTREAM_PHASE_A_PREFLIGHT_PASS"
        actual_calls = 0

    fact_result = _d((execution or {}).get("fact"))
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
    _write_if(write_evidence, ART / "director-quality-v3-evaluation-upstream-phase-a-provider-ledger.json", {"schema_version": "director_v3_evaluation_upstream_phase_a_provider_ledger_v1", "status": status, "fact_extraction_calls": min(actual_calls, 1), "script_ir_calls": max(0, actual_calls - 1), "total_calls": actual_calls, "retries": 0, "entries": []})
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
    print(json.dumps({"status": status, "starting_head": head, "remote_head": remote, "provider_calls": actual_calls, "blocked_reasons": blocked_reasons}, ensure_ascii=False, indent=2))
    return 2 if blocked_reasons else 0


if __name__ == "__main__":
    raise SystemExit(main())
