"""Deterministic ShotPlan builder; never writes StoryboardShot."""
from __future__ import annotations

import hashlib
import json
from typing import Any


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
        duration = float(beat.get("duration_seconds") or 4)
        duration = max(1.0, duration)
        beat_event = str(beat.get("event") or "")
        participant_ids = [str(item.get("character_id")) for item in participants if isinstance(item, dict) and str(item.get("character_id") or "").strip()]
        shots.append({
            "plan_shot_id": f"S{index:02d}",
            "scene_id": str(treatment.get("scene_id") or blocking.get("scene_id") or treatment.get("scene_name") or blocking.get("scene_name") or ""),
            "beat_id": beat_id,
            "purpose": purpose_map.get(beat_type, "coverage"),
            "dramatic_function": str(beat.get("dramatic_function") or ""),
            "event": beat_event,
            "participants": participant_ids,
            "spatial_source": "approved_scene_blocking",
            "camera": {"shot_size": "MS", "angle": "eye_level", "movement": "static", "speed": "slow", "camera_side": "center"},
            "duration_hint_seconds": duration,
            "action_beats": [{"action_id": f"{beat_id}_A01", "actor": participant_ids[0] if participant_ids else "", "action": beat_event, "start_seconds": 0.0, "end_seconds": round(max(0.5, duration * 0.85), 2)}] if beat_event else [],
            "entry_state": {"participants": participant_ids},
            "exit_state": {"last_event": beat_event},
            "asset_bindings": {"scene_asset_id": str(blocking.get("scene_asset_id") or blocking.get("scene_name") or ""), "character_asset_ids": participant_ids, "prop_asset_ids": [str(item.get("prop_id")) for item in (blocking.get("props") or []) if isinstance(item, dict) and item.get("prop_id")]},
            "continuity_contract": {"screen_direction": str(blocking.get("screen_direction") or "maintain"), "eyeline": {}, "prop_state": {}},
            "continuity": "inherit approved blocking and screen direction",
        })
    if not shots:
        unknowns.append("场景没有可规划的 beat")
    payload = {"scene_name": str(treatment.get("scene_name") or blocking.get("scene_name") or "未命名场景"), "shots": shots, "unknowns": sorted(set(str(item) for item in unknowns if str(item).strip())), "treatment_fingerprint": str(treatment.get("prompt_fingerprint") or ""), "blocking_fingerprint": str(blocking.get("evidence_fingerprint") or "")}
    fingerprint = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return {**payload, "status": "ready_for_review", "evidence_fingerprint": fingerprint, "model_info": {"mode": "shadow_deterministic", "llm_called": False}}
