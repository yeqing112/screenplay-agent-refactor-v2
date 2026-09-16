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
EXPECTED_HEAD = "63c93d6e1f78a4777fff9c3e329f5eeb723846eb"
EXPECTED_REMOTE_REF = "origin/codex/unify-formal-workspace"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-real", action="store_true", help="guarded provider dispatch; never bypasses gates")
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
    remote = _remote_head()
    dirty = _dirty_paths()
    source = load_and_verify_source()
    provider = _provider_snapshot()
    call_graph = build_call_graph(provider_config=provider)
    preflight = phase_a_preflight(source=source, provider_config=provider)
    checks = {
        "expected_starting_head": head == EXPECTED_HEAD,
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
        blocked_reasons.append("EVALUATION_PHASE_A_HEAD_MISMATCH")
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
    if args.execute_real or blocked_reasons:
        # Phase A currently cannot dispatch: the starting HEAD/worktree gates
        # are evaluated before any provider import.  Keep this branch explicit
        # so future dispatch code cannot accidentally turn a blocked run into
        # a hidden fallback or retry.
        status = "DIRECTOR_V3_AUTHORIZED_EVALUATION_UPSTREAM_PHASE_A_BLOCKED"
        actual_calls = 0
    else:
        status = "DIRECTOR_V3_EVALUATION_UPSTREAM_PHASE_A_PREFLIGHT_PASS"
        actual_calls = 0

    EVAL_ROOT.mkdir(parents=True, exist_ok=True)
    _write(EVAL_ROOT / "source-manifest-copy.json", source.get("manifest", {}))
    _write(EVAL_ROOT / "phase-a-run-manifest.json", {
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
    _write(ART / "director-quality-v3-evaluation-upstream-phase-a-callgraph.json", call_graph)
    _write(ART / "director-quality-v3-evaluation-upstream-phase-a-contract.json", {
        "schema_version": "director_v3_evaluation_upstream_phase_a_contract_v1",
        "source_package_id": SOURCE_PACKAGE_ID,
        "source_version_id": SOURCE_VERSION_ID,
        "source_authority": "immutable raw source + machine contract + neutral task instructions",
        "provider_calls": {"fact_extraction_max": 1, "script_ir_max": 1, "absolute_max": 2, "retries": 0},
        "isolation": {"evaluation_namespace": str(EVAL_ROOT.relative_to(ROOT)).replace("\\", "/"), "production_db_mutations": 0, "human_fresh_pool_mutations": 0},
        "output_schemas": ["fact_snapshot_v1", "script_ir_v1"],
        "epistemic_rules": ["character claim is not objective truth", "model_observation remains proposed", "confirmed source facts require exact evidence"],
    })
    _write(ART / "director-quality-v3-evaluation-upstream-phase-a-preflight.json", {
        "schema_version": "director_v3_evaluation_upstream_phase_a_preflight_v1",
        "status": "BLOCKED" if blocked_reasons else "PASS",
        "status_code": _status_code(blocked=bool(blocked_reasons)),
        "starting_head": head,
        "expected_starting_head": EXPECTED_HEAD,
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
    _write(ART / "director-quality-v3-evaluation-upstream-phase-a-provider-ledger.json", {"schema_version": "director_v3_evaluation_upstream_phase_a_provider_ledger_v1", "status": status, "fact_extraction_calls": 0, "script_ir_calls": 0, "total_calls": actual_calls, "retries": 0, "entries": []})
    _write(ART / "director-quality-v3-evaluation-upstream-phase-a-fact-validation.json", {"schema_version": "director_v3_evaluation_upstream_phase_a_fact_validation_v1", "status": "NOT_RUN_BLOCKED", "total_facts": 0, "confirmed": 0, "proposed": 0, "conflict": 0, "unknown": 0, "evidence_verified": 0, "evidence_invalid": 0, "claim_objective_promotion_violations": 0, "hard_errors": [], "reason": "provider-free gate blocked before Fact extraction"})
    _write(ART / "director-quality-v3-evaluation-upstream-phase-a-script-ir-validation.json", {"schema_version": "director_v3_evaluation_upstream_phase_a_script_ir_validation_v1", "status": "NOT_RUN_BLOCKED", "scene_count": 0, "beat_count": 0, "dialogue_count": 0, "invented_hard_events": 0, "invented_dialogues": 0, "dangling_refs": 0, "director_leakage": 0, "qualification": "NOT_RUN", "reason": "FactSnapshot must pass before ScriptIR call"})
    _write(ART / "director-quality-v3-evaluation-upstream-phase-a-grounding-audit.json", {"schema_version": "director_v3_evaluation_upstream_phase_a_grounding_audit_v1", "status": "NOT_RUN_BLOCKED", "source_hash_exact": source.get("status") == "PASS", "evidence_verification": "NOT_RUN", "invented_events": 0, "invented_dialogues": 0})
    _write(ART / "director-quality-v3-evaluation-upstream-phase-a-epistemic-audit.json", {"schema_version": "director_v3_evaluation_upstream_phase_a_epistemic_audit_v1", "status": "NOT_RUN_BLOCKED", "model_observation_auto_confirmed": 0, "claim_objective_promotion_violations": 0, "reported_past_flashback_auto_created": 0, "internal_thought_auto_dialogue": 0})
    _write(ART / "director-quality-v3-evaluation-upstream-phase-a-human-review.json", {"schema_version": "director_v3_evaluation_upstream_phase_a_human_review_v1", "status": "NOT_RECORDED", "review_required": True, "package_path": str(EVAL_ROOT.relative_to(ROOT)).replace("\\", "/")})
    _write(ART / "director-quality-v3-evaluation-upstream-phase-a-readiness.json", {"schema_version": "director_v3_evaluation_upstream_phase_a_readiness_v1", "status": status, "lineage_state": "SOURCE_ACCEPTED", "ready_for_treatment_processing": False, "treatment_processing_authorized": False, "human_fresh_pool_changed": False, "fresh_pilot_2_ready": False, "fresh_pilot_2_authorized": False, "production_db_mutations": 0, "provider_calls": actual_calls, "blocked_reasons": blocked_reasons})

    report = f"""# Director Quality V3 — Authorized Evaluation Source Upstream Phase A

**Status:** `{status}`

## Baseline Audit

- Expected starting HEAD: `{EXPECTED_HEAD}`; observed `{head}`.
- Remote `{EXPECTED_REMOTE_REF}`: `{remote.get('sha') or remote.get('status')}`.
- Immutable source package: `{SOURCE_PACKAGE_ID}` / `{SOURCE_VERSION_ID}`.
- Raw hash verification: `{'PASS' if source.get('status') == 'PASS' else 'FAIL'}`; provenance: `{'PASS' if checks['provenance_verified'] else 'FAIL'}`.
- Working tree dirty entries: `{len(dirty)}`; no files were reset, stashed, deleted or overwritten.

## Final As-Built Verification

- Provider/model resolution: `{provider.get('provider') or 'unresolved'}` / `{provider.get('model') or 'unresolved'}`; secrets omitted.
- Predicted provider calls: `{call_graph['predicted_provider_calls']}` (absolute max `2`); actual calls: `{actual_calls}`; retries: `0`.
- Evaluation isolation: production DB `0`, Book/Scene/FactSnapshot/ScriptIR production mutations `0`, Human Fresh Pool `0`.
- FactSnapshot: `NOT_RUN_BLOCKED`; ScriptIR: `NOT_RUN_BLOCKED`. The fail-closed boundary prevents ScriptIR dispatch unless FactSnapshot passes.
- Treatment, Blocking, Strategy, Spine, Topology, ShotPlan, Storyboard and media actions: `0`.

## Blocking Reasons

{chr(10).join('- ' + reason for reason in blocked_reasons) or '- none'}

## Decision

`{status}`

Lineage remains `SOURCE_ACCEPTED`; no Treatment processing is authorized. Human review is `NOT_RECORDED`.
"""
    _write(ART / "director-quality-v3-evaluation-upstream-phase-a-report.md", report)
    print(json.dumps({"status": status, "starting_head": head, "remote_head": remote, "provider_calls": actual_calls, "blocked_reasons": blocked_reasons}, ensure_ascii=False, indent=2))
    return 2 if blocked_reasons else 0


if __name__ == "__main__":
    raise SystemExit(main())
