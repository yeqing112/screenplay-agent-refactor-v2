import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts" / "e2e-production-pilot"


@pytest.fixture(scope="module")
def phase_c_pilot_trace():
    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    result = subprocess.run(
        [sys.executable, "scripts/run_phase_b_director_blocking_pilot.py"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    return json.loads((ART / "episode_01_phase_c_trace.json").read_text(encoding="utf-8"))


def test_real_confirm_rejects_continuity_invalid_proposal_without_production_write(phase_c_pilot_trace):
    evidence = phase_c_pilot_trace["continuity_failed_candidate"]
    assert evidence["status_code"] == 409
    assert evidence["code"] == "SHOT_PLAN_PHASE_C_CONTRACT_INVALID"
    assert any(error["code"] == "SHOT_AXIS_CONTINUITY_INVALID" for error in evidence["errors"])
    assert evidence["authority_count_unchanged"] is True
    assert evidence["pointer_unchanged"] is True
    assert evidence["approved_count_unchanged"] is True
    assert phase_c_pilot_trace["authority_flow"]["continuity_confirm_zero_write"] is True


def test_real_resolver_stales_semantically_invalid_canonical_row_and_preserves_pointer(phase_c_pilot_trace):
    evidence = phase_c_pilot_trace["resolver_continuity_tamper"]
    assert evidence["status_code"] == 409
    assert evidence["code"] == "SHOT_PLAN_PHASE_C_INVALID"
    assert any(error["code"] == "SHOT_AXIS_CONTINUITY_INVALID" for error in evidence["errors"])
    assert evidence["row_stale_status"] == "STALE"
    assert evidence["authority_stale_status"] == "STALE"
    assert evidence["pointer_preserved"] is True
    assert phase_c_pilot_trace["authority_flow"]["resolver_continuity_stale"] is True

