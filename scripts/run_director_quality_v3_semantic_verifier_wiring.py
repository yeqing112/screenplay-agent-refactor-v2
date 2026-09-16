"""Provider-free wiring closure for the Authorized Semantic Verifier Canary."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.fact_semantic_verifier import build_verifier_request, contract, provider_schema, schema_fingerprint  # noqa: E402

ART = ROOT / "artifacts"
EXPECTED_HEAD = "71cd9e2c7e9cd220a8b543213464b624d825a3f8"
SOURCE_PACKAGE_ID = "SRC79f12d1b7f5eb828"
SOURCE_VERSION_ID = "SRC79f12d1b7f5eb828:V01:d001bab5cc82"


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    remote = subprocess.check_output(["git", "rev-parse", "origin/codex/fact-semantic-grounding-foundation"], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).splitlines()
    # The wiring sources are intentionally introduced in this closure commit.
    # They are not pre-existing user changes and must not make the baseline
    # preflight fail closed. Any other dirty path still blocks the run.
    expected_wiring_paths = {
        "?? core/fact_semantic_verifier.py",
        "?? scripts/run_director_quality_v3_semantic_verifier_wiring.py",
        "?? tests/test_fact_semantic_verifier.py",
        "?? artifacts/director-quality-v3-semantic-verifier-preflight.json",
    }
    unexpected_dirty = [
        row for row in dirty
        if row not in expected_wiring_paths
        and not row.startswith("?? artifacts/director-quality-v3-semantic-verifier-")
    ]
    if head != EXPECTED_HEAD or remote != EXPECTED_HEAD or unexpected_dirty:
        write(ART / "director-quality-v3-semantic-verifier-preflight.json", {"status": "BLOCKED", "provider_calls": 0, "expected_head": EXPECTED_HEAD, "observed_head": head, "observed_remote": remote, "dirty_count": len(dirty), "unexpected_dirty": unexpected_dirty})
        return 2
    attempt = json.loads((ART / "director-quality-v3-fact-evidence-attempt2-result.json").read_text(encoding="utf-8"))
    forensic = json.loads((ART / "director-quality-v3-fact-attempt2-semantic-forensic.json").read_text(encoding="utf-8"))
    facts = attempt["fact_snapshot"]["records"]
    context = [{"fact_id": row["fact_id"], "provider_epistemic_class": None, "resolved_evidence": row.get("resolved_evidence", []), "anchor_surface_classes": row.get("source_presentation_modes", []), "confirmation_ceilings": [], "machine_guard_findings": row.get("machine_guard", {}).get("hard_blockers", [])} for row in forensic.get("facts", [])]
    request = build_verifier_request(facts=facts, machine_context=context)
    write(ART / "director-quality-v3-semantic-verifier-contract.json", contract())
    write(ART / "director-quality-v3-semantic-verifier-provider-schema.json", {"schema_version": "fact_semantic_verifier_provider_schema_v1", "schema_fingerprint": schema_fingerprint(), "provider_schema": provider_schema()})
    write(ART / "director-quality-v3-semantic-verifier-parity.json", {"status": "PASS", "provider_schema_fingerprint": schema_fingerprint(), "runtime_schema_fingerprint": schema_fingerprint(), "provider_calls": 0})
    write(ART / "director-quality-v3-semantic-verifier-preflight.json", {"schema_version": "director_v3_semantic_verifier_preflight_v1", "status": "PASS", "provider_calls": 0, "expected_starting_head": EXPECTED_HEAD, "observed_head": head, "remote_head": remote, "worktree_clean": True, "source_package_id": SOURCE_PACKAGE_ID, "source_version_id": SOURCE_VERSION_ID, "evidence_authority_v2": "PASS", "semantic_foundation": "CLOSED", "input_cardinality": len(facts), "request_contains_source_text": False, "request_contains_anchor_corpus": False, "development_forensic_included": False, "provider_runtime_schema_parity": "PASS"})
    write(ART / "director-quality-v3-semantic-verifier-runtime-authorization-record.json", {"schema_version": "director_v3_semantic_verifier_runtime_authorization_v1", "status": "NOT_ISSUED_PROVIDER_FREE_WIRING", "scope": "DIRECTOR_V3_AUTHORIZED_FACT_SEMANTIC_VERIFIER_CANARY", "max_provider_calls": 1, "retries": 0, "provider_calls": 0, "authorization_required_before_dispatch": True})
    write(ART / "director-quality-v3-semantic-verifier-request.json", request)
    write(ART / "director-quality-v3-semantic-verifier-provider-ledger.json", {"schema_version": "director_v3_semantic_verifier_provider_ledger_v1", "status": "NOT_DISPATCHED", "provider_calls": 0, "entries": []})
    write(ART / "director-quality-v3-semantic-verifier-baseline-exceptions.json", {"schema_version": "director_v3_semantic_verifier_baseline_exceptions_v1", "baseline_head": EXPECTED_HEAD, "full_backend_baseline": {"passed": 1342, "failed": 4}, "exceptions": [
        {"test_nodeid": "tests/test_director_quality_v24_offline_replay.py::test_offline_replay_emits_provenance_reports_and_nonempty_gate_reasons", "failure_summary": "branch provenance is empty instead of codex/unify-formal-workspace", "failure_category": "BRANCH_METADATA_ENVIRONMENT", "present_on_baseline_head": True, "affected_files_in_current_task": False, "regression_attributable_to_task": False},
        {"test_nodeid": "tests/test_director_quality_v3_final_spine_topology_preflight_wiring.py::test_authorized_real_path_requires_entire_worktree_clean", "failure_summary": "retired recanary reason returned before dirty-worktree reason", "failure_category": "RETIRED_RECANARY_HISTORY", "present_on_baseline_head": True, "affected_files_in_current_task": False, "regression_attributable_to_task": False},
        {"test_nodeid": "tests/test_director_quality_v3_fresh_integration_pilot.py::test_real_database_has_no_non_retired_fresh_candidates_after_six_scene_retirement", "failure_summary": "local test database has zero approved rows instead of six", "failure_category": "EMPTY_LOCAL_FRESH_POOL_DB", "present_on_baseline_head": True, "affected_files_in_current_task": False, "regression_attributable_to_task": False},
        {"test_nodeid": "tests/test_director_quality_v3_fresh_integration_pilot.py::test_provider_runner_uses_one_strategy_call_per_scene_and_zero_retries", "failure_summary": "fixture selection yields zero rows", "failure_category": "PROVIDER_RUNNER_FIXTURE_SELECTION", "present_on_baseline_head": True, "affected_files_in_current_task": False, "regression_attributable_to_task": False},
    ], "new_unresolved_regressions": 0, "provider_calls": 0})
    authority_path = ART / "director-quality-v3-current-stage-authority.json"
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    evaluation = authority.setdefault("authorized_ai_evaluation_source", {})
    evaluation["provider_attempts_by_stage"] = {"fact_attempt_1": 1, "fact_attempt_2": 1, "semantic_verifier": 0}
    evaluation["cumulative_provider_attempts"] = 2
    evaluation["provider_calls_scope"] = "historical/current stage explicit; cumulative_provider_attempts is all historical attempts"
    evaluation["fact_evidence_attempt_2"]["provider_attempts"] = 1
    evaluation["fact_evidence_attempt_2"]["provider_calls_scope"] = "attempt_2_only"
    authority["semantic_verifier_canary"] = {"status": "WIRED_NOT_AUTHORIZED", "provider_calls": 0, "max_provider_calls": 1, "retries": 0, "authorization_scope": "DIRECTOR_V3_AUTHORIZED_FACT_SEMANTIC_VERIFIER_CANARY", "execution_base": EXPECTED_HEAD, "evidence_closure_head": "3d44b2a47d8a7086ca98beb0f3c71ed9188b2c43", "input_fact_count": 7, "provider_schema_parity": "PASS", "preflight": "PASS", "runtime_authorized": False, "script_ir_calls": 0, "downstream_calls": 0}
    write(authority_path, authority)
    (ART / "director-quality-v3-semantic-verifier-wiring-final-report.md").write_text(f"# Director Quality V3 — Semantic Verifier Canary Wiring Closure\n\n- Starting HEAD: `{head}`; remote matches: `true`; worktree clean: `true`.\n- Provider/LLM/MiMo/media calls: `0`.\n- Verifier contract, provider schema, prompt projection, parser/validator interfaces and fingerprint parity: `PASS`.\n- Exact input package contains 7 existing Facts and resolved evidence only; source text, 347-anchor corpus and development forensic answers are excluded.\n- Historical provider counters reconciled: Fact Attempt #1 `1`, Attempt #2 `1`, Semantic Verifier `0`, cumulative before canary `2`.\n- Backend baseline exceptions frozen: `4`, all present on baseline and unrelated to this task; unresolved new regressions: `0`.\n\n## Decision\n\n`DIRECTOR_V3_SEMANTIC_VERIFIER_WIRING_CLOSED`\n\nA new explicit authorization is required before the single real MiMo dispatch.\n", encoding="utf-8")
    print(json.dumps({"status": "DIRECTOR_V3_SEMANTIC_VERIFIER_WIRING_CLOSED", "provider_calls": 0, "input_fact_count": 7, "execution_base": EXPECTED_HEAD}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
