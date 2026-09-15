import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"


def test_provider_free_validator_semantics_replay_and_pointer():
    proc = subprocess.run(
        [sys.executable, "scripts/run_director_quality_v3_shot_architecture_validator_semantics.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "DIRECTOR_V3_SHOT_ARCHITECTURE_VALIDATOR_SEMANTICS_CLOSED" in proc.stdout
    replay = json.loads((ARTIFACTS / "director-quality-v3-shot-architecture-validator-semantics-replay.json").read_text(encoding="utf-8"))
    assert replay["new_provider_calls"] == 0
    assert replay["real_llm_calls"] == 0
    assert replay["real_mimo_calls"] == 0
    assert replay["aggregate"]["scene_signal_distribution"] == {"RAW_ARCHITECTURE_PROMISING_BUT_NEEDS_CONTRACT": 3}
    assert replay["aggregate"]["hard_blocking_scene_count"] == 0
    assert replay["aggregate"]["definite_composite_total"] == 4
    assert replay["aggregate"]["continuous_framing_total"] == 3
    assert replay["aggregate"]["review_required_total"] == 1
    pointer = json.loads((ARTIFACTS / "director-quality-v3-current-stage-authority.json").read_text(encoding="utf-8"))
    assert pointer["shot_architecture"]["original_canary"]["experiment_validity"] == "INVALID"
    assert pointer["shot_architecture"]["original_canary"]["forensic_adjudication"] == "CLOSED"
    assert pointer["shot_architecture"]["contract_v2"]["status"] == "CLOSED"
    assert pointer["shot_architecture"]["validator_semantics"]["status"] == "CLOSED"
    assert pointer["shot_architecture"]["ready_for_final_recanary"] is False
    assert pointer["shot_architecture"]["production_shotplan"] == "HOLD"


def test_new_semantics_contracts_are_explicit_and_legacy_forensic_artifacts_remain():
    reaction = json.loads((ARTIFACTS / "director-quality-v3-shot-architecture-reaction-semantics-contract.json").read_text(encoding="utf-8"))
    assert reaction["stimulus_ref"]["required_for_new_provider_contract"] is True
    assert reaction["stimulus_ref"]["must_precede_reaction"] is True
    atomicity = json.loads((ARTIFACTS / "director-quality-v3-shot-architecture-atomicity-semantics-contract.json").read_text(encoding="utf-8"))
    assert set(atomicity["classifications"]) == {"ATOMIC_SHOT_PASS", "CONTINUOUS_FRAMING_EVOLUTION", "DEFINITE_COMPOSITE_COVERAGE_BUNDLE", "ATOMICITY_REVIEW_REQUIRED"}
    assert (ARTIFACTS / "director-quality-v3-shot-architecture-forensic-replay.json").exists()
