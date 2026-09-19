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


DIRECTOR_PLACEHOLDER_CODES = {
    "完成本场戏的叙事目标", "建立场景关系", "推进剧情", "建立冲突",
    "根据节拍调整", "保持自然", "完成本场", "推进当前叙事节拍",
}


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
            # These are source annotations, not new creative facts.  Keeping
            # them on the read-only projection lets Phase B coverage gates
            # bind every critical/reaction beat without creating an index ID.
            "beat_type": str(beat.get("beat_type") or beat_type).upper(),
            "objective": str(beat.get("objective") or ""),
            "characters": list(beat.get("characters") or []) if isinstance(beat.get("characters"), list) else [],
            "information_delta": str(beat.get("information_delta") or ""),
            "emotional_delta": str(beat.get("emotional_delta") or ""),
            "requires_reaction": bool(beat.get("requires_reaction", False)),
            "importance": str(beat.get("importance") or "normal"),
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


def _is_placeholder(value: Any) -> bool:
    text = str(value or "").strip()
    if not text or text in DIRECTOR_PLACEHOLDER_CODES:
        return True
    return any(token in text for token in ("完成本场戏的叙事目标", "根据节拍调整", "推进剧情"))


def validate_director_treatment_v2(treatment: dict[str, Any], *, scene: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate the Phase B directing contract without mutating the candidate.

    The legacy shadow contract remains intentionally permissive.  Callers opt
    into this validator for a production candidate and therefore get explicit,
    fail-closed reasons instead of a generic ``approved`` row.
    """
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if not isinstance(treatment, dict):
        return {"status": "blocked", "errors": [{"code": "DIRECTOR_TREATMENT_PLACEHOLDER", "message": "candidate is not an object"}], "warnings": []}
    required_text = {
        "scene_objective": "DIRECTOR_SCENE_OBJECTIVE_MISSING",
        "dramatic_question": "DIRECTOR_SCENE_OBJECTIVE_MISSING",
        "audience_state_in": "DIRECTOR_AUDIENCE_STATE_MISSING",
        "audience_state_out": "DIRECTOR_AUDIENCE_STATE_MISSING",
        "suspicion_or_information_strategy": "DIRECTOR_INFORMATION_STRATEGY_MISSING",
        "performance_arc": "DIRECTOR_PERFORMANCE_ARC_MISSING",
    }
    for field, code in required_text.items():
        value = treatment.get(field)
        missing = not value or (isinstance(value, str) and _is_placeholder(value))
        if missing:
            errors.append({"code": code, "field": field, "severity": "blocker", "message": f"{field} is missing or generic"})
    chars = treatment.get("character_directions")
    if not isinstance(chars, list) or not chars:
        errors.append({"code": "DIRECTOR_CHARACTER_DIRECTION_MISSING", "severity": "blocker", "message": "character_directions is empty"})
    else:
        for item in chars:
            if not isinstance(item, dict) or not all(str(item.get(k) or "").strip() for k in ("character", "objective", "obstacle", "strategy", "strategy_shift", "subtext", "performance_notes", "avoid")):
                errors.append({"code": "DIRECTOR_CHARACTER_DIRECTION_MISSING", "severity": "blocker", "message": "each character needs objective, obstacle, strategy, shift, subtext, performance_notes and avoid"})
                break
        if isinstance(scene, dict) and isinstance(scene.get("participants"), list):
            declared = {str((x.get("name") or x.get("character") or x.get("id")) if isinstance(x, dict) else x).strip() for x in scene["participants"]}
            directed_names = {str(x.get("character") or x.get("name") or "").strip() for x in chars if isinstance(x, dict)}
            missing_characters = sorted(x for x in declared if x and x not in directed_names)
            if missing_characters:
                errors.append({"code": "DIRECTOR_CHARACTER_DIRECTION_MISSING", "severity": "blocker", "missing": missing_characters, "message": "every declared participant needs a direction"})
    beats = scene.get("dramatic_beats") if isinstance(scene, dict) and isinstance(scene.get("dramatic_beats"), list) else scene.get("beats", []) if isinstance(scene, dict) else []
    critical = {str(b.get("beat_id")) for b in beats if isinstance(b, dict) and (str(b.get("importance", "")).lower() == "critical" or b.get("requires_reaction") is True)}
    directions = treatment.get("beat_directions") if isinstance(treatment.get("beat_directions"), list) else []
    directed = {str(item.get("beat_ref")) for item in directions if isinstance(item, dict)}
    missing_beats = sorted(critical - directed)
    if missing_beats:
        errors.append({"code": "DIRECTOR_BEAT_COVERAGE_INCOMPLETE", "severity": "blocker", "missing": missing_beats, "message": "critical/reaction beats lack director direction"})
    info = treatment.get("suspicion_or_information_strategy")
    if not isinstance(info, list) or not info or any(not isinstance(x, dict) or not x.get("information") for x in info):
        errors.append({"code": "DIRECTOR_INFORMATION_STRATEGY_MISSING", "severity": "blocker", "message": "ordered information strategy is missing"})
    if isinstance(treatment.get("performance_arc"), list) and len(treatment["performance_arc"]) < 2:
        errors.append({"code": "DIRECTOR_PERFORMANCE_ARC_MISSING", "severity": "blocker", "message": "performance arc needs at least an entry and exit state"})
    if _is_placeholder(treatment.get("scene_objective")):
        errors.append({"code": "DIRECTOR_TREATMENT_PLACEHOLDER", "severity": "blocker", "message": "scene objective is generic"})
    return {"status": "qualified" if not errors else "blocked", "errors": errors, "warnings": warnings, "blocker_count": len(errors), "warning_count": len(warnings), "critical_beat_count": len(critical), "covered_critical_beat_count": len(critical & directed)}


def build_director_treatment_v2(*, scene: dict[str, Any], characters: list[dict[str, Any]] | None = None, source_script_revision: str = "", source_script_hash: str = "", directives: dict[str, Any] | None = None, provider_not_called: bool = True) -> dict[str, Any]:
    """Build a materialized Phase B treatment on the existing payload shape.

    ``directives`` is a bounded, reviewed authoring input.  It may enrich
    directing decisions, but the source beat list and character identities are
    copied from ScriptIR and never replaced.
    """
    base = build_shadow_treatment(scene=scene, characters=characters, source_script_revision=source_script_revision)
    d = directives if isinstance(directives, dict) else {}
    base["scene_id"] = str(scene.get("scene_id") or scene.get("id") or "")
    base["scene_objective"] = str(d.get("scene_objective") or base.get("dramatic_objective") or "").strip()
    base["dramatic_question"] = str(d.get("dramatic_question") or base.get("audience_question") or "").strip()
    base["audience_state_in"] = str(d.get("audience_state_in") or "观众只掌握 ScriptIR 已声明的前置信息。")
    base["audience_state_out"] = str(d.get("audience_state_out") or "观众获得本场已声明的新信息，并保留未解决的问题。")
    base["suspicion_or_information_strategy"] = list(d.get("suspicion_or_information_strategy") or [{"order": i + 1, "beat_ref": b.get("beat_id"), "information": b.get("event"), "visibility": "BOTH_SEE", "audience_knows": True, "character_knows": b.get("characters", []), "withheld_from": [], "dramatic_effect": "让该节拍改变观众认知。"} for i, b in enumerate(base.get("beat_map", [])) if isinstance(b, dict) and b.get("event")])
    default_character_directions = []
    for item in characters or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("id") or "").strip()
        default_character_directions.append({"character": name, "objective": str(item.get("goal") or f"在本场具体行动中争取主动"), "obstacle": str(item.get("obstacle") or "对方行动与未公开信息"), "strategy": str(item.get("tactic") or "先观察，再以行动试探"), "strategy_shift": "根据关键揭示改变策略", "subtext": str(item.get("subtext") or "隐藏真实反应"), "performance_notes": "用可见行为和停顿表达变化，避免只演情绪标签。", "avoid": "不要预先知道尚未揭示的信息。"})
    base["character_directions"] = list(d.get("character_directions") or default_character_directions)
    critical = [b for b in base.get("beat_map", []) if isinstance(b, dict) and (str(b.get("importance", "")).lower() == "critical" or b.get("requires_reaction") is True)]
    base["beat_directions"] = list(d.get("beat_directions") or [{"beat_ref": b.get("beat_id"), "director_intent": f"让“{b.get('event')}”成为可表演的因果转折。", "performance_direction": "反应必须先于下一步行动，保留信息进入身体的时间。", "information_strategy": b.get("information_delta") or b.get("information_change") or "维持已声明信息边界。", "tempo": "hold_then_turn" if str(b.get("beat_type") or b.get("type")).upper() in {"REVEAL", "DECISION", "ESCALATION", "HOOK"} else "measured", "reaction_intent": "回应该节拍带来的信息或权力变化。" if b.get("requires_reaction") else "允许无反应停留。", "coverage_priority": "CRITICAL"} for b in critical])
    base["performance_arc"] = list(d.get("performance_arc") or [{"phase": "IN", "state": "带着前场状态进入"}, {"phase": "TURN", "state": "在关键揭示后改变策略"}, {"phase": "OUT", "state": "带着本场新问题离开"}])
    base["rhythm_strategy"] = d.get("rhythm_strategy") or {"opening": "建立可读空间", "reveal": "揭示前留反应停顿", "escalation": "缩短行动间隔但不跳过因果", "button": "把最后反应留给观众"}
    base["visual_priority"] = list(d.get("visual_priority") or ["人物可见反应", "关键道具状态", "人物与出口/障碍的空间关系"])
    base["scene_exit_intent"] = str(d.get("scene_exit_intent") or "让人物带着明确改变后的行动状态离开。")
    base["prohibited_interpretations"] = list(d.get("prohibited_interpretations") or ["不得把未揭示信息当成角色已知", "不得用镜头规格替代表演或空间决策"])
    base["source_script_hash"] = source_script_hash
    base["schema_version"] = "director_treatment_v2"
    base["provider_not_called"] = bool(provider_not_called)
    base["model_info"] = {"mode": "deterministic_phase_b_candidate", "llm_called": False, "provider_not_called": bool(provider_not_called), "provider_calls": 0, "repair_count": 0}
    base["validation"] = validate_director_treatment_v2(base, scene=scene)
    base["status"] = "ready_for_review" if base["validation"]["status"] == "qualified" else "blocked"
    base["prompt_fingerprint"] = hashlib.sha256(_canonical({k: v for k, v in base.items() if k not in {"prompt_fingerprint", "validation"}}).encode("utf-8")).hexdigest()
    base["candidate_fingerprint"] = hashlib.sha256(_canonical(base).encode("utf-8")).hexdigest()
    return base
