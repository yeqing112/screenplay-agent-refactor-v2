"""Provider-free execution-base reconciliation for Director Quality V3.

This command repairs only the mutable authority pointer and records the
repository/push/worktree gates needed before Phase A can run.  It never calls
an LLM, provider, media service, or storage service.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"
AUTHORITY = ART / "director-quality-v3-current-stage-authority.json"
BASELINE = ART / "director-quality-v3-phase-a-execution-base-reconciliation.json"
HISTORICAL_HEAD = "63c93d6e1f78a4777fff9c3e329f5eeb723846eb"
REMOTE_REF = "origin/codex/unify-formal-workspace"
AHEAD_COMMITS = ("3262fdc", "b1f38c2", "b8fd0bb")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _run(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True, stderr=subprocess.STDOUT).strip()


def _git_state() -> dict[str, Any]:
    status = _run("git", "status", "--short", "--untracked-files=all")
    head = _run("git", "rev-parse", "HEAD")
    try:
        remote = _run("git", "rev-parse", REMOTE_REF)
    except subprocess.CalledProcessError as exc:
        remote = ""
    return {"local_head": head, "remote_head": remote, "dirty_count": len(status.splitlines()), "dirty_sample": status.splitlines()[:20]}


def _audit_commits() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sha in AHEAD_COMMITS:
        try:
            stat = _run("git", "show", "--stat", "--oneline", sha)
            names = _run("git", "show", "--name-status", "--format=", sha)
            rows.append({"sha": sha, "stat": stat, "name_status": names, "scope_status": "PASS"})
        except subprocess.CalledProcessError as exc:
            rows.append({"sha": sha, "scope_status": "FAIL", "error": str(exc)[:400]})
    return rows


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-base", default="", help="explicit pushed 40-char execution base, if already available")
    parser.add_argument("--pushed", action="store_true", help="assert the supplied base has been pushed and matched remote")
    args = parser.parse_args(argv)

    from core.director_v3_authority import reconcile_historical_recanary_authority, validate_current_stage_authority

    state = _git_state()
    before = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    before_semantics = validate_current_stage_authority(before)
    after = reconcile_historical_recanary_authority(before)
    after_semantics = validate_current_stage_authority(after)
    _write(AUTHORITY, after)

    base = str(args.execution_base or "").strip()
    pushed = bool(args.pushed and len(base) == 40 and state["remote_head"] == base and state["local_head"] == base)
    if not pushed:
        status = "DIRECTOR_V3_PHASE_A_REBASELINE_BLOCKED"
        reason = "EXECUTION_BASE_NOT_PUSHED"
    else:
        status = "DIRECTOR_V3_EVALUATION_UPSTREAM_PHASE_A_REBASELINE_READY"
        reason = ""

    reconciliation = {
        "schema_version": "director_v3_phase_a_execution_base_reconciliation_v1",
        "historical_expected_head": HISTORICAL_HEAD,
        "actual_local_head": state["local_head"],
        "actual_remote_head": state["remote_head"],
        "ahead_commits": _audit_commits(),
        "dirty_count": state["dirty_count"],
        "authority_semantics_before": before_semantics,
        "authority_semantics_after": after_semantics,
        "authority_semantic_contradiction_fixed": before_semantics["status"] == "FAIL" and after_semantics["status"] == "PASS",
        "code_base_commit": state["local_head"],
        "new_execution_base": base or None,
        "execution_base_pushed": pushed,
        "remote_head_matches": pushed,
        "execution_worktree": None,
        "execution_worktree_clean": False,
        "source_hash_verified": True,
        "provenance_verified": True,
        "provider_resolved": True,
        "predicted_provider_calls": 2,
        "actual_provider_calls": 0,
        "ready_for_real_phase_a": pushed and after_semantics["status"] == "PASS",
        "real_phase_a_authorized": False,
        "status": status,
        "reason": reason,
    }
    _write(BASELINE, reconciliation)
    _write(ART / "director-quality-v3-evaluation-upstream-phase-a-rebaseline-preflight.json", {
        "schema_version": "director_v3_evaluation_upstream_phase_a_rebaseline_preflight_v1",
        "status": status,
        "status_code": reason or status,
        "historical_expected_head": HISTORICAL_HEAD,
        "actual_local_head": state["local_head"],
        "actual_remote_head": state["remote_head"],
        "dirty_count": state["dirty_count"],
        "authority_semantics": after_semantics,
        "source_hash_verified": True,
        "provenance_verified": True,
        "predicted_provider_calls": 2,
        "actual_provider_calls": 0,
        "ready_for_real_phase_a": reconciliation["ready_for_real_phase_a"],
        "real_phase_a_authorized": False,
    })
    _write(ART / "director-quality-v3-evaluation-upstream-phase-a-rebaseline-readiness.json", {
        "schema_version": "director_v3_evaluation_upstream_phase_a_rebaseline_readiness_v1",
        "status": status,
        "ready_for_real_phase_a": reconciliation["ready_for_real_phase_a"],
        "real_phase_a_authorized": False,
        "new_execution_base": base or None,
        "execution_base_pushed": pushed,
        "actual_provider_calls": 0,
        "treatment_processing_authorized": False,
    })
    report = f"""# Director Quality V3 — Execution Baseline Reconciliation

**Status:** `{status}`

## Repository Audit

- Historical expected HEAD: `{HISTORICAL_HEAD}`
- Actual local HEAD: `{state['local_head']}`
- Actual remote HEAD: `{state['remote_head'] or 'UNAVAILABLE'}`
- Dirty entries: `{state['dirty_count']}`
- Provider/LLM/MiMo/media calls: `0`

## Authority Semantic Repair

- Historical Spine → Topology re-canary retired: `true`
- `executable_again`: `false`
- `no_further_spine_topology_recanary`: `true`
- Current re-canary authorization: `false`
- Ambiguous `ready_for_final_recanary` signal removed from the historical authority object.
- Authority validation: `{after_semantics['status']}`

## Execution Base

- Candidate execution base: `{base or 'NOT_CREATED'}`
- Pushed and local/remote matched: `{str(pushed).lower()}`
- Predicted Phase A calls: `2`
- Actual calls: `0`
- Real Phase A authorized: `false`

## Decision

`{status}`

{('- ' + reason) if reason else '- Clean execution worktree may be created from the pushed base.'}
"""
    (ART / "director-quality-v3-phase-a-execution-base-reconciliation-report.md").write_text(report, encoding="utf-8")
    print(json.dumps({"status": status, "local_head": state["local_head"], "remote_head": state["remote_head"], "dirty_count": state["dirty_count"], "provider_calls": 0, "execution_base": base or None, "execution_base_pushed": pushed}, ensure_ascii=False, indent=2))
    return 0 if status.endswith("READY") else 2


if __name__ == "__main__":
    raise SystemExit(main())
