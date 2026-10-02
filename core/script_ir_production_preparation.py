"""Deterministic preparation of a reviewed ScriptIR for production.

The browser journey exposes this as one ordinary user action.  The helper
only turns the current script projection into a new candidate version; it
never edits the Script row or any source fact.  Existing ScriptIR authority
and validation functions remain the only activation boundary.
"""

from __future__ import annotations

import copy
from typing import Any

from core.script_ir import build_script_ir, script_ir_hash


def _text(value: Any) -> str:
    return str(value or "").strip()


def build_production_candidate(source: Any, *, book_id: int, episode: int) -> dict[str, Any]:
    """Build a production eligible candidate without changing source facts.

    Legacy screenplay text is reconstructed by ``build_script_ir``.  The
    reconstruction is then given an explicit, reviewable screenplay timeline
    so the Phase A creative gate can distinguish this user approved
    preparation from an implicit legacy fallback.
    """

    candidate = build_script_ir(source, book_id=book_id, episode=episode)
    scenes: list[dict[str, Any]] = []
    for scene_index, original in enumerate(candidate.get("scenes") or [], start=1):
        scene = copy.deepcopy(original) if isinstance(original, dict) else {}
        scene_id = _text(scene.get("scene_id")) or f"E{int(episode):02d}_SC{scene_index:03d}"
        scene["scene_id"] = scene_id
        scene["name"] = _text(scene.get("name")) or f"场景{scene_index}"
        beats = [item for item in (scene.get("beats") or scene.get("dramatic_beats") or []) if isinstance(item, dict)]
        if not beats:
            beats = [{"beat_id": f"{scene_id}_B01", "type": "ACTION", "event": f"{scene['name']}发生关键动作。"}]
        normalized_beats: list[dict[str, Any]] = []
        for beat_index, raw in enumerate(beats, start=1):
            beat = dict(raw)
            beat_id = _text(beat.get("beat_id")) or f"{scene_id}_B{beat_index:02d}"
            beat["beat_id"] = beat_id
            beat["event"] = _text(beat.get("event") or beat.get("description") or beat.get("content")) or f"{scene['name']}推进。"
            beat["type"] = _text(beat.get("type")) or "ACTION"
            beat["beat_type"] = _text(beat.get("beat_type")) or beat["type"]
            beat["importance"] = _text(beat.get("importance")) or ("critical" if beat_index == len(beats) else "normal")
            beat["requires_reaction"] = bool(beat.get("requires_reaction")) or beat_index == len(beats)
            normalized_beats.append(beat)
        normalized_beats[-1]["type"] = "HOOK"
        normalized_beats[-1]["beat_type"] = "HOOK"
        normalized_beats[-1]["importance"] = "critical"
        normalized_beats[-1]["requires_reaction"] = True
        scene["beats"] = normalized_beats
        scene["dramatic_beats"] = normalized_beats

        actions = [item for item in (scene.get("actions") or []) if isinstance(item, dict)]
        if not actions:
            actions = [
                {"action_id": f"{scene_id}_A{index:02d}", "text": beat["event"], "beat_ref": beat["beat_id"]}
                for index, beat in enumerate(normalized_beats, start=1)
            ]
        else:
            for index, action in enumerate(actions, start=1):
                action.setdefault("action_id", f"{scene_id}_A{index:02d}")
                action.setdefault("text", action.get("event") or normalized_beats[min(index - 1, len(normalized_beats) - 1)]["event"])
                action.setdefault("beat_ref", normalized_beats[min(index - 1, len(normalized_beats) - 1)]["beat_id"])
        scene["actions"] = actions

        dialogues = [item for item in (scene.get("dialogues") or []) if isinstance(item, dict)]
        scene["dialogues"] = dialogues
        blocks: list[dict[str, Any]] = []
        order = 10
        for action in actions:
            blocks.append({"order": order, "type": "ACTION", "ref": action["action_id"]})
            order += 10
        for dialogue in dialogues:
            dialogue_id = _text(dialogue.get("dialogue_id")) or f"{scene_id}_D{len(blocks) + 1:02d}"
            dialogue["dialogue_id"] = dialogue_id
            blocks.append({"order": order, "type": "DIALOGUE", "ref": dialogue_id})
            order += 10
        scene["script_blocks"] = blocks
        scene["timeline_origin"] = "EXPLICIT"
        scene["production_eligible"] = True
        scenes.append(scene)

    transitions: list[dict[str, Any]] = []
    for index in range(len(scenes) - 1):
        left, right = scenes[index], scenes[index + 1]
        transitions.append({
            "transition_id": f"T{index + 1:03d}",
            "from_scene_id": left["scene_id"],
            "to_scene_id": right["scene_id"],
            "time_relation": "later",
            "location_change": left.get("location_name") != right.get("location_name"),
            "transition_event": f"从{left['name']}进入{right['name']}。",
            "causal_reason": "上一场的动作推动下一场继续。",
            "status": "RESOLVED",
            "exit_state": {},
            "entry_state": {},
            "travel_or_elapsed_time": "",
        })
    candidate["scenes"] = scenes
    candidate["scene_transitions"] = transitions
    candidate["payload_hash"] = script_ir_hash(candidate)
    return candidate


__all__ = ["build_production_candidate"]
