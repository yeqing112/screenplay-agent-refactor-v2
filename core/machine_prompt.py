"""Machine Prompt compiler/exporter for storyboard video generation.

This module formalizes the product boundary agreed on 2026-08-25:

Director Shot Text (system generated + user editable)
-> standardized Machine Prompt (model-neutral, executable)
-> model/webui/api-json export (submission is optional and out of scope here).

The functions here are deterministic. They do not call an LLM and do not submit
to any generation provider.
"""

from __future__ import annotations

from typing import Any

from core.model_adapter import sanitize_machine_prompt_text
from core.prompt_ir import AssetBinding, ShotIR


MINIMAX_H3_MIN_DURATION_SECONDS = 4
MINIMAX_H3_MAX_DURATION_SECONDS = 15


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()


def _truncate(text: object, limit: int = 140) -> str:
    value = _clean_text(text)
    if len(value) <= limit:
        return value
    return value[:limit].rstrip("，。；、,. ") + "…"


def _rstrip_terminal_punct(text: object) -> str:
    return _clean_text(text).rstrip("。.!！?？")


def _machine_action_text(value: object) -> str:
    return sanitize_machine_prompt_text(value)


def _asset_label(binding: AssetBinding) -> str:
    name = _clean_text(getattr(binding, "asset_name", ""))
    token = _clean_text(getattr(binding, "reference_token", ""))
    if name and token:
        return f"{name}（{token}）"
    return name or token


def _asset_hint(binding: AssetBinding) -> str:
    parts: list[str] = []
    for item in getattr(binding, "canonical_prompt_parts", []) or []:
        if isinstance(item, dict):
            text = _clean_text(item.get("text"))
            if text:
                parts.append(text)
        if len(parts) >= 2:
            break
    if not parts:
        raw = _clean_text(getattr(binding, "authority_prompt_raw", ""))
        if raw:
            parts.append(raw)
    return _truncate("；".join(parts), 180)


def _shot_size_zh(ir: ShotIR) -> str:
    angle = _clean_text(ir.camera_angle).upper()
    return {
        "WS": "远景",
        "LS": "全景",
        "MS": "中景",
        "MCU": "近景",
        "CU": "特写",
        "ECU": "极特写",
    }.get(angle, ir.camera_angle or "中景")


def _camera_motion_zh(ir: ShotIR) -> str:
    movement = _clean_text(ir.camera_movement).lower().replace("_", "-")
    speed = _clean_text(ir.camera_speed).lower()
    # Structured records may carry a composed value such as
    # ``slow_push_in``.  Split the speed prefix before looking up the camera
    # movement so the exported machine language is a real standard term
    # ("缓慢推进"), rather than leaking the internal enum verbatim.
    for prefix, inferred_speed in (
        ("very-slow-", "very_slow"),
        ("slow-", "slow"),
        ("medium-", "medium"),
        ("fast-", "fast"),
    ):
        if movement.startswith(prefix):
            movement = movement[len(prefix):]
            if not speed:
                speed = inferred_speed
            break
    speed_prefix = {
        "very_slow": "极缓慢",
        "very-slow": "极缓慢",
        "slow": "缓慢",
        "medium": "平稳",
        "fast": "快速",
    }.get(speed, "平稳")
    mapping = {
        "static": "固定机位",
        "push-in": f"{speed_prefix}推进",
        "pushin": f"{speed_prefix}推进",
        "pull-out": f"{speed_prefix}后撤",
        "pan-left": f"{speed_prefix}左摇",
        "pan-right": f"{speed_prefix}右摇",
        "tilt-up": f"{speed_prefix}上摇",
        "tilt-down": f"{speed_prefix}下摇",
        "dolly": f"{speed_prefix}滑轨移动",
        "zoom": f"{speed_prefix}变焦",
        "handheld": "轻微可控手持",
        "orbit-left": f"{speed_prefix}左环绕",
        "orbit-right": f"{speed_prefix}右环绕",
    }
    return mapping.get(movement, f"{speed_prefix}{ir.camera_movement or '稳定运镜'}")


