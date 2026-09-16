import json
from pathlib import Path

from core.director_v3_authority import (
    reconcile_historical_recanary_authority,
    retired_recanary_provider_callable,
    validate_current_stage_authority,
)


def _pointer():
    return {
        "shot_architecture": {
            "generation_architecture_redesign": {
                "provider_canary_authorized": True,
                "spine_topology_canary": {
                    "ready_for_final_recanary": True,
                    "historical_recanary_retired": True,
                    "executable_again": False,
                    "no_further_spine_topology_recanary": True,
                },
            }
        },
        "final_spine_topology_preflight_wiring": {
            "ready_for_final_recanary": True,
        },
    }


def test_reconciliation_removes_ambiguous_executable_signals():
    result = reconcile_historical_recanary_authority(_pointer())
    canary = result["shot_architecture"]["generation_architecture_redesign"]["spine_topology_canary"]
    redesign = result["shot_architecture"]["generation_architecture_redesign"]
    assert "ready_for_final_recanary" not in canary
    assert canary["historical_preflight_ready"] is True
    assert canary["current_recanary_authorized"] is False
    assert redesign["provider_canary_authorized"] is False
    assert redesign["historical_provider_canary_authorized"] is True
    assert redesign["current_provider_canary_authorized"] is False
    assert "ready_for_final_recanary" not in result["final_spine_topology_preflight_wiring"]
    assert validate_current_stage_authority(result)["status"] == "PASS"


def test_wiring_closure_does_not_authorize_retired_recanary():
    pointer = reconcile_historical_recanary_authority(_pointer())
    pointer["final_spine_topology_preflight_wiring"]["status"] = "CLOSED"
    assert retired_recanary_provider_callable(pointer) is False


def test_contradictory_authority_is_rejected_before_reconciliation():
    pointer = _pointer()
    result = validate_current_stage_authority(pointer)
    assert result["status"] == "FAIL"
    assert "AMBIGUOUS_READY_FOR_FINAL_RECANARY_KEY" in result["errors"]
    assert "AMBIGUOUS_PROVIDER_CANARY_AUTHORITY" in result["errors"]


def test_real_pointer_is_semantically_reconciled():
    path = Path("artifacts/director-quality-v3-current-stage-authority.json")
    pointer = json.loads(path.read_text(encoding="utf-8"))
    reconciled = reconcile_historical_recanary_authority(pointer)
    assert validate_current_stage_authority(reconciled)["status"] == "PASS"


def test_retired_spine_topology_recanary_not_executable():
    assert retired_recanary_provider_callable(reconcile_historical_recanary_authority(_pointer())) is False


def test_no_further_spine_topology_recanary_blocks_provider():
    pointer = reconcile_historical_recanary_authority(_pointer())
    pointer["shot_architecture"]["generation_architecture_redesign"]["spine_topology_canary"]["no_further_spine_topology_recanary"] = False
    assert retired_recanary_provider_callable(pointer) is True


def test_wiring_closed_does_not_authorize_recanary():
    pointer = reconcile_historical_recanary_authority(_pointer())
    pointer["final_spine_topology_preflight_wiring"]["status"] = "CLOSED"
    assert pointer["shot_architecture"]["generation_architecture_redesign"]["spine_topology_canary"]["current_recanary_authorized"] is False


def test_final_recanary_authorization_false_blocks_provider():
    pointer = reconcile_historical_recanary_authority(_pointer())
    canary = pointer["shot_architecture"]["generation_architecture_redesign"]["spine_topology_canary"]
    assert canary["final_recanary_authorized"] is False


def test_current_stage_authority_has_no_recanary_semantic_conflict():
    pointer = reconcile_historical_recanary_authority(_pointer())
    assert validate_current_stage_authority(pointer) == {"status": "PASS", "errors": []}
