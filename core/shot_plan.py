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
        shots.append({
            "plan_shot_id": f"S{index:02d}",
            "beat_id": str(beat.get("beat_id") or f"B{index:02d}"),
            "purpose": purpose_map.get(beat_type, "coverage"),
            "event": str(beat.get("event") or ""),
            "participants": [str(item.get("character_id")) for item in participants if isinstance(item, dict)],
            "spatial_source": "approved_scene_blocking",
            "camera": None,
            "duration_hint_seconds": None,
            "continuity": "inherit approved blocking and screen direction",
        })
    unknowns.extend(["景别、机位与时长需在 ShotPlan 审核时确认"] if shots else ["场景没有可规划的 beat"])
    payload = {"scene_name": str(treatment.get("scene_name") or blocking.get("scene_name") or "未命名场景"), "shots": shots, "unknowns": sorted(set(str(item) for item in unknowns if str(item).strip())), "treatment_fingerprint": str(treatment.get("prompt_fingerprint") or ""), "blocking_fingerprint": str(blocking.get("evidence_fingerprint") or "")}
    fingerprint = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return {**payload, "status": "ready_for_review", "evidence_fingerprint": fingerprint, "model_info": {"mode": "shadow_deterministic", "llm_called": False}}