def _timeline_ranges(duration: int) -> list[tuple[str, float, float]]:
    total = max(int(duration or 3), 1)
    if total <= 3:
        ratios = [("opening", 0.0, 0.35), ("development", 0.35, 0.80), ("landing", 0.80, 1.0)]
    else:
        ratios = [("opening", 0.0, 0.20), ("development", 0.20, 0.75), ("landing", 0.75, 1.0)]
    return [(name, round(total * start, 2), round(total * end, 2)) for name, start, end in ratios]


def normalize_minimax_h3_duration(value: object) -> int:
    """Return the provider-valid H3 duration used by both export and submission."""

    try:
        duration = int(value or MINIMAX_H3_MIN_DURATION_SECONDS)
    except (TypeError, ValueError):
        duration = MINIMAX_H3_MIN_DURATION_SECONDS
    return min(max(duration, MINIMAX_H3_MIN_DURATION_SECONDS), MINIMAX_H3_MAX_DURATION_SECONDS)


def build_director_shot_text(ir: ShotIR) -> str:
    """Build the human creative layer that users may edit before compilation."""

    lines = [
        f"场景：{ir.scene_name or _asset_label(ir.scene_binding) or '当前场景'}",
        f"镜头：{_shot_size_zh(ir)}，{_camera_motion_zh(ir)}，时长约 {max(int(ir.duration or 3), 1)} 秒。",
    ]
    if ir.start_state:
        lines.append(f"起始：{ir.start_state}")
    if ir.action_process:
        lines.append(f"过程：{ir.action_process}")
    if ir.end_state:
        lines.append(f"落点：{ir.end_state}")
    if ir.dialogue:
        lines.append(f"对白/声音线索：{ir.dialogue}")
    if ir.emotion_arc.start or ir.emotion_arc.end:
        start = ir.emotion_arc.start or "当前情绪"
        end = ir.emotion_arc.end or start
        lines.append(f"情绪：{start} -> {end}，强度 {ir.emotion_arc.intensity or 'medium'}。")
    if ir.lighting:
        lines.append(f"光影：{ir.lighting}")
    return "\n".join(lines)


