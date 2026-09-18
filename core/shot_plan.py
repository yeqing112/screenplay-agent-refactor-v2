"""Deterministic ShotPlan builder; never writes StoryboardShot."""
from __future__ import annotations

import hashlib
import json
from typing import Any


SHOT_PLAN_DEFAULT_POLICY_VERSION = "shot_plan_default_policy_v1"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_shot_plan(*, treatment: dict[str, Any], blocking: dict[str, Any]) -> dict[str, Any]:
    beats = treatment.get("beat_map") if isinstance(treatment.get("beat_map"), list) else []
    participants = blocking.get("participants") if isinstance(blocking.get("participants"), list) else []
    shots = []
    unknowns = list(blocking.get("unknowns") or []) if isinstance(blocking.get("unknowns"), list) else []
    purpose_map = {"setup": "establish", "obstacle": "action", "decision": "power_shift", "power_shift": "power_shift", "reveal": "reveal", "action": "action", "prop": "prop", "handoff": "prop"}
    for index, beat in enumerate(beats, start=1):
        if not isinstance(beat, dict):
            continue
        beat_type = str(beat.get("type") or "setup").lower()
        beat_id = str(beat.get("beat_id") or f"B{index:02d}")
        duration_source = "source_timing" if beat.get("duration_seconds") not in (None, "") else "authored_default"
        duration = float(beat.get("duration_seconds") or 4)
        duration = max(1.0, duration)
        beat_event = str(beat.get("event") or "")
        plan_shot_id = f"S{index:02d}"
        participant_ids = [str(item.get("character_id")) for item in participants if isinstance(item, dict) and str(item.get("character_id") or "").strip()]
        blocking_participants = [item for item in participants if isinstance(item, dict) and str(item.get("character_id") or "").strip()]
        character_states: dict[str, Any] = {}
        for participant in blocking_participants:
            character_id = str(participant.get("character_id") or "").strip()
            entry = participant.get("entry") if isinstance(participant.get("entry"), dict) else {}
            character_states[character_id] = {
                "position": participant.get("start_position", participant.get("position")),
                "facing": participant.get("facing"),
                "state": entry.get("value") if entry else None,
                "authority_class": "UPSTREAM_CONSTRAINT",
            }
        continuity = blocking.get("continuity_state") if isinstance(blocking.get("continuity_state"), dict) else {}
        continuity_states = continuity.get("states") if isinstance(continuity.get("states"), list) else []
        for state in continuity_states:
            if isinstance(state, dict) and str(state.get("character_id") or "").strip():
                character_states.setdefault(str(state["character_id"]), {}).update({"state": state.get("state"), "provenance": state.get("provenance"), "authority_class": "PRODUCTION_CONTINUITY_STATE"})
        prop_states = []
        for prop in blocking.get("props") if isinstance(blocking.get("props"), list) else []:
            if isinstance(prop, dict) and str(prop.get("prop_id") or "").strip():
                entry_value = prop.get("entry_state") or prop.get("state") or "unknown"
                exit_value = prop.get("exit_state") or prop.get("state") or entry_value
                prop_states.append({"prop_id": str(prop["prop_id"]), "scene_id": str(treatment.get("scene_id") or blocking.get("scene_id") or ""), "shot_id": plan_shot_id, "entry_state": entry_value, "exit_state": exit_value, "state": entry_value, "state_variant": prop.get("state_variant"), "location": prop.get("location"), "holder": prop.get("holder"), "owner": prop.get("owner") or prop.get("holder"), "visibility": prop.get("visibility"), "source": prop.get("source") or "approved_scene_blocking", "provenance": prop.get("provenance") or {"authority_class": "PRODUCTION_CONTINUITY_STATE", "source": "approved_scene_blocking"}, "unresolved": list(prop.get("unresolved") or []) if isinstance(prop.get("unresolved"), list) else []})
        entry_state = {"scene_id": str(treatment.get("scene_id") or blocking.get("scene_id") or ""), "shot_id": plan_shot_id, "participants": participant_ids, "characters": character_states, "props": prop_states, "source": "approved_scene_blocking", "provenance": {"authority_class": "PRODUCTION_CONTINUITY_STATE", "source": "approved_scene_blocking"}}
        exit_state = {"scene_id": str(treatment.get("scene_id") or blocking.get("scene_id") or ""), "shot_id": plan_shot_id, "last_event": beat_event, "characters": character_states, "props": prop_states, "source": "shot_plan_authored_transition", "provenance": {"authority_class": "PRODUCTION_CONTINUITY_STATE", "source": "shot_plan_authored_transition"}}
        camera = {"shot_size": "MS", "angle": "eye_level", "movement": "static", "speed": "slow", "camera_side": "center"}
        camera_provenance = {"authority_class": "SHOT_AUTHORING_DECISION", "source": "deterministic_default", "policy_version": SHOT_PLAN_DEFAULT_POLICY_VERSION}
        shots.append({
            "plan_shot_id": plan_shot_id,
            "scene_id": str(treatment.get("scene_id") or blocking.get("scene_id") or treatment.get("scene_name") or blocking.get("scene_name") or ""),
            "beat_id": beat_id,
            "purpose": purpose_map.get(beat_type, "coverage"),
            "dramatic_function": str(beat.get("dramatic_function") or ""),
            "event": beat_event,
            "participants": participant_ids,
            "spatial_source": "approved_scene_blocking",
            "camera": camera,
            "camera_provenance": camera_provenance,
            "duration_hint_seconds": duration,
            "duration_provenance": {"authority_class": "DERIVED_EXECUTION_CONSTRAINT" if duration_source == "source_timing" else "SHOT_AUTHORING_DECISION", "source": duration_source, "policy_version": SHOT_PLAN_DEFAULT_POLICY_VERSION},
            "action_beats": [{"action_id": f"{beat_id}_A01", "actor": participant_ids[0] if participant_ids else "", "action": beat_event, "start_seconds": 0.0, "end_seconds": round(max(0.5, duration * 0.85), 2)}] if beat_event else [],
            "entry_state": entry_state,
            "exit_state": exit_state,
            "asset_bindings": {"scene_asset_id": str(blocking.get("scene_asset_id") or blocking.get("scene_name") or ""), "character_asset_ids": participant_ids, "prop_asset_ids": [str(item.get("prop_id")) for item in (blocking.get("props") or []) if isinstance(item, dict) and item.get("prop_id")], "canonical_asset_identity": {"scene": str(blocking.get("scene_asset_id") or blocking.get("scene_name") or ""), "characters": participant_ids, "props": [str(item.get("prop_id")) for item in (blocking.get("props") or []) if isinstance(item, dict) and item.get("prop_id")]}, "locked_visual_references": (blocking.get("asset_authority") or {}).get("locked_constraints", []) if isinstance(blocking.get("asset_authority"), dict) else [], "media_asset_pending": (blocking.get("asset_authority") or {}).get("authoring_pending", []) if isinstance(blocking.get("asset_authority"), dict) else []},
            "continuity_contract": {"screen_direction": str(blocking.get("screen_direction") or "maintain"), "eyeline": {}, "prop_state": {str(item.get("prop_id")): item for item in prop_states if isinstance(item, dict) and item.get("prop_id")}, "character_state": character_states, "provenance": {"authority_class": "PRODUCTION_CONTINUITY_STATE", "source": "approved_scene_blocking + deterministic shot transition"}},
            "continuity": "inherit approved blocking and screen direction",
        })
    if not shots:
        unknowns.append("场景没有可规划的 beat")
    payload = {"scene_name": str(treatment.get("scene_name") or blocking.get("scene_name") or "未命名场景"), "shots": shots, "unknowns": sorted(set(str(item) for item in unknowns if str(item).strip())), "treatment_fingerprint": str(treatment.get("prompt_fingerprint") or ""), "blocking_fingerprint": str(blocking.get("evidence_fingerprint") or "")}
    fingerprint = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return {**payload, "status": "ready_for_review", "evidence_fingerprint": fingerprint, "model_info": {"mode": "shadow_deterministic", "llm_called": False}}
