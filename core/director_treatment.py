"""Deterministic DirectorTreatment shadow builder.

This module deliberately performs no model call and no database write.  It
turns a scene's beats plus declared character facts into a stable, reviewable
creative treatment.  A later LLM-assisted implementation can use this shape
as its evidence/validation contract without changing the shot pipeline.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _purpose(beat_type: str) -> str:
    return {
        "setup": "建立空间与人物关系",
        "obstacle": "建立阻碍",
        "decision": "形成决策与权力变化",
        "power_shift": "完成权力变化",
        "reveal": "揭示新信息",
        "action": "推进可见行动",
        "prop": "建立关键道具状态",
        "handoff": "完成道具或信息交接",
    }.get(beat_type, "推进当前叙事节拍")


def build_shadow_treatment(
    *,
    scene: dict[str, Any],
    characters: list[dict[str, Any]] | None = None,
    source_script_revision: str = "",
    skill_id: str = "",
    skill_version: str = "",
) -> dict[str, Any]:
    """Build a stable shadow treatment; never calls an external model."""

    scene_name = str(scene.get("name") or "未命名场景").strip()
    beats = scene.get("beats") or []
    if not isinstance(beats, list):
        beats = []

    beat_map: list[dict[str, Any]] = []
    for index, raw in enumerate(beats, start=1):
        beat = raw if isinstance(raw, dict) else {"event": str(raw)}
        # ScriptIR normalizes source beats to ``beat_id``.  Prefer that
        # canonical identifier (while retaining ``id`` for legacy callers) so
        # Treatment/SceneBlocking validation never invents a second ID space.
        beat_id = str(beat.get("beat_id") or beat.get("id") or f"B{index:02d}")
        beat_type = str(beat.get("type") or "setup").strip().lower()
        event = str(beat.get("event") or "").strip()
        beat_map.append({
            "beat_id": beat_id,
            "type": beat_type,
            "event": event,
            "dramatic_function": str(beat.get("dramatic_function") or _purpose(beat_type)),
            "information_change": str(beat.get("information_change") or ""),
            "emotion_change": str(beat.get("emotion_change") or ""),
        })

    intents: dict[str, dict[str, Any]] = {}
    for index, character in enumerate(characters or [], start=1):
        if not isinstance(character, dict):
            continue
        character_id = str(character.get("id") or character.get("asset_id") or character.get("name") or f"CHAR_{index:03d}")
        name = str(character.get("name") or character_id)
        intents[character_id] = {
            "name": name,
            "goal": str(character.get("goal") or "完成本场戏的叙事目标"),
            "obstacle": str(character.get("obstacle") or "场景中的对立力量或信息缺口"),
            "tactic": str(character.get("tactic") or "通过行动而非解释推进局面"),
            "subtext": str(character.get("subtext") or ""),
            "emotion_in": str(character.get("emotion_in") or "克制"),
            "emotion_out": str(character.get("emotion_out") or "变化中"),
            "power_in": character.get("power_in", 0.5),
            "power_out": character.get("power_out", 0.5),
        }

    events = [item["event"] for item in beat_map if item["event"]]
    first_event = events[0] if events else "建立场景关系"
    last_event = events[-1] if events else "完成当前节拍"
    has_reveal = any(item["type"] in {"reveal", "power_shift", "decision"} for item in beat_map)
    payload = {
        "scene_name": scene_name,
        "dramatic_objective": f"围绕“{first_event}”建立冲突，并通过“{last_event}”推进本场戏。",
        "audience_question": "人物最终会如何改变当前局面？" if not has_reveal else "新信息将如何改变观众对人物关系的判断？",
        "character_intents": intents,
        "beat_map": beat_map,
        "relationship_power_shift": "由节拍中的行动与决策呈现，不预设未声明的关系事实。",
        "audience_emotion": "从建立预期到产生变化，再留下下一步悬念。",
        "information_strategy": "只在 beat_map 声明的揭示节拍释放新信息，其余节拍维持已知事实。",
        "performance_direction": "以目标、阻碍和策略驱动表演，避免只标注单一情绪。",
        "visual_strategy": "优先呈现可观察的空间关系、动作节拍和关键道具状态。",
        "coverage_strategy": "先保证节拍与人物关系可见，再由后续 ShotPlan 决定具体覆盖。",
        "sound_strategy": "声音服务于节拍变化；未声明的对白、音乐和音效不作为事实写入。",
        "edit_rhythm": "按节拍强弱切换，信息揭示前保留反应空间。",
        "constraints": ["不得覆盖锁定资产事实", "不得把未声明内容伪装成剧本事实"],
        "unknowns": [],
        "source_script_revision": source_script_revision,
        "skill_id": skill_id,
        "skill_version": skill_version,
    }
    fingerprint = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return {**payload, "status": "draft", "prompt_fingerprint": fingerprint, "model_info": {"mode": "shadow_deterministic", "llm_called": False}}
