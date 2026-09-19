"""Shared ScriptIR payload builders for production integration tests.

These helpers construct the public authoring payload.  They do not mutate a
normalized ScriptIR or bypass authority/quality gates.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


def build_explicit_production_script_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a minimal, explicit screenplay payload for production tests.

    Existing actions/dialogues are retained.  A compact action is added only
    for a beat that has no visible action line, so the resulting timeline has
    real content coverage rather than an empty gate-shaped fixture.
    """
    result = deepcopy(payload)
    scenes = result.setdefault("scenes", [])
    for scene_index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            continue
        scene_id = str(scene.get("scene_id") or f"E01_SC{scene_index:03d}")
        scene["scene_id"] = scene_id
        beats = scene.setdefault("beats", [])
        actions = scene.setdefault("actions", [])
        dialogues = scene.setdefault("dialogues", [])
        for beat_index, beat in enumerate(beats, start=1):
            if not isinstance(beat, dict):
                beat = {"event": str(beat)}
                beats[beat_index - 1] = beat
            beat_id = str(beat.get("beat_id") or beat.get("id") or f"{scene_id}_B{beat_index:02d}")
            beat["beat_id"] = beat_id
            beat.setdefault("type", "ACTION")
            beat.setdefault("event", "场景动作。")
        if not beats and not actions and not dialogues:
            beats.append({"beat_id": f"{scene_id}_B01", "type": "ACTION", "event": "场景建立。"})
        if not any(str(beat.get("importance") or "").lower() == "critical" or beat.get("requires_reaction") for beat in beats if isinstance(beat, dict)):
            beats[0]["importance"] = "critical"
            beats[0]["requires_reaction"] = True
        last_type = str(beats[-1].get("type") or "").upper() if beats else ""
        if last_type not in {"HOOK", "ESCALATION", "REVERSAL", "TRANSITION"}:
            beats[-1]["type"] = "HOOK"
            beats[-1]["importance"] = "critical"
            beats[-1]["requires_reaction"] = True
        covered = {str(action.get("beat_ref")) for action in actions if isinstance(action, dict) and action.get("beat_ref")}
        for beat in beats:
            beat_id = str(beat["beat_id"])
            if beat_id in covered:
                continue
            action_id = f"{scene_id}_A{len(actions) + 1:03d}"
            actions.append({"action_id": action_id, "text": str(beat.get("event") or "场景动作。"), "beat_ref": beat_id})
            covered.add(beat_id)
        normalized_actions = []
        for index, action in enumerate(actions, start=1):
            if isinstance(action, str):
                action = {"text": action}
            action = dict(action)
            action.setdefault("action_id", f"{scene_id}_A{index:03d}")
            action.setdefault("text", "场景动作。")
            normalized_actions.append(action)
        scene["actions"] = normalized_actions
        blocks: list[dict[str, Any]] = []
        order = 10
        dialogue_index = 0
        for action in normalized_actions:
            block = {"order": order, "type": "ACTION", "ref": action["action_id"]}
            if action.get("beat_ref"):
                block["beat_refs"] = [action["beat_ref"]]
            blocks.append(block)
            order += 10
            if dialogue_index < len(dialogues):
                dialogue = dialogues[dialogue_index]
                dialogue_id = str(dialogue.get("dialogue_id") or dialogue.get("id") or f"{scene_id}_D{dialogue_index + 1:03d}")
                dialogue["dialogue_id"] = dialogue_id
                blocks.append({"order": order, "type": "DIALOGUE", "ref": dialogue_id})
                order += 10
                dialogue_index += 1
        while dialogue_index < len(dialogues):
            dialogue = dialogues[dialogue_index]
            dialogue_id = str(dialogue.get("dialogue_id") or dialogue.get("id") or f"{scene_id}_D{dialogue_index + 1:03d}")
            dialogue["dialogue_id"] = dialogue_id
            blocks.append({"order": order, "type": "DIALOGUE", "ref": dialogue_id})
            order += 10
            dialogue_index += 1
        scene["script_blocks"] = blocks
        scene["timeline_origin"] = "EXPLICIT"
    return result
