"""Deterministic, evidence-backed creative opportunity detection.

The detector answers *where a director may have a meaningful choice*; it does
not decide the shot, mutate approved evidence, or call an LLM.  Every emitted
record carries a source reference and is validated by the shared opportunity
model before it leaves this module.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Iterable

from core.director_opportunity_model import (
    DIRECTING_DIMENSIONS,
    OPPORTUNITY_TYPES,
    OpportunityModelError,
    normalize_opportunity,
)


class OpportunityDetectionError(ValueError):
    """Raised when approved evidence cannot be inspected safely."""


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _first_text(*values: Any) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def _beat_id(value: dict[str, Any], index: int) -> str:
    return _first_text(value.get("beat_id"), value.get("id")) or f"B{index + 1:02d}"


def _beat_entries(script_scene: dict[str, Any], treatment: dict[str, Any]) -> list[tuple[str, dict[str, Any], str]]:
    """Merge approved beat sources and retain a human-auditable source path."""

    result: list[tuple[str, dict[str, Any], str]] = []
    seen: set[str] = set()
    for source_name, source in (("treatment", treatment), ("script_scene", script_scene)):
        beats = source.get("beat_map")
        path_name = "beat_map"
        if not isinstance(beats, list):
            beats = source.get("beats")
            path_name = "beats"
        for index, item in enumerate(_list(beats)):
            if not isinstance(item, dict):
                continue
            beat_id = _beat_id(item, index)
            if beat_id in seen:
                continue
            seen.add(beat_id)
            result.append((beat_id, copy.deepcopy(item), f"{source_name}.{path_name}[{index}].beat_id"))
    return result


def _participants(value: Any) -> list[str]:
    result: list[str] = []
    for item in _list(value):
        if isinstance(item, dict):
            item = _first_text(item.get("character_id"), item.get("id"), item.get("name"), item.get("character"))
        else:
            item = _text(item)
        if item and item not in result:
            result.append(item)
    return result


def _beat_participants(beat: dict[str, Any], shot: dict[str, Any]) -> list[str]:
    return _participants(beat.get("participants") or beat.get("characters") or shot.get("participants"))


def _shots_by_beat(structural_shot_plan: dict[str, Any]) -> dict[str, list[tuple[int, dict[str, Any]]]]:
    result: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for index, shot in enumerate(_list(structural_shot_plan.get("shots"))):
        if not isinstance(shot, dict):
            continue
        beat_id = _text(shot.get("beat_id"))
        if beat_id:
            result.setdefault(beat_id, []).append((index, shot))
    return result


def _scene_id(script_scene: dict[str, Any], treatment: dict[str, Any], blocking: dict[str, Any], plan: dict[str, Any]) -> str:
    return _first_text(script_scene.get("scene_id"), treatment.get("scene_id"), blocking.get("scene_id"), plan.get("scene_id"), treatment.get("scene_name"), plan.get("scene_name"))


def _declared_type(beat: dict[str, Any]) -> str:
    return _text(beat.get("type")).lower().replace("-", "_").replace(" ", "_")


def _search_text(beat: dict[str, Any], shot: dict[str, Any]) -> str:
    values: list[str] = []
    for source in (beat, shot):
        for key in ("event", "description", "content", "dramatic_function", "emotion_change", "information_change", "dialogue", "action"):
            value = source.get(key)
            if isinstance(value, list):
                values.extend(_text(item) for item in value)
            else:
                values.append(_text(value))
    return " ".join(values).lower()


def _has_any(text: str, tokens: Iterable[str]) -> bool:
    return any(token.lower() in text for token in tokens)


def _duration(shot: dict[str, Any]) -> float | None:
    value = _dict(shot.get("edit")).get("duration_seconds", shot.get("duration_hint_seconds"))
    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) <= 0:
        return None
    return float(value)


def _beat_field_ref(beat_ref: str, field: str) -> str:
    """Turn the canonical beat identity ref into an exact field ref."""

    base = _text(beat_ref)
    if base.endswith(".beat_id"):
        base = base[: -len(".beat_id")]
    return f"{base}.{field}" if base else field


def _first_present_field(source: dict[str, Any], fields: Iterable[str]) -> str:
    for field in fields:
        if field in source and source.get(field) not in (None, "", [], {}):
            return field
    return ""


def _explicit_presence_signal(beat: dict[str, Any], blocking: dict[str, Any], *, entering: bool) -> tuple[bool, str]:
    fields = ("entry", "entry_state", "entrance", "entered", "presence_in") if entering else ("exit", "exit_state", "exits", "exited", "presence_out")
    field = _first_present_field(beat, fields)
    if field:
        return True, field
    field = _first_present_field(blocking, fields)
    if field:
        return True, f"blocking.{field}"
    text = _search_text(beat, {})
    tokens = ("enter", "arrive", "进入", "出现") if entering else ("exit", "leave", "depart", "离开", "退场")
    return any(token in text for token in tokens), "event"


def _dialogue_pressure_fields(beat: dict[str, Any], shot: dict[str, Any]) -> list[str]:
    fields = ("conflict", "conflict_escalation", "interruption", "dominance_change", "pressure", "subtext_tension", "power_shift")
    result = [field for field in fields if beat.get(field) not in (None, "", [], {})]
    if result:
        return result
    text = _search_text(beat, shot)
    tokens = ("conflict", "interruption", "dominance", "pressure", "subtext", "confrontation", "对峙", "冲突", "打断", "压迫", "逼问", "质问", "权力", "潜台词")
    return ["event"] if any(token in text for token in tokens) else []


def _scene_button_field(beat: dict[str, Any], script_scene: dict[str, Any], treatment: dict[str, Any]) -> str:
    field = _first_present_field(beat, ("scene_button", "button", "plot_result", "ending", "release", "cliffhanger", "reaction_hold", "visual_punctuation", "transition"))
    if field:
        return f"beat.{field}"
    if _dict(script_scene.get("state_out")):
        return "script_scene.state_out"
    if _dict(treatment.get("state_out")):
        return "treatment.state_out"
    return ""


_DIMENSIONS: dict[str, list[str]] = {
    "OPP_EMOTION_TURN": ["emotion_arc", "performance_direction"],
    "OPP_REACTION": ["performance_direction", "edit_strategy", "shot_motivation"],
    "OPP_INFORMATION_WITHHOLD": ["information_strategy", "edit_strategy"],
    "OPP_INFORMATION_REVEAL": ["information_strategy", "edit_strategy", "performance_direction"],
    "OPP_POWER_SHIFT": ["power_dynamics", "camera_language", "performance_direction"],
    "OPP_RHYTHM_CHANGE": ["edit_strategy", "shot_diversity"],
    "OPP_PROP_EMPHASIS": ["information_strategy", "visual_storytelling", "shot_motivation"],
    "OPP_SPATIAL_ISOLATION": ["spatial_clarity", "camera_language", "shot_motivation"],
    "OPP_CHARACTER_ENTRANCE": ["shot_motivation", "spatial_clarity", "edit_strategy"],
    "OPP_CHARACTER_EXIT": ["shot_motivation", "spatial_clarity", "edit_strategy"],
    "OPP_VISUAL_REVEAL": ["visual_storytelling", "camera_language", "information_strategy"],
    "OPP_SILENCE_HOLD": ["edit_strategy", "performance_direction", "emotion_arc"],
    "OPP_DIALOGUE_PRESSURE": ["performance_direction", "edit_strategy", "power_dynamics"],
    "OPP_ACTION_ACCELERATION": ["edit_strategy", "camera_language", "performance_direction"],
    "OPP_SCENE_BUTTON": ["edit_strategy", "visual_storytelling", "shot_motivation"],
}


def _priority(opportunity_type: str, beat: dict[str, Any]) -> str:
    if opportunity_type in {"OPP_INFORMATION_REVEAL", "OPP_POWER_SHIFT", "OPP_EMOTION_TURN", "OPP_SCENE_BUTTON"}:
        return "high"
    if opportunity_type in {"OPP_REACTION", "OPP_INFORMATION_WITHHOLD", "OPP_CHARACTER_ENTRANCE", "OPP_CHARACTER_EXIT", "OPP_VISUAL_REVEAL"}:
        return "medium"
    return "low" if _declared_type(beat) in {"setup", "establishing", "coverage"} else "medium"


def _slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", value.upper()).strip("_")
    return value or "BEAT"


def _candidate(
    *,
    scene_id: str,
    beat_id: str,
    beat: dict[str, Any],
    shot: dict[str, Any],
    opportunity_type: str,
    reason: str,
    refs: list[str],
    subjects: list[str],
) -> dict[str, Any]:
    if opportunity_type not in OPPORTUNITY_TYPES:
        raise OpportunityDetectionError(f"unsupported detector opportunity type: {opportunity_type}")
    if not refs:
        raise OpportunityDetectionError(f"opportunity {opportunity_type} has no evidence")
    return normalize_opportunity(
        {
            "opportunity_id": f"OPP_{_slug(beat_id)}_{opportunity_type.removeprefix('OPP_')}",
            "type": opportunity_type,
            "scene_id": scene_id,
            "beat_id": beat_id,
            "subjects": subjects,
            "reason": reason,
            "evidence_refs": refs,
            "priority": _priority(opportunity_type, beat),
            "eligible": True,
            "recommended_directing_dimensions": [item for item in _DIMENSIONS[opportunity_type] if item in DIRECTING_DIMENSIONS],
        }
    )


def detect_creative_opportunities(
    *,
    script_scene: dict[str, Any] | None = None,
    treatment: dict[str, Any] | None = None,
    blocking: dict[str, Any] | None = None,
    structural_shot_plan: dict[str, Any] | None = None,
    fact_snapshot: dict[str, Any] | None = None,
    scene_canonical: dict[str, Any] | None = None,
    previous_scene_continuity: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Detect only opportunities supported by approved scene evidence.

    Optional evidence is read-only and may be absent.  Absence suppresses a
    rule; it never causes the detector to invent a subject, event, or asset.
    """

    script = _dict(script_scene)
    treatment_obj = _dict(treatment)
    blocking_obj = _dict(blocking)
    plan = _dict(structural_shot_plan)
    scene_id = _scene_id(script, treatment_obj, blocking_obj, plan)
    if not scene_id:
        raise OpportunityDetectionError("scene_id is required to emit opportunities")
    beats = _beat_entries(script, treatment_obj)
    if not beats:
        return []
    shots = _shots_by_beat(plan)
    scene_participants = _participants(blocking_obj.get("participants") or script.get("participants") or treatment_obj.get("participants"))
    result: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    previous_participants: set[str] = set()
    previous_duration: float | None = None
    for index, (beat_id, beat, beat_ref) in enumerate(beats):
        beat_shots = shots.get(beat_id, [])
        shot = beat_shots[0][1] if beat_shots else {}
        shot_index = beat_shots[0][0] if beat_shots else index
        subjects = _beat_participants(beat, shot)
        if not subjects and len(scene_participants) == 1:
            subjects = scene_participants.copy()
        text = _search_text(beat, shot)
        declared = _declared_type(beat)
        refs_base = [beat_ref]
        if beat_shots:
            refs_base.append(f"structural_shot_plan.shots[{shot_index}].beat_id")
        info_field = _first_present_field(beat, ("information_change", "reveal", "reveals"))
        info_change = _text(beat.get(info_field))
        emotion_field = _first_present_field(beat, ("emotion_change", "emotion_turn", "emotional_shift"))
        emotion_change = _text(beat.get(emotion_field))
        dialogue = _first_text(beat.get("dialogue"), shot.get("dialogue"))
        duration = _duration(shot)
        candidates: list[tuple[str, str, list[str]]] = []
        if emotion_change or declared in {"reaction", "emotional_peak", "emotion_turn", "turn", "decision", "power_shift"}:
            candidates.append(("OPP_EMOTION_TURN", "节拍证据声明了可观察的情绪状态变化窗口", refs_base + ([_beat_field_ref(beat_ref, emotion_field)] if emotion_field else [])))
        if declared in {"reaction", "dialogue_turn", "reveal", "decision", "power_shift"} or _has_any(text, ("reaction", "反应", "获知", "听到", "看到", "得知")):
            candidates.append(("OPP_REACTION", "节拍或动作证据表明信息/行动之后存在可观察反应窗口", refs_base))
        withhold_field = _first_present_field(beat, ("withhold", "withholds", "audience_should_not_know_yet"))
        if withhold_field or declared in {"mystery", "withhold", "suspense"}:
            candidates.append(("OPP_INFORMATION_WITHHOLD", "已批准证据声明信息需要延后或保持未知", refs_base + ([_beat_field_ref(beat_ref, withhold_field)] if withhold_field else [])))
        if info_change or declared in {"reveal", "visual_reveal", "information_reveal"}:
            candidates.append(("OPP_INFORMATION_REVEAL", "已批准节拍声明了新的信息变化或揭示触发点", refs_base + ([_beat_field_ref(beat_ref, info_field)] if info_field else [])))
        if declared in {"power_shift", "decision", "confrontation"} or _has_any(text, ("power shift", "权力", "压制", "反转", "对峙")):
            candidates.append(("OPP_POWER_SHIFT", "节拍类型或戏剧功能声明了人物关系/权力变化", refs_base))
        if declared in {"action", "obstacle", "chase", "reveal", "decision", "reaction"} and previous_duration is not None and duration is not None and abs(duration - previous_duration) >= 0.75:
            candidates.append(("OPP_RHYTHM_CHANGE", "相邻已批准镜头时长出现可测变化，存在节奏决策窗口", refs_base + [f"structural_shot_plan.shots[{shot_index}].duration_hint_seconds"]))
        bindings = _dict(shot.get("asset_bindings"))
        props = _list(bindings.get("prop_asset_ids") or bindings.get("props"))
        if props and (declared in {"prop", "handoff", "reveal", "action"} or _has_any(text, ("prop", "道具", "交接", "拿出", "放下", "钥匙", "照片"))):
            candidates.append(("OPP_PROP_EMPHASIS", "镜头绑定了已批准道具且节拍要求关注其状态或动作", refs_base + [f"structural_shot_plan.shots[{shot_index}].asset_bindings.prop_asset_ids"]))
        frame = _dict(_dict(shot.get("composition")))
        if (len(subjects) == 1 and len(scene_participants) > 1) or _text(frame.get("frame_relationship")).lower() in {"isolated", "single_subject"}:
            candidates.append(("OPP_SPATIAL_ISOLATION", "参与者/构图证据显示单一主体被从群体空间中隔离", refs_base + ([f"structural_shot_plan.shots[{shot_index}].composition.frame_relationship"] if frame else [])))
        current_participants = set(subjects)
        entered = sorted(current_participants - previous_participants) if previous_participants else []
        exited = sorted(previous_participants - current_participants) if previous_participants else []
        has_entry, entry_field = _explicit_presence_signal(beat, blocking_obj, entering=True)
        has_exit, exit_field = _explicit_presence_signal(beat, blocking_obj, entering=False)
        if entered and index > 0 and has_entry:
            candidates.append(("OPP_CHARACTER_ENTRANCE", "明确的入场/出现证据与参与者变化共同形成呈现窗口", refs_base + [_beat_field_ref(beat_ref, entry_field) if not entry_field.startswith("blocking.") else entry_field]))
        if exited and index > 0 and has_exit:
            candidates.append(("OPP_CHARACTER_EXIT", "明确的离场/退场证据与参与者变化共同形成呈现窗口", refs_base + [_beat_field_ref(beat_ref, exit_field) if not exit_field.startswith("blocking.") else exit_field]))
        if declared in {"reveal", "visual_reveal", "discovery"} or _has_any(text, ("visual reveal", "视觉揭示", "发现", "看见")):
            candidates.append(("OPP_VISUAL_REVEAL", "节拍证据要求观众通过画面发现或看见新的视觉事实", refs_base))
        if _has_any(text, ("silence", "pause", "沉默", "停顿", "无对白")) or (not dialogue and declared in {"hold", "silence", "reaction"}):
            candidates.append(("OPP_SILENCE_HOLD", "对白/节拍证据形成可观察的静默或停顿保持窗口", refs_base + [_beat_field_ref(beat_ref, "dialogue")]))
        pressure_fields = _dialogue_pressure_fields(beat, shot)
        if dialogue and pressure_fields:
            candidates.append(("OPP_DIALOGUE_PRESSURE", "节拍含有对白及对话对抗证据，存在表演/剪辑压力选择", refs_base + [_beat_field_ref(beat_ref, "dialogue")] + [_beat_field_ref(beat_ref, field) for field in pressure_fields if field != "event"]))
        if declared in {"action", "chase", "acceleration"} or _has_any(text, ("accelerate", "加速", "冲", "追逐")):
            candidates.append(("OPP_ACTION_ACCELERATION", "节拍类型或动作证据要求更快的动作呈现与剪辑节奏", refs_base))
        scene_button_field = _scene_button_field(beat, script, treatment_obj)
        if index == len(beats) - 1 and scene_button_field:
            candidates.append(("OPP_SCENE_BUTTON", "场景末拍存在已批准的状态/结果落点，需决定收束方式", refs_base + [scene_button_field]))
        for opportunity_type, reason, refs in candidates:
            opportunity = _candidate(scene_id=scene_id, beat_id=beat_id, beat=beat, shot=shot, opportunity_type=opportunity_type, reason=reason, refs=refs, subjects=subjects)
            if opportunity["opportunity_id"] not in seen_ids:
                seen_ids.add(opportunity["opportunity_id"])
                result.append(opportunity)
        previous_participants = current_participants
        previous_duration = duration if duration is not None else previous_duration
    return result


# Naming aliases used by callers and future integration tests.
build_creative_opportunities = detect_creative_opportunities
detect_directing_opportunities = detect_creative_opportunities


__all__ = [
    "OpportunityDetectionError",
    "detect_creative_opportunities",
    "build_creative_opportunities",
    "detect_directing_opportunities",
]
