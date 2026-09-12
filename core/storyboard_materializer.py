"""Deterministic materialization of production storyboard shots from ShotPlan."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def materialize_storyboard_from_shot_plan(approved_shot_plan: dict[str, Any], treatment: dict[str, Any] | None = None, blocking: dict[str, Any] | None = None, asset_snapshot: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Project approved intent into execution rows without creative rewriting."""
    plan = approved_shot_plan if isinstance(approved_shot_plan, dict) else {}
    shots = plan.get("shots") if isinstance(plan.get("shots"), list) else []
    if any(not isinstance(item, dict) for item in shots):
        raise ValueError("Approved ShotPlan contains a non-object shot; materialization is fail-closed.")
    plan_shot_ids = [str(item.get("plan_shot_id") or "").strip() for item in shots]
    if any(not value for value in plan_shot_ids) or len(set(plan_shot_ids)) != len(plan_shot_ids):
        raise ValueError("Approved ShotPlan must contain unique plan_shot_id values.")
    scene_name = str(plan.get("scene_name") or "未命名场景").strip()
    output: list[dict[str, Any]] = []
    for index, item in enumerate(shots, start=1):
        camera = item.get("camera") if isinstance(item.get("camera"), dict) else {}
        duration = item.get("duration_hint_seconds") or item.get("duration_seconds") or 3
        action_beats = item.get("action_beats") if isinstance(item.get("action_beats"), list) else []
        asset_bindings = item.get("asset_bindings") if isinstance(item.get("asset_bindings"), dict) else {}
        shot_id = item.get("shot_id")
        if not isinstance(shot_id, int) or shot_id <= 0:
            shot_id = index
        output.append({
            "shot_id": shot_id,
            "plan_shot_id": str(item.get("plan_shot_id") or f"S{index:02d}"),
            "scene_name": scene_name,
            "dialogue": str(item.get("dialogue") or ""),
            "duration": max(1, int(float(duration))),
            "camera_angle": str(camera.get("angle") or "eye_level"),
            "camera_movement": str(camera.get("movement") or "static"),
            "camera_speed": str(camera.get("speed") or "slow"),
            "shot_purpose": str(item.get("purpose") or "coverage"),
            "start_state": item.get("entry_state") if isinstance(item.get("entry_state"), (dict, list)) else str(item.get("entry_state") or ""),
            "action_process": str(item.get("event") or ""),
            "action_beats": action_beats,
            "end_state": item.get("exit_state") if isinstance(item.get("exit_state"), (dict, list)) else str(item.get("exit_state") or ""),
            "asset_bindings": asset_bindings,
            "continuity_contract": item.get("continuity_contract") if isinstance(item.get("continuity_contract"), dict) else {},
            "meta_info": {
                "materializer": {"version": "storyboard_materializer_v1", "source_fingerprint": _fingerprint({"plan": plan, "treatment": treatment or {}, "blocking": blocking or {}, "assets": asset_snapshot or {}})},
                "shot_plan_ref": {"plan_shot_id": str(item.get("plan_shot_id") or f"S{index:02d}"), "plan_fingerprint": str(plan.get("evidence_fingerprint") or _fingerprint(plan))},
            },
        })
    return output