def _reference_image_payload(reference_images: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for item in reference_images or []:
        if not isinstance(item, dict):
            continue
        url = _clean_text(
            item.get("image_url")
            or item.get("url")
            or item.get("preview_url")
            or item.get("file_path")
        )
        label = _clean_text(
            item.get("asset_name")
            or item.get("name")
            or item.get("reference_token")
            or item.get("asset_id")
        )
        if url or label:
            result.append(
                {
                    "label": label,
                    "url": url,
                    "status": _clean_text(item.get("status") or item.get("reference_status")),
                    "asset_type": _clean_text(item.get("asset_type") or item.get("asset_scope")),
                }
            )
    return result


def _asset_references(ir: ShotIR, reference_images: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    bindings = [ir.scene_binding, *ir.character_bindings, *ir.prop_bindings]
    references: list[dict[str, Any]] = []
    for binding in bindings:
        label = _asset_label(binding)
        if not label:
            continue
        references.append(
            {
                "asset_type": _clean_text(getattr(binding, "asset_type", "")),
                "asset_id": _clean_text(getattr(binding, "asset_id", "")),
                "label": label,
                "reference_token": _clean_text(getattr(binding, "reference_token", "")),
                "reference_status": _clean_text(getattr(binding, "reference_status", "")),
                "authority_hint": _asset_hint(binding),
            }
        )

    images = _reference_image_payload(reference_images)
    if images:
        references.append(
            {
                "asset_type": "reference_images",
                "label": f"{len(images)} 张参考图",
                "reference_images": images,
                "usage_policy": "作为人物身份、场景空间、道具外观与首帧连续性锚点；不得凭空替换资产。",
            }
        )
    return references


def _visual_facts(ir: ShotIR) -> list[str]:
    facts: list[str] = []
    for item in ir.visual_facts:
        fact = _clean_text(getattr(item, "fact", ""))
        name = _clean_text(getattr(item, "asset_name", ""))
        if fact:
            facts.append(f"{name}：{fact}" if name else fact)
    return facts[:12]


def _continuity_constraints(ir: ShotIR) -> list[str]:
    constraints = [
        "人物身份、脸型、发型、服装、关键道具与场景布局在镜头内保持连续。",
        "只表现当前镜头可观察到的动作变化，不新增未在导演分镜或资产中声明的主体。",
    ]
    if ir.continuity.has_previous and ir.continuity.previous_end_state:
        constraints.insert(0, f"开头承接上一镜结束状态：{_rstrip_terminal_punct(_truncate(ir.continuity.previous_end_state, 120))}。")
    if ir.scene_name or ir.continuity.previous_scene_name:
        constraints.append(f"场景连续性锚定为：{ir.scene_name or ir.continuity.previous_scene_name}。")
    return constraints


def infer_soundscape(ir: ShotIR) -> dict[str, str]:
    scene_text = f"{ir.scene_name} {ir.start_state} {ir.action_process} {ir.end_state}".lower()
    if any(key in scene_text for key in ("便利店", "收银台", "货架")):
        ambience = "冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。"
    elif any(key in scene_text for key in ("监控室", "监控", "屏幕")):
        ambience = "监控屏幕电流声、轻微电子噪点、空调低频与封闭房间的静态底噪。"
    elif any(key in scene_text for key in ("丛林", "森林", "密林", "神农架")):
        ambience = "远处虫鸣、树叶摩擦、潮湿林地脚步声与被树冠压住的低沉环境声。"
    elif any(key in scene_text for key in ("部落", "营地", "火堆")):
        ambience = "火堆噼啪声、远处人群低语、夜间林地环境声与轻微器物碰撞。"
    elif any(key in scene_text for key in ("医院", "病房", "手术")):
        ambience = "日光灯电流声、远处仪器提示音、走廊脚步回声与压低的室内底噪。"
    elif any(key in scene_text for key in ("赌场", "会所", "酒吧")):
        ambience = "隔墙低频音乐、人群细碎交谈、玻璃杯轻碰声与空间混响。"
    else:
        ambience = "贴合场景的低强度环境底噪，保持真实空间感，不抢占主体动作。"

    purpose = _clean_text(ir.shot_purpose).lower()
    if any(key in purpose for key in ("comedy", "轻松", "喜剧")):
        music = "轻微跳动的短音型，节奏克制，只托住反应点。"
    elif any(key in purpose for key in ("adventure", "冒险")):
        music = "稀疏的低频节奏和轻微脉冲，随动作推进保持紧张但不喧宾夺主。"
    else:
        music = "稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。"
    return {"overall_soundscape": ambience, "non_diegetic_music": music}


def compile_machine_prompt(
    ir: ShotIR,
    *,
    reference_images: list[dict[str, Any]] | None = None,
    reference_summary: str = "",
    director_shot_text: str | None = None,
) -> dict[str, Any]:
    """Compile ShotIR into a model-neutral, executable machine prompt payload."""

    director_text = director_shot_text or build_director_shot_text(ir)
    machine_start_state = _machine_action_text(ir.start_state)
    machine_action_process = _machine_action_text(ir.action_process)
    machine_end_state = _machine_action_text(ir.end_state)
    machine_dialogue = _machine_action_text(ir.dialogue)
    timeline_source = {
        "opening": machine_start_state or machine_action_process or machine_end_state,
        "development": machine_action_process or machine_end_state or machine_start_state,
        "landing": machine_end_state or machine_action_process or machine_start_state,
    }
    camera = {
        "shot_size": _shot_size_zh(ir),
        "movement": _camera_motion_zh(ir),
        "speed": _clean_text(ir.camera_speed) or "slow",
        "transition": _clean_text(ir.transition) or "cut",
    }
    timeline = []
    for phase, start_sec, end_sec in _timeline_ranges(ir.duration):
        timeline.append(
            {
                "phase": phase,
                "time_range_seconds": f"{start_sec:.2f}-{end_sec:.2f}s",
                "visual_action": _truncate(timeline_source[phase], 220),
                "camera_instruction": camera["movement"],
                "continuity_goal": "继承上一阶段视觉状态" if phase != "opening" else "建立首帧状态与资产锚点",
            }
        )

    sound = infer_soundscape(ir)
    machine_prompt = {
        "schema_version": "machine_prompt_v1",
        "source_layer": "director_shot_text",
        "api_submission": False,
        "shot": {
            "shot_id": ir.shot_id,
            "scene_name": ir.scene_name,
            "duration_seconds": max(int(ir.duration or 3), 1),
            "purpose": _clean_text(ir.shot_purpose),
        },
        "director_shot_text": director_text,
        "visual_timeline": timeline,
        "camera": camera,
        "observable_action": {
            "start_state": machine_start_state,
            "action_process": machine_action_process,
            "end_state": machine_end_state,
            "dialogue_or_sound_cue": machine_dialogue,
        },
        "emotion_arc": {
            "start": _clean_text(ir.emotion_arc.start),
            "end": _clean_text(ir.emotion_arc.end),
            "intensity": _clean_text(ir.emotion_arc.intensity) or "medium",
        },
        "asset_references": _asset_references(ir, reference_images),
        "visual_facts": _visual_facts(ir),
        "reference_summary": _clean_text(reference_summary),
        "continuity_constraints": _continuity_constraints(ir),
        "soundscape": sound,
        "negative_constraints": [
            "不要字幕、水印、logo、分屏、四宫格或界面文字。",
            "不要改变人物身份、服装、发型、场景布局和关键道具状态。",
            "不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。",
        ],
        "export_contract": {
            "webui_copy_supported": True,
            "markdown_supported": True,
            "csv_supported": True,
            "api_json_supported": True,
            "api_submission_is_separate_step": True,
        },
    }
    return machine_prompt


def _h3_reference_role(asset_type: object) -> str:
    normalized = _clean_text(asset_type).lower()
    if normalized == "storyboard_composition":
        return "approved shot composition, character blocking, screen direction, spatial layout, and lighting only"
    if normalized == "scene":
        return "scene layout, spatial proportions, and lighting"
    if normalized == "character":
        return "character identity, face, hair, costume, and body silhouette"
    if normalized == "prop":
        return "prop shape, material, color, and state"
    return "the declared visual asset only"


def _rescale_h3_timeline(timeline: list[dict[str, Any]], duration_seconds: int) -> list[tuple[dict[str, Any], str]]:
    ranges = _timeline_ranges(duration_seconds)
    return [
        (segment, f"{start:.2f}-{end:.2f}s")
        for segment, (_, start, end) in zip(timeline, ranges)
        if isinstance(segment, dict)
    ]


def export_minimax_h3_webui(machine_prompt: dict[str, Any]) -> dict[str, Any]:
    shot = machine_prompt.get("shot") or {}
    timeline = machine_prompt.get("visual_timeline") or []
    action = machine_prompt.get("observable_action") or {}
    camera = machine_prompt.get("camera") or {}
    source_duration = shot.get("duration_seconds")
    duration_seconds = normalize_minimax_h3_duration(source_duration)
    refs = [
        image
        for asset in machine_prompt.get("asset_references") or []
        for image in (asset.get("reference_images") or [])
        if isinstance(asset, dict)
    ]
    if refs:
        reference_assignments = []
        for index, image in enumerate(refs, start=1):
            label = _clean_text(image.get("label")) or f"reference {index}"
            role = _h3_reference_role(image.get("asset_type"))
            reference_assignments.append(f"Reference image {index} ({label}): use only for {role}.")
        ref_sentence = "Reference assignments: " + " ".join(reference_assignments) + " Do not swap the roles of reference images. "
    else:
        ref_sentence = "Use the structured asset descriptions only for their declared identity, scene, or prop roles. "

    segments = []
    for segment, time_range in _rescale_h3_timeline(timeline, duration_seconds):
        segments.append(
            f"{time_range}: {segment.get('visual_action')} "
            f"Camera: {segment.get('camera_instruction')}."
        )

    negative_constraints = [
        _clean_text(item)
        for item in (machine_prompt.get("negative_constraints") or [])
        if _clean_text(item)
    ]
    hard_constraints = " ".join(negative_constraints)
    sound = machine_prompt.get("soundscape") or {}
    sound_cue = _clean_text(sound.get("overall_soundscape"))

    integrated = (
        f"[Shot {shot.get('shot_id')}] Live-action cinematic footage. "
        f"Scene: {shot.get('scene_name') or 'current scene'}. "
        f"Duration: {duration_seconds} seconds. "
        f"{ref_sentence}"
        f"Opening state: {_rstrip_terminal_punct(action.get('start_state'))}. "
        f"Observable action timeline: {' '.join(segments)} "
        f"Final frame: {_rstrip_terminal_punct(action.get('end_state'))}. "
        f"Shot size: {camera.get('shot_size')}; camera movement: {camera.get('movement')}. "
        f"Maintain continuity of face, costume, hair, prop state, lighting, and spatial layout. "
        f"Hard constraints: {hard_constraints or 'No unexplained changes or extra subjects.'} "
        f"Ambient sound cue: {sound_cue or 'Keep the scene ambience natural and restrained.'}"
    )
    return {
        "target_model": "minimax-h3",
        "export_mode": "webui_copy",
        "api_submission": False,
        "fields": {
            "integrated_multimodal_description": _clean_text(integrated),
            "overall_soundscape": _clean_text(sound.get("overall_soundscape")),
            "non_diegetic_music": _clean_text(sound.get("non_diegetic_music")),
        },
        "reference_images": refs,
        "model_params": {
            "duration_seconds": duration_seconds,
            "source_duration_seconds": source_duration,
            "aspect_ratio": "16:9",
            "submission_policy": "export_only; paste into WebUI or convert to API payload explicitly",
        },
    }


def export_generic_zh_video_webui(machine_prompt: dict[str, Any]) -> dict[str, Any]:
    shot = machine_prompt.get("shot") or {}
    camera = machine_prompt.get("camera") or {}
    action = machine_prompt.get("observable_action") or {}
    sound = machine_prompt.get("soundscape") or {}
    timeline = machine_prompt.get("visual_timeline") or []
    lines = [
        f"镜头 {shot.get('shot_id')}｜{shot.get('scene_name')}｜{shot.get('duration_seconds')} 秒｜16:9",
        f"首帧：{action.get('start_state')}",
        f"镜头：{camera.get('shot_size')}，{camera.get('movement')}，转场 {camera.get('transition')}",
        "动作时间线：",
    ]
    for segment in timeline:
        lines.append(f"- {segment.get('time_range_seconds')}：{segment.get('visual_action')}")
    if action.get("dialogue_or_sound_cue"):
        lines.append(f"对白/同期声线索：{action.get('dialogue_or_sound_cue')}")
    lines.extend(
        [
            f"结束落点：{action.get('end_state')}",
            "连续性约束：" + "；".join(machine_prompt.get("continuity_constraints") or []),
            f"环境声：{sound.get('overall_soundscape')}",
            f"配乐：{sound.get('non_diegetic_music')}",
            "负面约束：" + "；".join(machine_prompt.get("negative_constraints") or []),
        ]
    )
    return {
        "target_model": "generic-zh-video",
        "export_mode": "webui_copy",
        "api_submission": False,
        "prompt": "\n".join(lines),
    }


def export_machine_prompt(machine_prompt: dict[str, Any], target_model: str) -> dict[str, Any]:
    normalized = _clean_text(target_model).lower().replace("_", "-")
    if normalized in {"minimax-h3", "h3", "minimax"}:
        return export_minimax_h3_webui(machine_prompt)
    return export_generic_zh_video_webui(machine_prompt)
