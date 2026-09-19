"""Script renderers.

Two renderers are provided:

* ``render_reader_script`` — the professional screenplay a user reads.
  No camera direction, no internal engineering labels, no beat_id/fact refs.
* ``render_technical_script_view`` — the advanced engineering view with
  beat_id, fact refs, knowledge state and transition contracts.

``render_script_markdown`` is kept as a thin, backward-compatible alias of
the reader script (old callers/tests keep working).
"""
from __future__ import annotations

import re
from typing import Any


def _text(value: Any) -> str:
    return str(value or "").strip()


def _clean_action(value: Any) -> str:
    """Strip camera-direction and internal engineering labels from action."""
    text = _text(value)
    for pattern in (
        "【视觉证明", "【隐藏层", "【强钩子", "【开场", "【冲突引入",
        "【场景结束", "【场景开始", "【重试要求",
    ):
        text = text.replace(pattern, "")
    return text.strip()


def _render_scene_header(scene: dict[str, Any], index: int) -> list[str]:
    name = _text(scene.get("name")) or f"场景{index}"
    location = _text(scene.get("location_name"))
    time_of_day = _text(scene.get("time_of_day"))
    # Extract location/time from the raw name when structured fields are absent.
    if not location and "—" in name:
        parts = [p.strip() for p in name.split("—")]
        name = parts[0]
        location = parts[1] if len(parts) > 1 else ""
        time_of_day = parts[2] if len(parts) > 2 else time_of_day
    header = f"场{index}  {name}"
    if location and location != name:
        header += f"  {location}"
    header += f"  {time_of_day} / 内" if time_of_day else ""
    return [header, ""]


def render_reader_script(script_ir: dict[str, Any]) -> str:
    """Professional screenplay for a human reader.

    Renders strictly in ``scene.script_blocks`` order: ACTION blocks resolve
    the referenced action/beat text, DIALOGUE blocks resolve the referenced
    dialogue.  It never emits episode objective, beat ids, dialogue ids,
    assertion modes, camera direction or internal engineering labels.
    """
    title = _text(script_ir.get("title")) or f"第{_text(script_ir.get('episode')) or 1}集"
    lines = [f"# {title}", ""]
    for index, scene in enumerate(script_ir.get("scenes") or [], start=1):
        if not isinstance(scene, dict):
            continue
        lines.extend(_render_scene_header(scene, index))
        # Build content indexes.
        actions_by_id = {}
        for action in scene.get("actions") or []:
            if isinstance(action, dict) and _text(action.get("action_id")):
                actions_by_id[_text(action["action_id"])] = action
        beats_by_id = {}
        for beat in scene.get("dramatic_beats") or scene.get("beats") or []:
            if isinstance(beat, dict) and _text(beat.get("beat_id")):
                beats_by_id[_text(beat["beat_id"])] = beat
        dialogues_by_id = {}
        for dialogue in scene.get("dialogues") or []:
            if isinstance(dialogue, dict) and _text(dialogue.get("dialogue_id")):
                dialogues_by_id[_text(dialogue["dialogue_id"])] = dialogue
        blocks = [b for b in (scene.get("script_blocks") or []) if isinstance(b, dict)]
        if not blocks:
            # Deterministic fallback when no explicit timeline exists.
            blocks = _fallback_blocks(scene)
        for block in sorted(blocks, key=lambda item: _order_key(item)):
            block_type = _text(block.get("type")).upper()
            ref = _text(block.get("ref"))
            if block_type == "ACTION":
                content = ""
                if ref:
                    action = actions_by_id.get(ref)
                    if action is not None:
                        content = _clean_action(action.get("text"))
                    else:
                        beat = beats_by_id.get(ref)
                        if beat is not None:
                            content = _clean_action(beat.get("event"))
                elif "action_id" in block:
                    action = actions_by_id.get(_text(block.get("action_id")))
                    if action is not None:
                        content = _clean_action(action.get("text"))
                if content:
                    lines.append(content)
                    lines.append("")
            elif block_type == "DIALOGUE":
                dialogue = dialogues_by_id.get(ref) if ref else None
                if dialogue is None and ref:
                    dialogue = next((d for d in (scene.get("dialogues") or []) if isinstance(d, dict) and _text(d.get("id")) == ref), None)
                if dialogue is not None:
                    speaker = _text(dialogue.get("speaker")) or "角色"
                    parenthetical = _text(dialogue.get("parenthetical"))
                    text = _text(dialogue.get("text") or dialogue.get("content"))
                    if text:
                        if parenthetical:
                            lines.append(f"**{speaker}**（{parenthetical}）")
                        else:
                            lines.append(f"**{speaker}**")
                        lines.append(text)
                        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _order_key(block: dict[str, Any]) -> tuple[int, int]:
    order = block.get("order")
    if isinstance(order, int) and not isinstance(order, bool):
        return (int(order), 0)
    raw = _text(block.get("order"))
    try:
        return (int(float(raw)), 0)
    except (TypeError, ValueError):
        return (10**9, 0)


