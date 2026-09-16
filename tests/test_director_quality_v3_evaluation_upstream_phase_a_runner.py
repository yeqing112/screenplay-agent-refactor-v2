from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import run_director_quality_v3_evaluation_upstream_phase_a as runner


def test_phase_a_runner_provider_free_preflight_never_dispatches(capsys: pytest.CaptureFixture[str]):
    code = runner.main([])
    output = json.loads(capsys.readouterr().out)
    assert code == 2  # current workspace intentionally remains dirty
    assert output["status"] == "DIRECTOR_V3_AUTHORIZED_EVALUATION_UPSTREAM_PHASE_A_BLOCKED"
    assert output["provider_calls"] == 0
    # Development trees are commonly dirty, while the final immutable
    # verification worktree is intentionally clean.  Both conditions must
    # fail closed without dispatching a provider.
    assert any(reason in output["blocked_reasons"] for reason in {
        "WORKTREE_NOT_CLEAN_FOR_REAL_PROVIDER_RUN",
        "EVALUATION_PHASE_A_HEAD_MISMATCH",
    })


def test_phase_a_runner_rejects_authorization_bypass_flags():
    with pytest.raises(SystemExit):
        runner.main(["--force"])


def test_phase_a_runner_writes_isolated_zero_call_evidence():
    runner.main([])
    preflight = json.loads(Path("artifacts/director-quality-v3-evaluation-upstream-phase-a-preflight.json").read_text(encoding="utf-8"))
    readiness = json.loads(Path("artifacts/director-quality-v3-evaluation-upstream-phase-a-readiness.json").read_text(encoding="utf-8"))
    assert preflight["provider_calls"] == 0
    assert preflight["checks"]["no_production_mutation_plan"] is True
    assert readiness["lineage_state"] == "SOURCE_ACCEPTED"
    assert readiness["ready_for_treatment_processing"] is False
    assert readiness["treatment_processing_authorized"] is False

