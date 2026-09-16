"""Single-source authority semantics for Director Quality V3 stages.

The historical Spine -> Topology re-canary is permanently retired.  This
module keeps that fact separate from the provider-free forensic readiness
record so a readiness report can never be interpreted as an executable
provider authorization.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def historical_spine_topology(pointer: dict[str, Any]) -> dict[str, Any]:
    return _dict(
        _dict(_dict(pointer.get("shot_architecture")).get("generation_architecture_redesign"))
        .get("spine_topology_canary")
    )


def reconcile_historical_recanary_authority(pointer: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with unambiguous retired-recanary semantics.

    ``historical_preflight_ready`` is informational only.  The executable
    signal is always false for this retired cohort, regardless of wiring
    closure.  The legacy ``ready_for_final_recanary`` key is removed so old
    runners cannot mistake historical readiness for current authorization.
    """

    result = deepcopy(pointer)
    shot = result.setdefault("shot_architecture", {})
    redesign = shot.setdefault("generation_architecture_redesign", {})
    canary = redesign.setdefault("spine_topology_canary", {})

    if "ready_for_final_recanary" in canary:
        canary.pop("ready_for_final_recanary", None)
    canary.update(
        {
            "historical_preflight_ready": True,
            "historical_recanary_retired": True,
            "executable_again": False,
            "retired_after_execution": True,
            "no_further_spine_topology_recanary": True,
            "current_recanary_authorized": False,
            "final_recanary_authorized": False,
        }
    )

    # This field previously ambiguously authorized the retired cohort.
    # Preserve its historical meaning explicitly while making the current
    # provider signal fail closed.
    historical = redesign.get("historical_provider_canary_authorized")
    legacy = redesign.pop("provider_canary_authorized", None)
    if historical is None:
        historical = True if legacy is None else bool(legacy)
    redesign["historical_provider_canary_authorized"] = bool(historical)
    redesign["current_provider_canary_authorized"] = False
    redesign["provider_canary_authorized"] = False

    wiring = result.setdefault("final_spine_topology_preflight_wiring", {})
    wiring.pop("ready_for_final_recanary", None)
    wiring["historical_preflight_ready"] = True
    wiring["ready_for_execution"] = False
    wiring["current_recanary_authorized"] = False

    evaluation = result.setdefault("authorized_ai_evaluation_source", {})
    evaluation.setdefault("lineage_state", "SOURCE_ACCEPTED")
    evaluation.setdefault("provider_calls", 0)
    evaluation.setdefault("upstream_processing_authorized", False)
    return result


def validate_current_stage_authority(pointer: dict[str, Any]) -> dict[str, Any]:
    """Validate that retired historical readiness cannot authorize execution."""

    canary = historical_spine_topology(pointer)
    redesign = _dict(_dict(pointer.get("shot_architecture")).get("generation_architecture_redesign"))
    errors: list[str] = []
    if canary.get("historical_recanary_retired") is not True:
        errors.append("HISTORICAL_RECANARY_NOT_RETIRED")
    if canary.get("executable_again") is not False:
        errors.append("RETIRED_RECANARY_EXECUTABLE")
    if canary.get("no_further_spine_topology_recanary") is not True:
        errors.append("FURTHER_RECANARY_NOT_DISABLED")
    if canary.get("current_recanary_authorized") is not False:
        errors.append("CURRENT_RECANARY_AUTHORIZED")
    if "ready_for_final_recanary" in canary:
        errors.append("AMBIGUOUS_READY_FOR_FINAL_RECANARY_KEY")
    if redesign.get("provider_canary_authorized") is not False:
        errors.append("AMBIGUOUS_PROVIDER_CANARY_AUTHORITY")
    if redesign.get("current_provider_canary_authorized") is not False:
        errors.append("CURRENT_PROVIDER_CANARY_AUTHORIZED")
    return {"status": "PASS" if not errors else "FAIL", "errors": errors}


def retired_recanary_provider_callable(pointer: dict[str, Any]) -> bool:
    """Whether the historical retired cohort may reach a provider call."""

    canary = historical_spine_topology(pointer)
    return not (
        canary.get("historical_recanary_retired") is True
        and canary.get("executable_again") is False
        and canary.get("no_further_spine_topology_recanary") is True
        and canary.get("current_recanary_authorized") is False
    )