def _fallback_blocks(scene: dict[str, Any]) -> list[dict[str, Any]]:
    """Deterministic interleave fallback for payloads without script_blocks."""
    actions = [a for a in (scene.get("actions") or []) if isinstance(a, dict) and _text(a.get("action_id"))]
    beats = [b for b in (scene.get("dramatic_beats") or scene.get("beats") or []) if isinstance(b, dict) and _text(b.get("beat_id"))]
    dialogues = [d for d in (scene.get("dialogues") or []) if isinstance(d, dict) and _text(d.get("dialogue_id"))]
    action_sources = actions if actions else beats
    blocks: list[dict[str, Any]] = []
    order = 10
    max_len = max(len(action_sources), len(dialogues))
    for index in range(max_len):
        if index < len(action_sources):
            blocks.append({"order": order, "type": "ACTION", "ref": _text(action_sources[index].get("action_id") or action_sources[index].get("beat_id"))})
            order += 10
        if index < len(dialogues):
            blocks.append({"order": order, "type": "DIALOGUE", "ref": _text(dialogues[index].get("dialogue_id"))})
            order += 10
    return blocks


def render_technical_script_view(script_ir: dict[str, Any]) -> str:
    """Advanced engineering view: beats, fact refs, knowledge state,
    transition contracts.
    """
    title = _text(script_ir.get("title")) or f"第{_text(script_ir.get('episode')) or 1}集"
    lines = [f"# {title}（技术视图）", ""]
    for index, scene in enumerate(script_ir.get("scenes") or [], start=1):
        if not isinstance(scene, dict):
            continue
        scene_id = _text(scene.get("scene_id")) or f"SC{index:02d}"
        lines.append(f"## {scene_id}  {_text(scene.get('name')) or f'场景{index}'}")
        lines.append("")
        beats = scene.get("dramatic_beats") or scene.get("beats") or []
        for beat in beats:
            if not isinstance(beat, dict):
                continue
            beat_id = _text(beat.get("beat_id"))
            beat_type = _text(beat.get("beat_type") or beat.get("type"))
            event = _text(beat.get("event"))
            importance = _text(beat.get("importance")) or "normal"
            requires_reaction = beat.get("requires_reaction")
            lines.append(f"- `{beat_id}` [{beat_type}] importance={importance} requires_reaction={requires_reaction}")
            if event:
                lines.append(f"    {event}")
            objective = _text(beat.get("objective"))
            if objective:
                lines.append(f"    objective={objective}")
            info_delta = _text(beat.get("information_delta"))
            if info_delta:
                lines.append(f"    info_delta={info_delta}")
            emotion_delta = _text(beat.get("emotional_delta"))
            if emotion_delta:
                lines.append(f"    emotion_delta={emotion_delta}")
        for dialogue in scene.get("dialogues") or []:
            if not isinstance(dialogue, dict):
                continue
            dialogue_id = _text(dialogue.get("dialogue_id"))
            speaker = _text(dialogue.get("speaker"))
            text = _text(dialogue.get("text") or dialogue.get("content"))
            mode = _text(dialogue.get("assertion_mode")) or "OBJECTIVE_FACT"
            contradicts = dialogue.get("contradicts_fact_refs") or []
            notice = dialogue.get("audience_should_notice")
            lines.append(f"- `{dialogue_id}` **{speaker}** [{mode}] contradicts={contradicts} notice={notice}")
            if text:
                lines.append(f"    {text}")
        lines.append("")
    transitions = script_ir.get("scene_transitions") or []
    if transitions:
        lines.append("## SceneTransitionContracts")
        lines.append("")
        for transition in transitions:
            if not isinstance(transition, dict):
                continue
            lines.append(f"- `{_text(transition.get('from_scene_id'))}` → `{_text(transition.get('to_scene_id'))}` [{_text(transition.get('status'))}] time={_text(transition.get('time_relation'))} location_change={transition.get('location_change')}")
            if _text(transition.get("transition_event")):
                lines.append(f"    event={_text(transition.get('transition_event'))}")
            if _text(transition.get("causal_reason")):
                lines.append(f"    causal={_text(transition.get('causal_reason'))}")
            if _text(transition.get("travel_or_elapsed_time")):
                lines.append(f"    elapsed={_text(transition.get('travel_or_elapsed_time'))}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def render_script_markdown(script_ir: dict[str, Any]) -> str:
    """Backward-compatible legacy renderer.

    Kept byte-for-byte stable so existing callers/tests that rely on the old
    ``## 场景 N：name`` format keep working.  Production readers should use
    ``render_reader_script`` / ``render_technical_script_view`` instead.
    """
    title = str(script_ir.get("title") or f"第{script_ir.get('episode', 1)}集").strip()
    lines = [f"# {title}", ""]
    objective = str(script_ir.get("episode_objective") or "").strip()
    if objective:
        lines.extend([f"**本集目标**：{objective}", ""])
    for index, scene in enumerate(script_ir.get("scenes") or [], start=1):
        if not isinstance(scene, dict):
            continue
        name = str(scene.get("name") or f"场景{index}").strip()
        location = str(scene.get("location_name") or "").strip()
        suffix = f"（{location}）" if location and location != name else ""
        lines.extend([f"## 场景 {index}：{name}{suffix}", ""])
        for beat in scene.get("beats") or []:
            if isinstance(beat, dict) and str(beat.get("event") or "").strip():
                lines.append(f"- {str(beat['event']).strip()}")
        for dialogue in scene.get("dialogues") or []:
            if isinstance(dialogue, dict):
                speaker = str(dialogue.get("speaker") or "角色").strip()
                text = str(dialogue.get("text") or dialogue.get("content") or "").strip()
                if text:
                    lines.append(f"- **{speaker}**：{text}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"
