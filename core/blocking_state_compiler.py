"""Deterministic BlockingTransition -> BeatSpatialState compiler."""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

COMPILER_VERSION = "blocking_state_compiler_v1"
TRANSITION_PROPERTIES = frozenset({"ZONE", "FACING", "POSTURE", "POSSESSION", "PROP_STATE", "PROP_ZONE", "EXIT_ACCESS", "INTERACTION_STATE", "ATTENTION_TARGET"})
EXIT_STATES = frozenset({"AVAILABLE", "CONTESTED", "BLOCKED"})


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _error(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "severity": "blocker", "message": message, **extra}


def _state_refs(state: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    chars = {str(key) for key in (state.get("characters") or {})} if isinstance(state.get("characters"), dict) else set()
    props = {str(key) for key in (state.get("props") or {})} if isinstance(state.get("props"), dict) else set()
    zones = set()
    for item in (state.get("characters") or {}).values() if isinstance(state.get("characters"), dict) else []:
        if isinstance(item, dict) and item.get("zone"):
            zones.add(str(item["zone"]))
    for item in (state.get("props") or {}).values() if isinstance(state.get("props"), dict) else []:
        if isinstance(item, dict) and item.get("zone"):
            zones.add(str(item["zone"]))
    zones.update(str(key) for key in (state.get("exit_access") or {}) if isinstance(state.get("exit_access"), dict))
    return chars, props, zones


def _apply_change(state: dict[str, Any], transition: dict[str, Any], change: dict[str, Any], valid_zones: set[str], valid_subjects: set[str]) -> dict[str, Any] | None:
    prop = _text(change.get("property")).upper()
    if prop not in TRANSITION_PROPERTIES:
        return _error("BLOCKING_TRANSITION_PROPERTY_INVALID", "unsupported transition property", property=prop)
    subject_type = _text(transition.get("subject_type")).upper()
    subject = _text(transition.get("subject_ref"))
    if not subject or subject not in valid_subjects and subject_type not in {"EXIT_ACCESS", "ZONE"}:
        return _error("BLOCKING_SUBJECT_REF_INVALID", "transition subject is not in initial state", subject_ref=subject)
    old = change.get("from")
    new = change.get("to")
    if prop in {"ZONE", "PROP_ZONE"} and valid_zones and str(new) not in valid_zones:
        return _error("BLOCKING_ZONE_REF_INVALID", "transition references an unknown zone", zone=str(new))
    if prop == "EXIT_ACCESS" and str(new).upper() not in EXIT_STATES:
        return _error("BLOCKING_EXIT_ACCESS_INVALID", "exit access state is invalid", state=new)
    if prop in {"ZONE", "FACING", "POSTURE", "POSSESSION", "PROP_STATE", "PROP_ZONE", "INTERACTION_STATE", "ATTENTION_TARGET"}:
        container = state["props"] if subject_type == "PROP" or prop in {"PROP_STATE", "PROP_ZONE"} else state["characters"]
        current = container.get(subject)
        if not isinstance(current, dict):
            return _error("BLOCKING_SUBJECT_REF_INVALID", "transition subject has no state", subject_ref=subject)
        field = {"PROP_ZONE": "zone", "PROP_STATE": "state", "ATTENTION_TARGET": "attention_target"}.get(prop, prop.lower())
        actual = current.get(field)
        if old is not None and actual != old:
            return _error("BLOCKING_TRANSITION_SOURCE_STATE_MISMATCH", "transition source does not match compiled state", subject_ref=subject, property=prop, expected=old, actual=actual)
        current[field] = new
    elif prop == "EXIT_ACCESS":
        key = subject or _text(change.get("zone"))
        if key not in state.setdefault("exit_access", {}):
            state["exit_access"][key] = {"state": "AVAILABLE"}
        current = state["exit_access"][key]
        actual = current.get("state")
        if old is not None and actual != old:
            return _error("BLOCKING_TRANSITION_SOURCE_STATE_MISMATCH", "exit access source does not match compiled state", subject_ref=key, property=prop, expected=old, actual=actual)
        current["state"] = str(new).upper()
        if transition.get("controller_ref"):
            current["controller_ref"] = transition["controller_ref"]
    return None


def compile_blocking_states(initial_state: dict[str, Any], ordered_beats: list[dict[str, Any]], blocking_transitions: list[dict[str, Any]], *, valid_zones: set[str] | list[str] | None = None) -> dict[str, Any]:
    """Compile complete state snapshots in ordered ScriptIR beat order."""
    errors: list[dict[str, Any]] = []
    if not isinstance(initial_state, dict) or not isinstance(initial_state.get("characters"), dict) or not isinstance(initial_state.get("props"), dict) or not isinstance(initial_state.get("exit_access", {}), dict):
        return {"status": "blocked", "errors": [_error("BLOCKING_INITIAL_STATE_MISSING", "initial_state must contain characters, props and exit_access")], "states": [], "compiler_version": COMPILER_VERSION}
    state = copy.deepcopy(initial_state)
    declared_chars, declared_props, inferred_zones = _state_refs(state)
    zones = {str(x) for x in valid_zones} if valid_zones is not None else inferred_zones
    valid_subjects = declared_chars | declared_props
    by_beat: dict[str, list[dict[str, Any]]] = {}
    seen_keys: set[tuple[str, str, str]] = set()
    for transition in blocking_transitions if isinstance(blocking_transitions, list) else []:
        if not isinstance(transition, dict):
            errors.append(_error("BLOCKING_TRANSITION_SCHEMA_INVALID", "transition must be an object")); continue
        beat_ref = _text(transition.get("beat_ref"))
        if not beat_ref or not _text(transition.get("transition_id")) or not isinstance(transition.get("changes"), list):
            errors.append(_error("BLOCKING_TRANSITION_SCHEMA_INVALID", "transition requires transition_id, beat_ref and changes")); continue
        for change in transition["changes"]:
            key = (beat_ref, _text(transition.get("subject_ref")), _text(change.get("property")).upper() if isinstance(change, dict) else "")
            if key in seen_keys:
                errors.append(_error("BLOCKING_TRANSITION_CONFLICT", "same beat/subject/property has multiple transitions", key=key))
            seen_keys.add(key)
        by_beat.setdefault(beat_ref, []).append(transition)
    states: list[dict[str, Any]] = []
    beat_refs = {_text(b.get("beat_id") or b.get("id")) for b in ordered_beats if isinstance(b, dict)}
    for transition in blocking_transitions if isinstance(blocking_transitions, list) else []:
        if isinstance(transition, dict) and _text(transition.get("beat_ref")) not in beat_refs:
            errors.append(_error("BLOCKING_BEAT_REF_INVALID", "transition references an unknown beat", beat_ref=transition.get("beat_ref")))
    for beat in ordered_beats if isinstance(ordered_beats, list) else []:
        if not isinstance(beat, dict):
            continue
        ref = _text(beat.get("beat_id") or beat.get("id"))
        for transition in by_beat.get(ref, []):
            for change in transition.get("changes", []):
                if isinstance(change, dict):
                    issue = _apply_change(state, transition, change, zones, valid_subjects)
                    if issue:
                        errors.append(issue)
        states.append({"beat_ref": ref, "characters": copy.deepcopy(state["characters"]), "props": copy.deepcopy(state["props"]), "exit_access": copy.deepcopy(state.get("exit_access", {})), "authority_class": "DERIVED_PROJECTION", "compiler_version": COMPILER_VERSION})
    compiled_hash = hashlib.sha256(_canon(states).encode("utf-8")).hexdigest()
    return {"status": "qualified" if not errors else "blocked", "errors": errors, "states": states, "compiler_version": COMPILER_VERSION, "compiled_states_hash": compiled_hash, "state_count": len(states)}


def validate_blocking_contract(blocking: dict[str, Any], *, ordered_beats: list[dict[str, Any]]) -> dict[str, Any]:
    initial = blocking.get("initial_state") if isinstance(blocking, dict) else None
    transitions = blocking.get("blocking_transitions") if isinstance(blocking, dict) else None
    if not isinstance(initial, dict) or not isinstance(transitions, list):
        return {"status": "blocked", "errors": [_error("BLOCKING_NOT_MATERIALIZED", "initial_state and blocking_transitions are required")], "warnings": []}
    result = compile_blocking_states(initial, ordered_beats, transitions, valid_zones=set(blocking.get("zone_ids") or []))
    required = {_text(x.get("beat_id") or x.get("id")) for x in ordered_beats if isinstance(x, dict) and (str(x.get("importance", "")).lower() == "critical" or x.get("requires_reaction") is True)}
    covered = {_text(x.get("beat_ref")) for x in result.get("states", [])}
    if not required.issubset(covered):
        result.setdefault("errors", []).append(_error("BLOCKING_CRITICAL_BEAT_COVERAGE_INCOMPLETE", "compiled states do not cover critical beats", missing=sorted(required - covered)))
        result["status"] = "blocked"
    return {**result, "critical_beat_count": len(required), "critical_beat_coverage": len(required & covered)}


__all__ = ["COMPILER_VERSION", "TRANSITION_PROPERTIES", "compile_blocking_states", "validate_blocking_contract"]
