"""Traceability contract between a scene strategy and a Draft ShotPlan."""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from core.director_scene_strategy import parse_scene_directing_strategy, SceneStrategyError


STRATEGY_TO_SHOT_SCHEMA_VERSION = "director_strategy_to_shot_contract_v1"
SUPPORTED_STRATEGY_SCHEMA_VERSIONS = ("director_scene_strategy_v1", "director_scene_strategy_v2", "director_scene_strategy_v3")
SHOT_PLAN_STATES = ("DRAFT", "QA_FAILED", "REDESIGN_REQUIRED", "READY_FOR_APPROVAL", "APPROVED")
REQUIRED_TRACE_FIELDS = ("beat_id", "strategy_phase_id", "dramatic_function", "audience_information_state", "emotion_phase", "power_state", "edit_function", "camera_motivation", "performance_function")


class StrategyShotContractError(ValueError):
    code = "STRATEGY_TO_SHOT_CONTRACT_INVALID"


def _text(value: Any) -> str: return str(value or "").strip()
def _dict(value: Any) -> dict[str, Any]: return value if isinstance(value, dict) else {}
def _list(value: Any) -> list[Any]: return value if isinstance(value, list) else []
def _canonical(value: Any) -> str: return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
def contract_fingerprint(value: Any) -> str: return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def build_strategy_to_shot_contract(*, strategy: dict[str, Any], draft_shot_plan: dict[str, Any], immutable_facts: dict[str, Any] | None = None) -> dict[str, Any]:
    shots = [row for row in _list(_dict(draft_shot_plan).get("shots")) if isinstance(row, dict)]
    phase_by_beat = {}
    for phase in (_list(strategy.get("scene_phases")) or _list(strategy.get("audience_experience"))):
        if isinstance(phase, dict):
            for beat_id in _list(phase.get("beat_ids")):
                phase_by_beat[_text(beat_id)] = _text(phase.get("phase_id"))
    traces = []
    for index, shot in enumerate(shots, 1):
        beat_id = _text(shot.get("beat_id"))
        traces.append({"plan_shot_id": _text(shot.get("plan_shot_id") or f"S{index:02d}"), "beat_id": beat_id, "strategy_phase_id": _text(shot.get("strategy_phase_id") or phase_by_beat.get(beat_id)), "dramatic_function": _text(shot.get("dramatic_function")), "audience_information_state": _text(shot.get("audience_information_state")), "emotion_phase": _text(shot.get("emotion_phase")), "power_state": _text(shot.get("power_state")), "edit_function": _text(shot.get("edit_function")), "camera_motivation": _text(shot.get("camera_motivation")), "performance_function": _text(shot.get("performance_function"))})
    payload = {"schema_version": STRATEGY_TO_SHOT_SCHEMA_VERSION, "strategy_schema_version": _text(strategy.get("schema_version")), "strategy_schema_supported": _text(strategy.get("schema_version")) in SUPPORTED_STRATEGY_SCHEMA_VERSIONS, "strategy_fingerprint": _text(strategy.get("strategy_fingerprint")), "creative_core_fingerprint": _text(strategy.get("creative_core_fingerprint")), "draft_shot_plan_fingerprint": contract_fingerprint(draft_shot_plan), "state": "DRAFT", "topology_mutable": True, "required_trace_fields": list(REQUIRED_TRACE_FIELDS), "shot_traces": traces, "immutable_facts_fingerprint": contract_fingerprint(immutable_facts or {})}
    payload["contract_fingerprint"] = contract_fingerprint(payload)
    return payload


def validate_strategy_traceability(*, contract: dict[str, Any], strategy: dict[str, Any] | None = None, draft_shot_plan: dict[str, Any] | None = None) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    traces = _list(_dict(contract).get("shot_traces"))
    seen: set[str] = set()
    for index, trace in enumerate(traces):
        if not isinstance(trace, dict):
            errors.append({"code": "TRACE_ITEM_INVALID", "shot_index": index}); continue
        sid = _text(trace.get("plan_shot_id"))
        if not sid or sid in seen:
            errors.append({"code": "TRACE_SHOT_ID_INVALID", "shot_index": index, "shot_id": sid})
        seen.add(sid)
        for field in REQUIRED_TRACE_FIELDS:
            if not _text(trace.get(field)):
                errors.append({"code": "TRACE_FIELD_MISSING", "shot_id": sid, "field": field})
    if strategy is not None:
        try:
            parse_scene_directing_strategy(strategy, _dict(strategy.get("_contract")))
        except (SceneStrategyError, TypeError):
            # Strategy validation is performed by its own validator; this
            # contract reports only trace-level failures.
            pass
    expected_ids = [_text(row.get("plan_shot_id")) for row in _list(_dict(draft_shot_plan).get("shots")) if isinstance(row, dict)] if draft_shot_plan else None
    actual_ids = [_text(row.get("plan_shot_id")) for row in traces if isinstance(row, dict)]
    if expected_ids is not None and expected_ids != actual_ids:
        errors.append({"code": "TRACE_TOPOLOGY_MISMATCH", "expected": expected_ids, "actual": actual_ids})
    return {"valid": not errors, "errors": errors, "coverage": {"trace_count": len(traces), "required_fields": list(REQUIRED_TRACE_FIELDS), "complete_trace_count": sum(1 for row in traces if isinstance(row, dict) and all(_text(row.get(field)) for field in REQUIRED_TRACE_FIELDS))}}


def transition_shot_plan_state(*, current_state: str, target_state: str, layer1_pass: bool = False, layer2_pass: bool = False, critic_pass: bool = False, topology_changed: bool = False) -> dict[str, Any]:
    current, target = _text(current_state).upper(), _text(target_state).upper()
    if current not in SHOT_PLAN_STATES or target not in SHOT_PLAN_STATES:
        raise StrategyShotContractError("unknown ShotPlan lifecycle state")
    if target == "APPROVED":
        if not layer1_pass or not layer2_pass or not critic_pass:
            raise StrategyShotContractError("APPROVED requires Layer 1, Layer 2 and Creative Critic gates")
        if topology_changed:
            raise StrategyShotContractError("approved topology must be frozen before approval")
    topology_mutable = target != "APPROVED"
    return {"from": current, "to": target, "topology_mutable": topology_mutable, "topology_frozen": not topology_mutable}


__all__ = ["STRATEGY_TO_SHOT_SCHEMA_VERSION", "SUPPORTED_STRATEGY_SCHEMA_VERSIONS", "SHOT_PLAN_STATES", "REQUIRED_TRACE_FIELDS", "StrategyShotContractError", "build_strategy_to_shot_contract", "validate_strategy_traceability", "transition_shot_plan_state", "contract_fingerprint"]
