"""Asset, keyframe, and timecoded motion prompt production.

The renderer consumes canonical asset records and a shot performance plan. It
does not invent screenplay facts or contain fixture-specific names.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any


ASSET_RENDERER_VERSION = "asset_prompt_renderer_v3"
KEYFRAME_RENDERER_VERSION = "shot_keyframe_renderer_v3"
VIDEO_RENDERER_VERSION = "timecoded_video_renderer_v3"
GENERIC_PATTERNS = ("自然反应", "克制表演", "保持稳定", "完成信息传递", "动作简洁真实")
INTERNAL_TOKEN_RE = re.compile(r"(?:action_id|beat_ref|event_ref|axis_ref|projection_origin|asset_identity_ref|schema_version|shot_plan|prompt_ir|[A-Z][A-Z0-9_]{3,})")


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


@dataclass
class AssetPromptIR:
    asset_type: str
    identity: str
    fields: dict[str, Any]
    asset_prompt_ir: dict[str, Any]
    provider_prompt: str
    negative_prompt: str
    reference_policy: dict[str, Any]
    renderer_version: str
    fingerprint: str
    readiness: str


@dataclass
class ShotPerformancePlan:
    shot_id: str
    duration: float
    characters: list[dict[str, Any]]
    dialogue: list[dict[str, Any]]
    emotion_arc: list[dict[str, Any]]
    body_movement: list[dict[str, Any]]
    hand_movement: list[dict[str, Any]]
    head_movement: list[dict[str, Any]]
    eye_movement: list[dict[str, Any]]
    facial_changes: list[dict[str, Any]]
    interaction_beats: list[dict[str, Any]]
    prop_interaction: list[dict[str, Any]]
    camera_movement: list[dict[str, Any]]
    ending_pose: dict[str, Any]


@dataclass
class TimecodedMotionIR:
    shot_id: str
    duration: float
    segments: list[dict[str, Any]]
    dialogue_audio_generated: bool
    renderer_version: str = VIDEO_RENDERER_VERSION


def _asset_prompt(asset_type: str, identity: str, fields: dict[str, Any]) -> AssetPromptIR:
    required = fields.get("required_fields", [])
    missing = [name for name in required if not _text(fields.get(name))]
    if missing:
        return AssetPromptIR(asset_type, identity, fields, {"status": "ASSET_PROMPT_NOT_READY", "missing": missing}, "", "", {"status": "BLOCKED"}, ASSET_RENDERER_VERSION, fingerprint({"asset_type": asset_type, "identity": identity, "fields": fields}), "ASSET_PROMPT_NOT_READY")
    ordered = [(key, value) for key, value in fields.items() if key != "required_fields" and _text(value)]
    prose = "；".join(f"{key}：{value}" for key, value in ordered)
    negative = _text(fields.get("negative_prompt") or "避免身份漂移、比例变化、错误材质、文字水印、过度风格化")
    prompt_ir = {"asset_type": asset_type, "identity": identity, "fields": fields, "source": fields.get("source", "CANONICAL_ASSET_AUTHORITY")}
    projection = {"prompt": prose, "negative_prompt": negative, "reference_policy": {"mode": "LOCKED_CANONICAL_REFERENCE", "status": "LOCKED", "stale_status": "FRESH"}, "renderer_version": ASSET_RENDERER_VERSION}
    return AssetPromptIR(asset_type, identity, fields, prompt_ir, prose, negative, projection["reference_policy"], ASSET_RENDERER_VERSION, fingerprint(projection), "ASSET_PROMPT_READY")


def build_character_asset_prompt(identity: str, fields: dict[str, Any]) -> AssetPromptIR:
    return _asset_prompt("CHARACTER", identity, fields)


def build_character_variant_prompt(identity: str, variant: str, fields: dict[str, Any]) -> AssetPromptIR:
    return _asset_prompt("CHARACTER_VARIANT", f"{identity}:{variant}", fields)


def build_scene_asset_prompt(identity: str, fields: dict[str, Any]) -> AssetPromptIR:
    return _asset_prompt("SCENE", identity, fields)


def build_prop_asset_prompt(identity: str, fields: dict[str, Any]) -> AssetPromptIR:
    return _asset_prompt("PROP", identity, fields)


def build_visual_style_asset_prompt(identity: str, fields: dict[str, Any]) -> AssetPromptIR:
    return _asset_prompt("VISUAL_STYLE", identity, fields)


def build_performance_plan(*, shot_id: str, characters: list[dict[str, Any]], dialogue: list[dict[str, Any]], emotion_arc: list[dict[str, Any]], body_movement: list[dict[str, Any]], hand_movement: list[dict[str, Any]], head_movement: list[dict[str, Any]], eye_movement: list[dict[str, Any]], facial_changes: list[dict[str, Any]], interaction_beats: list[dict[str, Any]], prop_interaction: list[dict[str, Any]], camera_movement: list[dict[str, Any]], ending_pose: dict[str, Any], duration: float = 5.0) -> ShotPerformancePlan:
    return ShotPerformancePlan(shot_id, duration, characters, dialogue, emotion_arc, body_movement, hand_movement, head_movement, eye_movement, facial_changes, interaction_beats, prop_interaction, camera_movement, ending_pose)


def build_timecoded_motion_ir(plan: ShotPerformancePlan) -> TimecodedMotionIR:
    segments = []
    for segment in _list(plan.body_movement):
        item = dict(segment)
        item.setdefault("start_time", 0.0)
        item.setdefault("end_time", plan.duration)
        if isinstance(item.get("actor"), str):
            item["actor"] = item["actor"].strip()
        for key in ("body_action", "hand_action", "head_action", "eye_action", "facial_action", "dialogue", "dialogue_delivery", "lip_sync_window", "prop_action", "interaction_target", "camera_action", "emotion_start", "emotion_end", "ending_state"):
            item.setdefault(key, "N/A")
        segments.append(item)
    if not segments:
        raise ValueError("TIMECODED_MOTION_REQUIRED")
    if any(float(item["end_time"]) <= float(item["start_time"]) for item in segments):
        raise ValueError("TIMECODED_MOTION_RANGE_INVALID")
    return TimecodedMotionIR(plan.shot_id, plan.duration, segments, False)


def _character_frame(item: dict[str, Any]) -> str:
    return "；".join(f"{key}：{value}" for key, value in item.items() if value not in (None, "") and key not in {"identity", "asset_ref"})


def render_keyframe_prompt(*, scene: dict[str, Any], characters: list[dict[str, Any]], props: list[dict[str, Any]], camera: dict[str, Any], composition: dict[str, Any], lighting: dict[str, Any], continuity: dict[str, Any], style: dict[str, Any]) -> dict[str, Any]:
    sections = [
        f"场景：{_text(scene.get('description'))}；时间：{_text(scene.get('time'))}；天气：{_text(scene.get('weather'))}；空间布局：{_text(scene.get('layout'))}",
        "可见人物：" + "；".join(_character_frame(item) for item in characters),
        "道具状态：" + ("；".join(_character_frame(item) for item in props) if props else "无额外道具"),
        "摄影机：" + "；".join(f"{key}：{value}" for key, value in camera.items() if value not in (None, "")),
        "构图层次：" + "；".join(f"{key}：{value}" for key, value in composition.items() if value not in (None, "")),
        "灯光：" + "；".join(f"{key}：{value}" for key, value in lighting.items() if value not in (None, "")),
        "连续性：" + "；".join(f"{key}：{value}" for key, value in continuity.items() if value not in (None, "")),
        "风格：" + "；".join(f"{key}：{value}" for key, value in style.items() if value not in (None, "")),
    ]
    prompt = "。".join(sections) + "。"
    return {"prompt": prompt, "negative_prompt": "避免人物身份漂移、服装材质变化、错误道具位置、空间布局改变、额外人物、文字水印", "language": "zh-CN", "renderer_version": KEYFRAME_RENDERER_VERSION, "generation_payload_fingerprint": fingerprint({"prompt": prompt, "renderer_version": KEYFRAME_RENDERER_VERSION})}


def render_timecoded_video_prompt(*, first_frame_prompt: str, plan: ShotPerformancePlan, motion: TimecodedMotionIR, ending_state: dict[str, Any], camera_timeline: list[dict[str, Any]], dialogue_audio_generated: bool = False) -> dict[str, Any]:
    lines = ["首帧连续性：从官方首帧开始，保持人物身份、服装、场景结构、道具位置和构图连续。"]
    for item in motion.segments:
        lines.append(f"{float(item['start_time']):.1f}–{float(item['end_time']):.1f} 秒：{item.get('actor', '主体')}；身体：{item.get('body_action')}；手部：{item.get('hand_action')}；头部：{item.get('head_action')}；视线：{item.get('eye_action')}；面部：{item.get('facial_action')}；道具：{item.get('prop_action')}；互动对象：{item.get('interaction_target')}；情绪：{item.get('emotion_start')}→{item.get('emotion_end')}；结束姿态：{item.get('ending_state')}。")
    lines.append("镜头时间线：" + "；".join(f"{item.get('start_time', 0):.1f}–{item.get('end_time', plan.duration):.1f} 秒 {item.get('action', '保持') }" for item in camera_timeline) + "。")
    if plan.dialogue:
        lines.append("对白/口型：音频生成关闭；仅控制视觉口型、停顿、转接和反应时间。" + "；".join(f"{item.get('speaker')}在{item.get('start_time'):.1f}–{item.get('end_time'):.1f}秒完成口型：{item.get('text')}（{item.get('delivery')}）" for item in plan.dialogue))
    else:
        lines.append("对白/口型：本镜无 ScriptIR 授权对白；不生成音频。")
    lines.append("最终状态：" + "；".join(f"{key}：{value}" for key, value in ending_state.items() if value not in (None, "")) + "。")
    lines.append("禁止事项：不新增人物，不改变服装或关键道具状态，不出现跳切、额外镜头运动、身份漂移或音频生成。")
    prompt = "\n".join(lines)
    return {"prompt": prompt, "negative_prompt": "避免跳切、变形、额外动作、额外镜头运动、身份漂移、服装变化、音频生成、文字水印", "language": "zh-CN", "duration_seconds": plan.duration, "dialogue_audio_generated": dialogue_audio_generated, "renderer_version": VIDEO_RENDERER_VERSION, "generation_payload_fingerprint": fingerprint({"prompt": prompt, "renderer_version": VIDEO_RENDERER_VERSION})}


def quality_gate_v3(*, assets: list[AssetPromptIR], keyframes: list[dict[str, Any]], videos: list[dict[str, Any]], motions: list[TimecodedMotionIR], plans: list[ShotPerformancePlan]) -> dict[str, Any]:
    generic = sum(sum(1 for phrase in GENERIC_PATTERNS if phrase in item.get("prompt", "")) for item in keyframes + videos)
    internal = sum(1 for item in keyframes + videos if INTERNAL_TOKEN_RE.search(item.get("prompt", "")))
    asset_blockers = sum(1 for asset in assets if asset.readiness != "ASSET_PROMPT_READY")
    timeline_blockers = sum(1 for motion in motions if not motion.segments or motion.dialogue_audio_generated)
    dialogue_missing = sum(1 for plan in plans if plan.dialogue and not any(item.get("lip_sync_window") not in (None, "N/A", "") for item in next((m.segments for m in motions if m.shot_id == plan.shot_id), [])))
    return {"asset_prompt_readiness": "PASS" if asset_blockers == 0 else "BLOCK", "asset_blocker_count": asset_blockers, "timecoded": len(motions) == len(plans), "timeline_blocker_count": timeline_blockers, "dialogue_timing_blocker_count": dialogue_missing, "generic_placeholder_count": generic, "internal_token_leak_count": internal, "keyframe_count": len(keyframes), "video_count": len(videos), "status": "PASS" if not any((asset_blockers, timeline_blockers, dialogue_missing, generic, internal)) else "BLOCK"}


__all__ = ["AssetPromptIR", "ShotPerformancePlan", "TimecodedMotionIR", "build_character_asset_prompt", "build_character_variant_prompt", "build_scene_asset_prompt", "build_prop_asset_prompt", "build_visual_style_asset_prompt", "build_performance_plan", "build_timecoded_motion_ir", "render_keyframe_prompt", "render_timecoded_video_prompt", "quality_gate_v3", "fingerprint", "ASSET_RENDERER_VERSION", "KEYFRAME_RENDERER_VERSION", "VIDEO_RENDERER_VERSION"]
