"""Phase C structured ShotPlan contracts and deterministic compilers.

This module is deliberately provider free.  It turns current Director and
Blocking payloads into an auditable ShotPlan proposal; prose remains a reader
projection and never participates in qualification.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

SHOT_PLAN_CONTRACT_VERSION = "shot_plan_phase_c_v1"
COVERAGE_ROLES = {
    "PRIMARY_BEAT_COVERAGE", "REACTION_COVERAGE", "INSERT_EVIDENCE",
    "RELATIONAL_COVERAGE", "SPATIAL_ORIENTATION", "TRANSITION_COVERAGE",
    "BRIDGE_COVERAGE", "SCENE_EXIT_COVERAGE",
}
PURPOSES = {
    "ESTABLISH_SPACE", "ESTABLISH_RELATIONSHIP", "INTRODUCE_INFORMATION",
    "REVEAL_INFORMATION", "WITHHOLD_INFORMATION", "REDIRECT_ATTENTION",
    "CAPTURE_REACTION", "ESCALATE_THREAT", "SHIFT_POWER", "CONFIRM_EVIDENCE",
    "FOLLOW_ACTION", "ISOLATE_CHARACTER", "CONNECT_CHARACTERS",
    "SHOW_SPATIAL_RELATION", "SHOW_PROP_STATE", "BRIDGE_BEATS", "SCENE_EXIT",
}
FRAMINGS = {"EXTREME_WIDE", "WIDE", "MEDIUM_WIDE", "MEDIUM", "MEDIUM_CLOSE", "CLOSE", "EXTREME_CLOSE", "INSERT", "OVER_SHOULDER", "TWO_SHOT", "GROUP_SHOT", "POV"}
MOVEMENTS = {"NONE", "PAN", "TILT", "DOLLY_IN", "DOLLY_OUT", "TRACK", "ARC", "HANDHELD_FOLLOW", "REFRAME"}

def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def _hash(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode()).hexdigest()

def _beats(treatment: dict[str, Any]) -> list[dict[str, Any]]:
    return [b for b in treatment.get("beat_map", []) if isinstance(b, dict) and str(b.get("beat_id") or "").strip()]

def _decisions(treatment: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = treatment.get("director_beat_decisions") or treatment.get("director_decisions") or []
    if isinstance(raw, dict):
        raw = raw.get("director_beat_decisions") or raw.get("decisions") or []
    return {str(d.get("beat_ref") or d.get("beat_id")): d for d in raw if isinstance(d, dict) and str(d.get("beat_ref") or d.get("beat_id") or "").strip()}

def _blocking_state(blocking: dict[str, Any], beat_id: str) -> dict[str, Any]:
    for key in ("beat_spatial_states", "states", "blocking_states"):
        for state in blocking.get(key, []) if isinstance(blocking.get(key), list) else []:
            if isinstance(state, dict) and str(state.get("beat_ref") or state.get("beat_id") or "") == beat_id:
                characters = state.get("characters") or state.get("subject_zones") or {}
                zones = {str(k): (v.get("zone") if isinstance(v, dict) else v) for k, v in characters.items()} if isinstance(characters, dict) else {}
                return {**state, "state_ref": str(state.get("state_ref") or beat_id), "subject_zones": zones, "prop_states": state.get("props") if isinstance(state.get("props"), dict) else {}}
    participants = blocking.get("participants") if isinstance(blocking.get("participants"), list) else []
    zones = {str(p.get("character_id")): p.get("start_position", p.get("position")) for p in participants if isinstance(p, dict) and p.get("character_id")}
    return {"state_ref": beat_id, "subject_zones": zones, "prop_states": {}, "source": "current_scene_blocking"}

def _changed_props(blocking: dict[str, Any], beat_id: str) -> list[str]:
    """Materialize prop evidence only from BlockingState transitions."""
    states = []
    for item in blocking.get("beat_spatial_states", []) if isinstance(blocking.get("beat_spatial_states"), list) else []:
        if isinstance(item, dict): states.append(item)
    prior = {}
    current = {}
    for item in states:
        props = item.get("props") if isinstance(item.get("props"), dict) else {}
        if str(item.get("beat_ref")) == beat_id: current = props; break
        prior = {str(k): (v.get("state") if isinstance(v, dict) else v) for k, v in props.items()}
    now = {str(k): (v.get("state") if isinstance(v, dict) else v) for k, v in current.items()}
    return sorted(k for k, value in now.items() if prior.get(k) != value and value not in (None, "", "ABSENT"))

def build_beat_coverage_contracts(*, treatment: dict[str, Any], blocking: dict[str, Any]) -> list[dict[str, Any]]:
    """Project objective coverage requirements from upstream semantics only."""
    result = []
    for beat in _beats(treatment):
        bid = str(beat["beat_id"])
        typ = str(beat.get("beat_type") or beat.get("type") or "").upper()
        decision = _decisions(treatment).get(bid, {})
        required = ["PRIMARY_BEAT_COVERAGE"]
        reaction_contracts = decision.get("reaction_contracts") if isinstance(decision.get("reaction_contracts"), list) else []
        if reaction_contracts or beat.get("requires_reaction") or beat.get("reaction_contract") or beat.get("reaction_required"):
            required.append("REACTION_COVERAGE")
        prop_refs = list(beat.get("prop_refs") or beat.get("critical_prop_refs") or [])
        if not prop_refs:
            prop_refs = _changed_props(blocking, bid)
        if typ in {"PROP", "EVIDENCE"} or prop_refs:
            required.append("INSERT_EVIDENCE")
        if bid == _beats(treatment)[-1]["beat_id"]:
            required.append("SCENE_EXIT_COVERAGE")
        result.append({"beat_ref": bid, "required_coverages": sorted(set(required)), "required_subjects": sorted({str(x) for x in (beat.get("characters") or beat.get("participants") or []) if str(x).strip()}), "reaction_contract_refs": [str(x.get("contract_id") or x.get("state_delta_ref") or x.get("trigger_ref")) for x in reaction_contracts if isinstance(x, dict)] or ([str(beat.get("reaction_contract"))] if beat.get("reaction_contract") else []), "required_prop_refs": sorted({str(x) for x in prop_refs if str(x).strip()})})
    return result

def compile_shot_coverage(*, treatment: dict[str, Any], blocking: dict[str, Any], shots: list[dict[str, Any]], contracts: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    contracts = contracts if contracts is not None else build_beat_coverage_contracts(treatment=treatment, blocking=blocking)
    out = []
    for contract in contracts:
        satisfied = {role: [] for role in contract["required_coverages"]}
        for shot in shots:
            if str(contract["beat_ref"]) in [str(x) for x in shot.get("beat_refs", [])]:
                for role in shot.get("coverage_roles", []):
                    if role in satisfied: satisfied[role].append(str(shot["shot_id"]))
        out.append({"beat_ref": contract["beat_ref"], "required": contract["required_coverages"], "satisfied_by": satisfied, "complete": all(satisfied.values())})
    return out

def compile_shot_continuity(*, shots: list[dict[str, Any]], blocking: dict[str, Any]) -> dict[str, Any]:
    axis = str(blocking.get("interaction_axis") or blocking.get("axis_ref") or "AXIS_UNSPECIFIED")
    compiled = []
    previous = None
    for shot in shots:
        c = shot.get("continuity_contract") or {}
        compiled.append({"shot_id": shot["shot_id"], "axis_ref": c.get("axis_ref", axis), "axis_policy": c.get("axis_policy", "PRESERVE"), "screen_direction_state": c.get("screen_direction_state", {}), "blocking_state_ref": c.get("blocking_state_ref")})
        previous = c
    return {"compiler_version": "shot_continuity_compiler_v1", "shots": compiled}

def estimate_runtime(*, shots: list[dict[str, Any]]) -> dict[str, Any]:
    total = round(sum(float(s.get("estimated_duration_ms") or 0) for s in shots), 2)
    return {"estimator_version": "duration_estimator_v1", "shot_count": len(shots), "estimated_duration_ms": total, "estimated_duration_seconds": round(total / 1000, 2)}

def validate_shot_plan_contract(*, plan: dict[str, Any], treatment: dict[str, Any], blocking: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    shots = plan.get("shots") if isinstance(plan.get("shots"), list) else []
    ids = [str(s.get("shot_id") or "") for s in shots if isinstance(s, dict)]
    if len(ids) != len(set(ids)) or any(not x for x in ids): errors.append({"code": "SHOT_ID_INVALID"})
    beat_ids = {str(b["beat_id"]) for b in _beats(treatment)}
    ordered_beats = [str(b["beat_id"]) for b in _beats(treatment)]
    decision_ids = {str(d.get("decision_id")) for d in _decisions(treatment).values() if d.get("decision_id")}
    for shot in shots:
        if not isinstance(shot, dict): errors.append({"code": "SHOT_SCHEMA_INVALID"}); continue
        if not set(map(str, shot.get("beat_refs", []))) <= beat_ids: errors.append({"code": "SHOT_BEAT_REF_INVALID", "shot_id": shot.get("shot_id")})
        if any(str(ref) not in decision_ids for ref in shot.get("director_decision_refs", [])):
            errors.append({"code": "SHOT_DIRECTOR_DECISION_REF_INVALID", "shot_id": shot.get("shot_id")})
        if shot.get("shot_purpose") not in PURPOSES: errors.append({"code": "SHOT_PURPOSE_INVALID", "shot_id": shot.get("shot_id")})
        if not set(shot.get("coverage_roles", [])) <= COVERAGE_ROLES: errors.append({"code": "SHOT_COVERAGE_ROLE_INVALID"})
        camera = shot.get("camera_state") or {}
        if camera.get("framing_class") not in FRAMINGS or camera.get("movement") not in MOVEMENTS or not camera.get("orientation"): errors.append({"code": "SHOT_CAMERA_STATE_INCOMPLETE", "shot_id": shot.get("shot_id")})
        if camera.get("movement") != "NONE" and not all(camera.get(k) for k in ("movement_trigger", "movement_target", "movement_end_condition")): errors.append({"code": "SHOT_CAMERA_MOVEMENT_INCOMPLETE"})
        if len(shot.get("camera_segments", [1])) != 1: errors.append({"code": "SHOT_INTERNAL_CUT_INVALID", "shot_id": shot.get("shot_id")})
        binding = shot.get("spatial_binding") or {}
        state = _blocking_state(blocking, str((shot.get("beat_refs") or [""])[0]))
        first_beat_ref = str((shot.get("beat_refs") or [""])[0])
        if first_beat_ref not in beat_ids or str(binding.get("blocking_state_ref") or "") != str(state.get("state_ref") or first_beat_ref):
            errors.append({"code": "SHOT_BLOCKING_STATE_REF_INVALID", "shot_id": shot.get("shot_id")})
        expected_zones = state.get("subject_zones") if isinstance(state, dict) else None
        actual_zones = binding.get("subject_zones") if isinstance(binding.get("subject_zones"), dict) else {}
        if isinstance(expected_zones, dict) and expected_zones and actual_zones != expected_zones:
            errors.append({"code": "SHOT_SPATIAL_BINDING_INVALID", "shot_id": shot.get("shot_id")})
        declared_axis = (shot.get("continuity_contract") or {}).get("axis_ref")
        if not declared_axis:
            errors.append({"code": "SHOT_AXIS_CONTRACT_INVALID", "shot_id": shot.get("shot_id")})
        if not set((binding.get("prop_refs") or [])) <= set((state.get("prop_states") or {}).keys()):
            errors.append({"code": "SHOT_PROP_REF_INVALID", "shot_id": shot.get("shot_id")})
    flattened = [str(ref) for shot in shots for ref in (shot.get("beat_refs") or []) if str(ref) in beat_ids]
    if flattened != sorted(flattened, key=ordered_beats.index):
        errors.append({"code": "SHOT_BEAT_ORDER_INVALID"})
    coverage = compile_shot_coverage(treatment=treatment, blocking=blocking, shots=shots)
    for item in coverage:
        if not item["complete"]: errors.append({"code": "SHOT_COVERAGE_INCOMPLETE", "beat_ref": item["beat_ref"]})
    return {"valid": not errors, "errors": errors, "coverage": coverage}

def build_phase_c_shot_plan(*, treatment: dict[str, Any], blocking: dict[str, Any], script_authority: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a deterministic, full-scene proposal from current Phase B inputs."""
    contracts = build_beat_coverage_contracts(treatment=treatment, blocking=blocking)
    shots = []
    for i, beat in enumerate(_beats(treatment), 1):
        bid, event = str(beat["beat_id"]), str(beat.get("event") or "")
        decision = _decisions(treatment).get(bid, {})
        roles = ["PRIMARY_BEAT_COVERAGE"]
        if "REACTION_COVERAGE" in next(c["required_coverages"] for c in contracts if c["beat_ref"] == bid): roles.append("REACTION_COVERAGE")
        contract = next(c for c in contracts if c["beat_ref"] == bid)
        if "INSERT_EVIDENCE" in contract["required_coverages"]: roles.append("INSERT_EVIDENCE")
        if i == len(_beats(treatment)): roles.append("SCENE_EXIT_COVERAGE")
        state = _blocking_state(blocking, bid)
        subjects = [str(x) for x in (beat.get("characters") or beat.get("participants") or []) if str(x).strip()]
        framing = "INSERT" if "INSERT_EVIDENCE" in roles else ("MEDIUM_CLOSE" if "REACTION_COVERAGE" in roles else "MEDIUM")
        purpose_map = {"INTRODUCE_ANOMALY": "REVEAL_INFORMATION", "CONFIRM_EVIDENCE": "CONFIRM_EVIDENCE", "ESCALATE_THREAT": "ESCALATE_THREAT", "SHIFT_POWER": "SHIFT_POWER", "HOOK_NEXT_SCENE": "SCENE_EXIT", "RAISE_SUSPICION": "WITHHOLD_INFORMATION", "TRIGGER_DECISION": "REDIRECT_ATTENTION", "SETUP_RELATIONSHIP": "ESTABLISH_RELATIONSHIP"}
        decision_id = str(decision.get("decision_id") or "")
        shot = {"shot_id": f"SH_{str(treatment.get('scene_id') or blocking.get('scene_id') or 'SCENE').replace('-', '_')}_{i:03d}", "scene_id": str(treatment.get("scene_id") or blocking.get("scene_id") or ""), "beat_refs": [bid], "director_decision_refs": [decision_id] if decision_id else [], "shot_purpose": "SCENE_EXIT" if i == len(_beats(treatment)) else purpose_map.get(str(decision.get("dramatic_purpose") or ""), "FOLLOW_ACTION"), "coverage_roles": roles, "dramatic_payload": {"primary_subject": subjects[0] if subjects else "", "secondary_subjects": subjects[1:], "information_delivered": [str(x) for x in (decision.get("audience_state_delta") or {}).get("knowledge_added", [])] if isinstance(decision.get("audience_state_delta"), dict) else [], "reaction_required": [str(x.get("character_ref")) for x in (decision.get("reaction_contracts") or []) if isinstance(x, dict) and x.get("character_ref")]}, "spatial_binding": {"blocking_state_ref": state.get("state_ref", bid), "subject_zones": state.get("subject_zones", {}), "prop_refs": contract.get("required_prop_refs", [])}, "information_visibility": "CHARACTER_AND_AUDIENCE", "camera_state": {"framing_class": framing, "orientation": "EYE_LEVEL", "support": "STATIC", "movement": "NONE", "subject_binding": subjects}, "continuity_contract": {"axis_ref": str(blocking.get("interaction_axis") or blocking.get("axis_ref") or "AXIS_UNSPECIFIED"), "axis_policy": "PRESERVE", "blocking_state_ref": state.get("state_ref", bid), "screen_direction_state": {}, "prop_refs": contract.get("required_prop_refs", [])}, "temporal_intent": {"duration_mode": "REACTION_HOLD" if "REACTION_COVERAGE" in roles else "ACTION_COMPLETION", "cut_trigger": event}, "camera_segments": [{"camera_state": "single_continuous_take"}], "estimated_duration_ms": int(max(1000, float(beat.get("duration_seconds") or 3) * 1000)), "shot_description": event}
        shots.append(shot)
    coverage = compile_shot_coverage(treatment=treatment, blocking=blocking, shots=shots, contracts=contracts)
    continuity = compile_shot_continuity(shots=shots, blocking=blocking)
    runtime = estimate_runtime(shots=shots)
    plan = {"contract_version": SHOT_PLAN_CONTRACT_VERSION, "scene_id": treatment.get("scene_id") or blocking.get("scene_id") or "", "shots": shots, "coverage_contracts": contracts, "coverage_results": coverage, "compiled_continuity": continuity, "runtime_estimate": runtime, "phase_c_semantic_ready": all(x["complete"] for x in coverage), "source_lineage": script_authority or {}, "provider_provenance": {"origin": "DETERMINISTIC_BUILDER", "provider_calls": 0}}
    plan["payload_hash"] = _hash(plan)
    return plan
