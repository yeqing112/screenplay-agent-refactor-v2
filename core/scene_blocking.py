"""Deterministic, evidence-first SceneBlocking / Spatial Engine shadow builder."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_scene_blocking(*, scene: dict[str, Any], treatment: dict[str, Any], source_script_hash: str = "") -> dict[str, Any]:
    """Build spatial facts only from declared blocking; never invent coordinates."""
    scene_name = str(scene.get("name") or treatment.get("scene_name") or "未命名场景").strip()
    intents = treatment.get("character_intents") if isinstance(treatment.get("character_intents"), dict) else {}
    declared = scene.get("character_blocking") or scene.get("blocking") or []
    declared_items = declared if isinstance(declared, list) else []
    by_key = {}
    for item in declared_items:
        if not isinstance(item, dict):
            continue
        for key in (item.get("id"), item.get("character_id"), item.get("name"), item.get("character")):
            if str(key or "").strip():
                by_key[str(key).strip()] = item

    participants = []
    unknowns = []
    for character_id, intent in intents.items():
        intent = intent if isinstance(intent, dict) else {}
        name = str(intent.get("name") or character_id)
        block = by_key.get(str(character_id)) or by_key.get(name)
        if block:
            # ``blocking`` is a legacy free-text spatial declaration.  It is
            # still evidence from the script, so retain it as the position
            # value instead of discarding it and manufacturing an unknown.
            position = str(block.get("position") or block.get("screen_position") or block.get("blocking") or "").strip()
            facing = str(block.get("facing") or block.get("screen_direction") or "").strip()
            anchor = str(block.get("anchor") or block.get("spatial_anchor") or "").strip()
        else:
            position = facing = anchor = ""
        if not position:
            unknowns.append(f"未声明 {name} 的画面位置")
        participants.append({
            "character_id": str(character_id), "name": name,
            "position": position or None, "facing": facing or None, "anchor": anchor or None,
            "source": "script_declared" if block else "missing",
        })

    beats = treatment.get("beat_map") if isinstance(treatment.get("beat_map"), list) else []
    transitions = []
    for index, beat in enumerate(beats):
        if not isinstance(beat, dict):
            continue
        transitions.append({
            "beat_id": str(beat.get("beat_id") or f"B{index + 1:02d}"),
            "event": str(beat.get("event") or ""),
            "blocking_change": "preserve_existing_spatial_relationship",
            "entry_state": "same_as_previous" if index else "scene_start",
            "exit_state": "same_as_next",
        })

    spatial_rules = [
        "locked_asset_identity_is_immutable",
        "do_not_change_screen_direction_without_declared_transition",
        "do_not_invent_character_position_when_script_is_silent",
        "carry_forward_unresolved_positions_to_shot_plan_review",
    ]
    payload = {
        "scene_name": scene_name,
        "participants": participants,
        "beat_transitions": transitions,
        "spatial_rules": spatial_rules,
        "unknowns": unknowns,
        "treatment_fingerprint": str(treatment.get("prompt_fingerprint") or ""),
        "source_script_hash": source_script_hash,
    }
    fingerprint = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return {**payload, "status": "needs_information" if unknowns else "ready_for_review", "evidence_fingerprint": fingerprint, "model_info": {"mode": "shadow_deterministic", "llm_called": False}}
