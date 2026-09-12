"""Human-readable Markdown renderer for ScriptIR."""
from __future__ import annotations

from typing import Any


def render_script_markdown(script_ir: dict[str, Any]) -> str:
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
