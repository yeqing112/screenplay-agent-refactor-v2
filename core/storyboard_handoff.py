"""Deterministic Phase C ShotPlan -> Storyboard Production handoff.

The Phase C ``ShotDesignDecision`` is the only creative authority.  This
module projects that authority into the structural contract consumed by the
Storyboard materializer.  It deliberately never reads legacy ``purpose`` or
``camera`` copies and never invents timing, camera speed, lighting, or prose
actions.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


HANDOFF_SCHEMA_VERSION = "storyboard_handoff_v1"
HANDOFF_PROJECTION_VERSION = "storyboard_handoff_projection_v1"
PROJECTION_ORIGIN = "SHOT_PLAN_PROJECTION"
CONTINUITY_ORIGIN = "PRODUCTION_CONTINUITY_STATE"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _norm(value: Any) -> str:
    return _text(value).lower()


def _canonical_shot_basis(shot: dict[str, Any]) -> dict[str, Any]:
    """Return only Phase C source fields; legacy copies are excluded."""
    return {
        "plan_shot_id": _text(shot.get("plan_shot_id")),
        "scene_id": _text(shot.get("scene_id")),
        "beat_refs": list(shot.get("beat_refs") or []),
        "beat_id": _text(shot.get("beat_id")),
        "shot_purpose": shot.get("shot_purpose"),
        "camera_state": shot.get("camera_state"),
        "axis_contract": shot.get("axis_contract"),
        "temporal_intent": shot.get("temporal_intent"),
        "spatial_binding": shot.get("spatial_binding"),
        "subjects": shot.get("subjects"),
        "participants": shot.get("participants"),
        "beat_refs_for_design": shot.get("beat_refs"),
        "director_decision_refs": shot.get("director_decision_refs"),
        "requirement_refs": shot.get("requirement_refs"),
        "information_refs": shot.get("information_refs"),
        "reaction_contract_refs": shot.get("reaction_contract_refs"),
        "coverage_roles": shot.get("coverage_roles"),
        "duration_hint_seconds": shot.get("duration_hint_seconds"),
        "asset_bindings": shot.get("asset_bindings"),
        "continuous_take": shot.get("continuous_take"),
        "cut_events": shot.get("cut_events"),
        # Entry/exit are accepted only as already-authoritative continuity
        # snapshots.  When a Blocking payload is supplied, it supersedes them.
        "entry_state": shot.get("entry_state"),
        "exit_state": shot.get("exit_state"),
    }


def _state_index(blocking: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    data = blocking if isinstance(blocking, dict) else {}
    raw = data.get("beat_spatial_states")
    if not isinstance(raw, list):
        raw = data.get("compiled_states")
    result: dict[str, dict[str, Any]] = {}
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and _text(item.get("beat_ref")):
                result[_text(item["beat_ref"])] = item
    elif isinstance(raw, dict):
        for key, item in raw.items():
            if isinstance(item, dict):
                result[_text(key)] = item
    return result


def _state_snapshot(*, shot: dict[str, Any], state_ref: str, blocking: dict[str, Any] | None, side: str) -> dict[str, Any]:
    index = _state_index(blocking)
    source = index.get(state_ref)
    if source is not None:
        characters = source.get("characters") if isinstance(source.get("characters"), dict) else {}
        normalized_characters = {
            str(key): (value.get("zone") if isinstance(value, dict) and "zone" in value else value)
            for key, value in characters.items()
        }
        return {
            "state_ref": state_ref,
            "characters": normalized_characters,
            "props": source.get("props", {}),
            "exit_access": source.get("exit_access", {}),
            "authority_class": CONTINUITY_ORIGIN,
            "compiler_version": source.get("compiler_version", blocking.get("compiler_version") if isinstance(blocking, dict) else ""),
            "side": side,
        }
    if blocking is not None:
        raise ValueError(f"STORYBOARD_HANDOFF_STATE_BINDING_INVALID: {shot.get('plan_shot_id') or '<shot>'} references missing Blocking state {state_ref}.")
    existing = shot.get(f"{side}_state")
    if isinstance(existing, (dict, list)):
        return {"state_ref": state_ref, "value": existing, "authority_class": CONTINUITY_ORIGIN, "side": side}
    raise ValueError(f"STORYBOARD_HANDOFF_STATE_BINDING_INVALID: {shot.get('plan_shot_id') or '<shot>'} has no {side} state for {state_ref}.")


def _continuity_projection(shot: dict[str, Any], state_refs: list[str]) -> dict[str, Any]:
    axis = shot.get("axis_contract") if isinstance(shot.get("axis_contract"), dict) else {}
    spatial = shot.get("spatial_binding") if isinstance(shot.get("spatial_binding"), dict) else {}
    return {
        "axis_ref": axis.get("axis_ref"),
        "axis_policy": axis.get("axis_policy"),
        "axis_applicability": axis.get("axis_applicability"),
        "screen_side_assignments": axis.get("screen_side_assignments", {}),
        "look_direction": axis.get("look_direction", {}),
        "continuous_take": shot.get("continuous_take") is True,
        "cut_events": list(shot.get("cut_events") or []),
        "blocking_state_refs": list(state_refs),
        "prop_refs": list(spatial.get("prop_refs") or []),
        "projection_origin": CONTINUITY_ORIGIN,
    }


def _action_projection(shot: dict[str, Any], beat_refs: list[str]) -> list[dict[str, Any]]:
    subjects = [str(item) for item in (shot.get("subjects") or []) if _text(item)]
    return [
        {
            "action_id": f"{_text(shot.get('plan_shot_id'))}_ACTION_{index:03d}",
            "beat_refs": [beat_ref],
            "actor_refs": subjects,
            "event_ref": beat_ref,
            "projection_origin": PROJECTION_ORIGIN,
        }
        for index, beat_ref in enumerate(beat_refs, start=1)
    ]


def project_shot_design_to_storyboard_handoff(
    shot_plan: dict[str, Any],
    *,
    blocking: dict[str, Any] | None = None,
    require_phase_c: bool = True,
) -> dict[str, Any]:
    """Project a canonical Phase C plan into ``storyboard_handoff_v1``.

    Every failure is explicit and happens before any materialization write.
    """
    plan = shot_plan if isinstance(shot_plan, dict) else {}
    if require_phase_c and plan.get("phase_c_semantic_ready") is not True:
        raise ValueError("STORYBOARD_HANDOFF_PHASE_C_NOT_READY: current ShotPlan is not Phase C semantic-ready.")
    scene_id = _text(plan.get("scene_id"))
    scene_name = _text(plan.get("scene_name"))
    if not scene_id:
        raise ValueError("STORYBOARD_HANDOFF_SCENE_ID_REQUIRED: scene_id is required.")
    if not scene_name:
        raise ValueError("STORYBOARD_HANDOFF_SCENE_NAME_REQUIRED: scene_name is required.")
    shots = plan.get("shots") if isinstance(plan.get("shots"), list) else []
    if not shots:
        raise ValueError("STORYBOARD_HANDOFF_SHOTS_REQUIRED: canonical ShotPlan contains no shots.")
    output: list[dict[str, Any]] = []
    ids: set[str] = set()
    for ordinal, source in enumerate(shots, start=1):
        if not isinstance(source, dict):
            raise ValueError(f"STORYBOARD_HANDOFF_SHOT_INVALID: shot[{ordinal}] must be an object.")
        plan_shot_id = _text(source.get("plan_shot_id"))
        if not plan_shot_id:
            raise ValueError("STORYBOARD_HANDOFF_SHOT_ID_REQUIRED: plan_shot_id is required.")
        if plan_shot_id in ids:
            raise ValueError(f"STORYBOARD_HANDOFF_SHOT_ID_DUPLICATE: {plan_shot_id}.")
        ids.add(plan_shot_id)
        purpose = _text(source.get("shot_purpose"))
        if not purpose:
            raise ValueError(f"STORYBOARD_HANDOFF_SHOT_PURPOSE_REQUIRED: {plan_shot_id} requires shot_purpose.")
        camera_state = source.get("camera_state")
        if not isinstance(camera_state, dict):
            raise ValueError(f"STORYBOARD_HANDOFF_CAMERA_STATE_REQUIRED: {plan_shot_id} requires camera_state.")
        for field in ("framing_class", "orientation", "movement"):
            if not _text(camera_state.get(field)):
                raise ValueError(f"STORYBOARD_HANDOFF_CAMERA_STATE_REQUIRED: {plan_shot_id} camera_state.{field} is required.")
        duration = source.get("duration_hint_seconds")
        if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration <= 0:
            raise ValueError(f"STORYBOARD_HANDOFF_DURATION_REQUIRED: {plan_shot_id} requires duration_hint_seconds.")
        beat_refs = [str(item) for item in (source.get("beat_refs") or []) if _text(item)]
        if not beat_refs:
            raise ValueError(f"STORYBOARD_HANDOFF_BEAT_BINDING_REQUIRED: {plan_shot_id} requires beat_refs.")
        spatial = source.get("spatial_binding") if isinstance(source.get("spatial_binding"), dict) else {}
        state_refs = [str(item) for item in (spatial.get("blocking_state_refs") or []) if _text(item)]
        if not state_refs:
            raise ValueError(f"STORYBOARD_HANDOFF_STATE_BINDING_INVALID: {plan_shot_id} has no blocking_state_refs.")
        entry = _state_snapshot(shot=source, state_ref=state_refs[0], blocking=blocking, side="entry")
        exit = _state_snapshot(shot=source, state_ref=state_refs[-1], blocking=blocking, side="exit")
        continuity = _continuity_projection(source, state_refs)
        asset_bindings = source.get("asset_bindings") if isinstance(source.get("asset_bindings"), dict) else {}
        if not asset_bindings:
            asset_bindings = {"scene": scene_id, "characters": list(source.get("subjects") or []), "props": list(spatial.get("prop_refs") or [])}
        camera = {
            "shot_size": _text(camera_state.get("framing_class")),
            "angle": _norm(camera_state.get("orientation")),
            "movement": _norm(camera_state.get("movement")),
        }
        if _text(camera_state.get("support")):
            camera["support"] = _norm(camera_state.get("support"))
        handoff_shot = {
            "plan_shot_id": plan_shot_id,
            "beat_id": _text(source.get("beat_id")) or beat_refs[0],
            # Structured Phase C semantic refs are carried through the
            # handoff so the materializer never has to recover truth from
            # prose fields or from legacy Storyboard columns.
            "beat_refs": beat_refs,
            "subjects": list(source.get("subjects") or []),
            "camera_state": dict(camera_state),
            "axis_contract": dict(source.get("axis_contract") or {}) if isinstance(source.get("axis_contract"), dict) else {},
            "spatial_binding": dict(spatial),
            "temporal_intent": dict(source.get("temporal_intent") or {}) if isinstance(source.get("temporal_intent"), dict) else {},
            "information_visibility": source.get("information_visibility"),
            "continuous_take": source.get("continuous_take") is True,
            "cut_events": list(source.get("cut_events") or []),
            "purpose": purpose,
            "camera": camera,
            "duration_hint_seconds": duration,
            "action_beats": _action_projection(source, beat_refs),
            "entry_state": entry,
            "exit_state": exit,
            "asset_bindings": asset_bindings,
            "continuity_contract": continuity,
            "dialogue": source.get("dialogue") if isinstance(source.get("dialogue"), str) else "",
            "transition": source.get("transition") if isinstance(source.get("transition"), str) else "",
            "lighting": source.get("lighting") if isinstance(source.get("lighting"), str) else "",
            "event": "",
            "projection_origin": PROJECTION_ORIGIN,
            "meta_info": {
                "projection_origin": PROJECTION_ORIGIN,
                "authority_classes": {
                    "shot_plan_projection": ["purpose", "camera", "duration_hint_seconds", "action_beats", "asset_bindings", "continuity_contract"],
                    "production_continuity_state": ["entry_state", "exit_state"],
                    "structural_materialization_metadata": ["plan_shot_id", "beat_id"],
                },
                "shot_design_refs": {
                    "information_refs": list(source.get("information_refs") or []),
                    "reaction_contract_refs": list(source.get("reaction_contract_refs") or []),
                    "coverage_roles": list(source.get("coverage_roles") or []),
                    "director_decision_refs": list(source.get("director_decision_refs") or []),
                    "requirement_refs": list(source.get("requirement_refs") or []),
                },
            },
        }
        handoff_shot["storyboard_handoff_shot_fingerprint"] = fingerprint({
            "projection_version": HANDOFF_PROJECTION_VERSION,
            "canonical_shot": _canonical_shot_basis(source),
        })
        output.append(handoff_shot)
    source_basis = {"scene_id": scene_id, "scene_name": scene_name, "shots": [_canonical_shot_basis(item) for item in shots]}
    source_fp = fingerprint(source_basis)
    result = {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "projection_version": HANDOFF_PROJECTION_VERSION,
        "scene_id": scene_id,
        "scene_name": scene_name,
        "shots": output,
        "source_shot_plan_fingerprint": source_fp,
        "source_shot_plan_payload_hash": _text(plan.get("payload_hash")),
        "projection_origin": PROJECTION_ORIGIN,
    }
    result["handoff_fingerprint"] = fingerprint({key: value for key, value in result.items() if key != "handoff_fingerprint"})
    return result


def validate_storyboard_handoff(handoff: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if not isinstance(handoff, dict) or handoff.get("schema_version") != HANDOFF_SCHEMA_VERSION:
        return [{"code": "STORYBOARD_HANDOFF_SCHEMA_VERSION_REQUIRED"}]
    shots = handoff.get("shots")
    if not isinstance(shots, list) or not shots:
        return [{"code": "STORYBOARD_HANDOFF_SHOTS_REQUIRED"}]
    seen: set[str] = set()
    for index, shot in enumerate(shots, start=1):
        if not isinstance(shot, dict):
            errors.append({"code": "STORYBOARD_HANDOFF_SHOT_INVALID", "index": index})
            continue
        sid = _text(shot.get("plan_shot_id"))
        if not sid:
            errors.append({"code": "STORYBOARD_HANDOFF_SHOT_ID_REQUIRED", "index": index})
        elif sid in seen:
            errors.append({"code": "STORYBOARD_HANDOFF_SHOT_ID_DUPLICATE", "plan_shot_id": sid})
        seen.add(sid)
        if not _text(shot.get("purpose")):
            errors.append({"code": "STORYBOARD_HANDOFF_SHOT_PURPOSE_REQUIRED", "plan_shot_id": sid})
        camera = shot.get("camera")
        if not isinstance(camera, dict) or any(not _text(camera.get(field)) for field in ("shot_size", "angle", "movement")):
            errors.append({"code": "STORYBOARD_HANDOFF_CAMERA_STATE_REQUIRED", "plan_shot_id": sid})
        duration = shot.get("duration_hint_seconds")
        if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration <= 0:
            errors.append({"code": "STORYBOARD_HANDOFF_DURATION_REQUIRED", "plan_shot_id": sid})
        if not isinstance(shot.get("action_beats"), list):
            errors.append({"code": "STORYBOARD_HANDOFF_ACTION_BEATS_INVALID", "plan_shot_id": sid})
        if not isinstance(shot.get("entry_state"), (dict, list)) or not isinstance(shot.get("exit_state"), (dict, list)):
            errors.append({"code": "STORYBOARD_HANDOFF_STATE_BINDING_INVALID", "plan_shot_id": sid})
        if not isinstance(shot.get("continuity_contract"), dict):
            errors.append({"code": "STORYBOARD_HANDOFF_CONTINUITY_INVALID", "plan_shot_id": sid})
    expected = fingerprint({key: value for key, value in handoff.items() if key != "handoff_fingerprint"})
    if _text(handoff.get("handoff_fingerprint")) != expected:
        errors.append({"code": "STORYBOARD_HANDOFF_FINGERPRINT_INVALID"})
    return errors


__all__ = [
    "HANDOFF_SCHEMA_VERSION",
    "HANDOFF_PROJECTION_VERSION",
    "PROJECTION_ORIGIN",
    "CONTINUITY_ORIGIN",
    "fingerprint",
    "project_shot_design_to_storyboard_handoff",
    "validate_storyboard_handoff",
]
