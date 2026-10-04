"""Director decision IR and deterministic provider projections for prompt V4.

The director decision layer is the only layer allowed to choose production
actions.  Renderers below only serialize already-resolved decisions into
provider language.  The module is fixture agnostic and never calls media
providers.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


SCHEMA_VERSION = "prompt_production_v4"
REJECTED_INTERNAL_REFS = (
    "performance plan", "PerformancePlan", "ShotPlan", "previous state", "current framing",
    "locked variant", "authority", "由 performance plan 控制", "沿用本镜 performance plan",
    "保持既定位置", "下一镜可继承", "当前线索", "交互目标", "当前关注点",
)
GENERIC_PHRASES = (
    "完成主要身体动作", "完成一次可见反应", "完成一次明确动作", "头部小幅调整",
    "视线锁定交互目标", "道具进入最终状态", "保持本镜空间区位", "完成动作后稳定",
    "最终头部方向", "最终视线目标", "保持本镜最终状态", "自然反应", "克制反应",
    "做一次", "某个", "一次明确的", "由.*控制", "沿用.*",
)
SCHEMA_DUMP_RE = re.compile(r"(?:^|[；;\n])\s*(?:identity|source|face_shape|multi_view_policy|required_fields|asset_type|fields|renderer_version)\s*[:：]")


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


@dataclass
class AssetDesignDecisionIR:
    asset_type: str
    identity: str
    source_facts: dict[str, Any]
    design_decisions: dict[str, Any]
    reference_policy: dict[str, Any]
    status: str = "READY"


@dataclass
class KeyframeBlockingIR:
    identity: str
    reference_identity: str
    position: str
    screen_x: str
    depth_zone: str
    body_pose: str
    weight_distribution: str
    torso_direction: str
    head_yaw: str
    head_pitch: str
    eye_target: str
    expression: str
    left_hand: str
    right_hand: str
    prop_contact: str


@dataclass
class DialoguePerformancePlan:
    speaker: str
    authoritative_text: str
    start_time: float
    end_time: float
    delivery: str
    phrase_windows: list[dict[str, Any]]
    estimated_minimum_seconds: float
    status: str = "READY"


@dataclass
class CameraChoreographyIR:
    start_time: float
    end_time: float
    movement_type: str
    direction: str
    speed: str
    distance_or_scale_change: str
    target: str
    start_framing: str
    end_framing: str
    easing: str


@dataclass
class DirectorDecisionIR:
    shot_id: str
    duration_seconds: float
    source_facts: dict[str, Any]
    starting_state: dict[str, Any]
    blocking: list[KeyframeBlockingIR]
    performance_beats: list[dict[str, Any]]
    dialogue_beats: list[DialoguePerformancePlan]
    camera_beats: list[CameraChoreographyIR]
    emotion_arc: dict[str, Any]
    ending_state: dict[str, Any]
    source_fact_hash: str
    producer: str = "DIRECTOR_DECISION_LAYER_V4"


def estimate_dialogue_duration(text: str, delivery: str = "normal") -> float:
    """Conservative visual mouth-time estimate; punctuation adds pauses."""
    text = _text(text)
    if not text:
        return 0.0
    speed = {"fast": 0.115, "normal": 0.145, "slow": 0.19}.get(delivery, 0.16)
    visible = len(re.sub(r"\s+", "", text))
    punctuation = len(re.findall(r"[，。！？、；：,.!?;:]", text))
    return round(visible * speed + punctuation * 0.16 + 0.25, 2)


def split_dialogue_phrases(text: str, start_time: float, delivery: str = "normal") -> list[dict[str, Any]]:
    chunks = [chunk.strip() for chunk in re.split(r"(?<=[，。！？、；：,.!?;:])", _text(text)) if chunk.strip()]
    if not chunks:
        return []
    weights = [max(1, len(re.sub(r"\s+", "", chunk))) for chunk in chunks]
    total = sum(weights)
    duration = estimate_dialogue_duration(text, delivery)
    cursor = float(start_time)
    result = []
    for index, (chunk, weight) in enumerate(zip(chunks, weights)):
        span = duration * weight / total
        end = cursor + span
        result.append({"index": index + 1, "text": chunk, "start_time": round(cursor, 2), "end_time": round(end, 2)})
        cursor = end
    return result


def build_dialogue_performance_plan(speaker: str, text: str, *, start_time: float, shot_duration: float, delivery: str = "normal") -> DialoguePerformancePlan:
    minimum = estimate_dialogue_duration(text, delivery)
    end = round(start_time + minimum, 2)
    status = "READY" if end <= shot_duration else "DIALOGUE_DURATION_OVERFLOW"
    return DialoguePerformancePlan(
        speaker=speaker,
        authoritative_text=_text(text),
        start_time=float(start_time),
        end_time=min(end, shot_duration),
        delivery=delivery,
        phrase_windows=split_dialogue_phrases(text, start_time, delivery),
        estimated_minimum_seconds=minimum,
        status=status,
    )


def semantic_placeholder_reasons(value: Any) -> list[str]:
    text = _text(value)
    reasons: list[str] = []
    for phrase in GENERIC_PHRASES:
        if re.search(phrase, text, flags=re.IGNORECASE):
            reasons.append(f"UNRESOLVED_SEMANTIC_PLACEHOLDER:{phrase}")
    for ref in REJECTED_INTERNAL_REFS:
        if ref in text:
            reasons.append(f"INTERNAL_PLAN_REFERENCE:{ref}")
    if re.search(r"(?:主体|角色|人物|某人|某个)\s*(?:完成|反应|移动|看向)", text):
        reasons.append("UNNAMED_ACTOR_ACTION")
    if re.search(r"(?:保持|停在|转向|注视)\s*(?:目标|对象|那里|当前)", text):
        reasons.append("UNRESOLVED_REFERENT")
    return sorted(set(reasons))


def validate_source_facts(decision: DirectorDecisionIR, source_facts: Mapping[str, Any]) -> dict[str, Any]:
    expected = _dict(source_facts)
    actual = decision.source_facts
    conflicts: list[dict[str, Any]] = []
    for key in ("shot_id", "scene_id", "character_ids", "prop_ids", "dialogue", "location"):
        if key not in expected:
            continue
        if actual.get(key) != expected.get(key):
            conflicts.append({"field": key, "expected": expected.get(key), "actual": actual.get(key)})
    allowed_chars = set(expected.get("character_ids") or [])
    for block in decision.blocking:
        if allowed_chars and block.identity not in allowed_chars:
            conflicts.append({"field": "blocking.identity", "expected": sorted(allowed_chars), "actual": block.identity})
    return {"source_fact_conflicts": conflicts, "count": len(conflicts), "status": "PASS" if not conflicts else "BLOCK"}


def validate_llm_director_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the nested DirectorDecisionIR contract before projection."""
    errors: list[str] = []
    if not isinstance(payload.get("shot_id"), str) or not _text(payload.get("shot_id")):
        errors.append("DIRECTOR_PLAN_SCHEMA_INVALID:shot_id")
    if not isinstance(payload.get("source_facts"), Mapping):
        errors.append("DIRECTOR_PLAN_SCHEMA_INVALID:source_facts")
    blocks = payload.get("blocking")
    if not isinstance(blocks, list) or not blocks:
        errors.append("DIRECTOR_PLAN_SCHEMA_INVALID:blocking_must_be_array")
    else:
        required = {"identity", "reference_identity", "position", "screen_x", "depth_zone", "body_pose", "weight_distribution", "torso_direction", "head_yaw", "head_pitch", "eye_target", "expression", "left_hand", "right_hand", "prop_contact"}
        for index, item in enumerate(blocks):
            if not isinstance(item, Mapping):
                errors.append(f"DIRECTOR_PLAN_SCHEMA_INVALID:blocking[{index}]")
                continue
            errors.extend(f"DIRECTOR_PLAN_SCHEMA_INVALID:blocking[{index}].{key}" for key in sorted(required - set(item)))
    beats = payload.get("performance_beats")
    if not isinstance(beats, list) or not beats:
        errors.append("DIRECTOR_PLAN_SCHEMA_INVALID:performance_beats")
    else:
        required = {"start_time", "end_time", "actor", "body_action", "hand_action", "head_action", "eye_action", "facial_action", "ending_state"}
        for index, item in enumerate(beats):
            if not isinstance(item, Mapping):
                errors.append(f"DIRECTOR_PLAN_SCHEMA_INVALID:performance_beats[{index}]")
                continue
            errors.extend(f"DIRECTOR_PLAN_SCHEMA_INVALID:performance_beats[{index}].{key}" for key in sorted(required - set(item)))
            errors.extend(f"UNRESOLVED_LLM_BEAT:{index}:{reason}" for reason in semantic_placeholder_reasons(item))
    camera = payload.get("camera_beats")
    if not isinstance(camera, list) or not camera:
        errors.append("DIRECTOR_PLAN_SCHEMA_INVALID:camera_beats")
    else:
        required = {"start_time", "end_time", "movement_type", "direction", "speed", "distance_or_scale_change", "target", "start_framing", "end_framing", "easing"}
        for index, item in enumerate(camera):
            if not isinstance(item, Mapping):
                errors.append(f"DIRECTOR_PLAN_SCHEMA_INVALID:camera_beats[{index}]")
                continue
            errors.extend(f"DIRECTOR_PLAN_SCHEMA_INVALID:camera_beats[{index}].{key}" for key in sorted(required - set(item)))
    dialogue = payload.get("dialogue_beats")
    if not isinstance(dialogue, list):
        errors.append("DIRECTOR_PLAN_SCHEMA_INVALID:dialogue_beats")
    else:
        for index, item in enumerate(dialogue):
            if not isinstance(item, Mapping):
                errors.append(f"DIRECTOR_PLAN_SCHEMA_INVALID:dialogue_beats[{index}]")
            elif not _text(item.get("authoritative_text")) or not isinstance(item.get("phrase_windows"), list):
                errors.append(f"DIRECTOR_PLAN_SCHEMA_INVALID:dialogue_beats[{index}].authoritative_text_or_phrase_windows")
    if not isinstance(payload.get("emotion_arc"), Mapping):
        errors.append("DIRECTOR_PLAN_SCHEMA_INVALID:emotion_arc")
    ending = payload.get("ending_state")
    if not isinstance(ending, Mapping) or not ending.get("characters") or not ending.get("camera"):
        errors.append("DIRECTOR_PLAN_UNRESOLVED_ENDING_STATE")
    return {"status": "PASS" if not errors else "BLOCK", "errors": sorted(set(errors)), "error_count": len(set(errors))}


def validate_dialogue_plans(plans: list[DialoguePerformancePlan], duration: float) -> dict[str, Any]:
    duplicated = []
    overflow = []
    seen: dict[str, list[tuple[float, float]]] = {}
    for plan in plans:
        if plan.status == "DIALOGUE_DURATION_OVERFLOW" or plan.estimated_minimum_seconds > max(0.0, plan.end_time - plan.start_time) + 0.05:
            overflow.append(plan.speaker)
        for window in plan.phrase_windows:
            key = _text(window.get("text"))
            seen.setdefault(key, []).append((float(window.get("start_time", 0)), float(window.get("end_time", 0))))
        if plan.end_time > duration + 0.01:
            overflow.append(plan.speaker)
    for text, windows in seen.items():
        if text and len(windows) > 1:
            duplicated.append({"text": text, "windows": windows})
    return {
        "duplicated_windows": duplicated,
        "overflow": sorted(set(overflow)),
        "status": "PASS" if not duplicated and not overflow else "BLOCK",
    }


def validate_physical_beats(beats: list[dict[str, Any]]) -> dict[str, Any]:
    reasons: list[str] = []
    required = ("actor", "body_action", "hand_action", "head_action", "eye_action", "facial_action", "ending_state")
    for index, beat in enumerate(beats):
        for key in required:
            if not _text(beat.get(key)):
                reasons.append(f"beat[{index}].{key}:MISSING")
        reasons.extend(f"beat[{index}]:{reason}" for reason in semantic_placeholder_reasons(beat))
    return {"reasons": sorted(set(reasons)), "status": "PASS" if not reasons else "BLOCK"}


def validate_camera_beats(beats: list[CameraChoreographyIR]) -> dict[str, Any]:
    missing = []
    for index, beat in enumerate(beats):
        for field_name in asdict(beat):
            if not _text(getattr(beat, field_name)) and field_name not in {"start_time", "end_time"}:
                missing.append(f"camera[{index}].{field_name}")
    return {"missing": missing, "status": "PASS" if not missing else "BLOCK"}


def validate_keyframe_blocks(blocks: list[KeyframeBlockingIR]) -> dict[str, Any]:
    missing = []
    for index, block in enumerate(blocks):
        for key, value in asdict(block).items():
            if not _text(value):
                missing.append(f"blocking[{index}].{key}")
        missing.extend(f"blocking[{index}]:{reason}" for reason in semantic_placeholder_reasons(block))
    return {"missing": sorted(set(missing)), "status": "PASS" if not missing else "BLOCK"}


def validate_ending_state(state: Mapping[str, Any]) -> dict[str, Any]:
    required = ("characters", "camera")
    missing = [key for key in required if not state.get(key)]
    text = canonical(state)
    reasons = semantic_placeholder_reasons(text)
    return {"missing": missing, "placeholder_reasons": reasons, "status": "PASS" if not missing and not reasons else "BLOCK"}


def cross_shot_repetition_audit(decisions: list[DirectorDecisionIR]) -> dict[str, Any]:
    values: dict[str, list[str]] = {"body_action": [], "hand_action": [], "eye_action": [], "ending_state": []}
    for decision in decisions:
        for beat in decision.performance_beats:
            for key in values:
                values[key].append(_text(beat.get(key)))
    collapsed = {key: sorted(set(items)) for key, items in values.items() if items and len(set(items)) <= max(1, len(decisions) // 3)}
    return {"collapsed_fields": collapsed, "status": "BLOCK" if collapsed else "PASS"}


def timeline_repetition_audit(decisions: list[DirectorDecisionIR]) -> dict[str, Any]:
    boundaries = [
        tuple(
            (round(float(beat.get("start_time", 0)), 2), round(float(beat.get("end_time", 0)), 2))
            for beat in decision.performance_beats
        )
        for decision in decisions
    ]
    unique = len(set(boundaries))
    return {"fixed_timeline_count": len(decisions) - unique, "unique_timeline_count": unique, "status": "BLOCK" if len(decisions) > 1 and unique == 1 else "PASS"}


def render_asset_provider_prompt(decision: AssetDesignDecisionIR) -> str:
    facts = decision.source_facts
    design = decision.design_decisions
    if decision.asset_type == "CHARACTER":
        return (
            f"人物定妆设定板，同一名{facts.get('age', '成年')}角色，16:9 横向画布，严格保持 {decision.identity} 的同一人物身份。"
            f"上排展示正脸近景、左侧脸近景、右前45度脸部近景；下排展示全身正面、全身侧面、全身背面。"
            f"脸部：{facts.get('face', '')}；眼睛：{facts.get('eyes', '')}；鼻子：{facts.get('nose', '')}；嘴部：{facts.get('mouth', '')}；"
            f"皮肤：{facts.get('skin', '')}；头发：{facts.get('hair', '')}；身形：{facts.get('height_build', '')}。"
            f"服装：{facts.get('costume', '')}；面料：{facts.get('costume_materials', '')}；鞋履与配饰：{facts.get('footwear', '')}，{facts.get('accessories', '')}。"
            f"设定板构图：{design.get('composition', '')}；姿势策略：{design.get('pose_policy', '')}；灯光：{design.get('lighting', '')}；背景：{design.get('background', '')}。"
            "六个视图必须保持脸型、发型、身材比例、服装剪裁、材质和配饰完全一致，禁止文字、水印、额外人物和身份漂移。"
        )
    if decision.asset_type == "SCENE":
        return (
            f"场景设定板，16:9 横向 2×2 多视图，同一{facts.get('space_identity', decision.identity)}，四格分别为 master wide、reverse angle、side angle、key detail。"
            f"建筑与布局：{facts.get('architecture', '')}；{facts.get('layout', '')}；门窗：{facts.get('doors_windows', '')}；固定家具：{facts.get('fixed_furniture', '')}；"
            f"材质：{facts.get('materials', '')}；地标：{facts.get('landmarks', '')}；时间与天气：{facts.get('time', '')}、{facts.get('weather', '')}；灯光方向：{facts.get('light_direction', '')}。"
            f"master wide 从{design.get('master_direction', '')}展示完整空间；reverse angle 从{design.get('reverse_direction', '')}展示；side angle 从{design.get('side_direction', '')}展示；key detail 聚焦{design.get('detail_target', '')}。"
            "四格必须是同一建筑、同一布局、同一门窗、同一固定道具、同一时间和同一光线逻辑。"
        )
    if decision.asset_type == "PROP":
        view = design.get("view_layout", "正面、侧面、背面和结构细节")
        return (
            f"道具参考设定板，16:9 横向画布，主体为{facts.get('object_type', decision.identity)}，采用{design.get('board_type', 'multi-angle reference board')}。"
            f"展示{view}；尺寸比例：{facts.get('dimensions', '')}；形状结构：{facts.get('shape', '')}；材质与表面：{facts.get('material', '')}、{facts.get('surface', '')}；"
            f"颜色：{facts.get('color', '')}；磨损：{facts.get('wear', '')}；关键识别特征：{facts.get('distinctive_marks', '')}；故事状态：{facts.get('story_state', '')}。"
            f"背景：{design.get('background', '')}；灯光：{design.get('lighting', '')}；保持每个视角的尺寸、结构、颜色和损坏状态一致，禁止文字水印和额外物体。"
        )
    return (
        f"视觉风格参考板，16:9 横向画布，电影写实悬疑短剧风格。现实度：{facts.get('realism_level', '')}；摄影语言：{facts.get('cinematic_language', '')}；"
        f"对比度：{facts.get('contrast', '')}；饱和度：{facts.get('saturation', '')}；肤色与纹理：{facts.get('skin_rendering', '')}、{facts.get('texture', '')}；"
        f"光线：{facts.get('lighting_philosophy', '')}；镜头与景深：{facts.get('lens_feeling', '')}、{facts.get('depth_of_field', '')}；调色：{facts.get('color_palette', '')}。"
        f"排除：{facts.get('style_exclusions', '')}。"
    )


def render_keyframe_provider_prompt(*, scene: Mapping[str, Any], blocks: list[KeyframeBlockingIR], props: list[dict[str, Any]], camera: Mapping[str, Any], composition: Mapping[str, Any], lighting: Mapping[str, Any], style: Mapping[str, Any]) -> str:
    character_text = "；".join(
        f"{block.identity}（reference identity: {block.reference_identity}）：位于{block.position}，画面横向{block.screen_x}、{block.depth_zone}；{block.body_pose}，重心{block.weight_distribution}，躯干{block.torso_direction}；头部水平转向{block.head_yaw}、俯仰{block.head_pitch}，双眼看向{block.eye_target}；表情为{block.expression}；左手{block.left_hand}，右手{block.right_hand}，与道具关系：{block.prop_contact}"
        for block in blocks
    )
    prop_text = "；".join(f"{item.get('name', item.get('identity', '道具'))}：{item.get('state', '')}，位于{item.get('position', '')}" for item in props) or "无额外道具"
    return (
        f"生成一张可直接作为视频首帧的16:9电影写实画面。场景：{scene.get('description', '')}；空间布局：{scene.get('layout', '')}；时间：{scene.get('time', '')}；天气：{scene.get('weather', '')}。"
        f"人物 blocking：{character_text}。道具：{prop_text}。"
        f"摄影机：{camera.get('shot_size', '')}，{camera.get('height', '')}，{camera.get('angle', '')}，焦段感{camera.get('lens', '')}；构图：前景{composition.get('foreground', '')}，中景{composition.get('midground', '')}，背景{composition.get('background', '')}，保留{composition.get('negative_space', '')}。"
        f"灯光：主光{lighting.get('key', '')}，方向{lighting.get('direction', '')}，阴影{lighting.get('shadow', '')}；视觉风格：{style.get('description', '')}。"
        "画面必须完整包含上述人物、手部、眼神、道具接触和空间关系，不添加人物、文字、水印或未授权道具。"
    )


def render_video_provider_prompt(decision: DirectorDecisionIR) -> str:
    lines = [f"从首帧开始，保持人物身份、服装、场景结构和道具状态连续；视频时长 {decision.duration_seconds:.1f} 秒。"]
    for beat in decision.performance_beats:
        lines.append(
            f"{beat['start_time']:.2f}–{beat['end_time']:.2f} 秒，{beat['actor']}：{beat['body_action']}；{beat['hand_action']}；{beat['head_action']}；{beat['eye_action']}；{beat['facial_action']}；道具动作：{beat.get('prop_action', '无')}；结束：{beat['ending_state']}。"
        )
    for dialogue in decision.dialogue_beats:
        phrase = "；".join(f"{item['start_time']:.2f}–{item['end_time']:.2f} 秒说‘{item['text']}’" for item in dialogue.phrase_windows)
        lines.append(f"对白视觉口型：{dialogue.speaker}完整对白仅出现一次：‘{dialogue.authoritative_text}’；{phrase}；不生成音频。")
    for camera in decision.camera_beats:
        lines.append(f"镜头 {camera.start_time:.2f}–{camera.end_time:.2f} 秒：{camera.movement_type}，{camera.direction}，{camera.speed}，{camera.distance_or_scale_change}，目标{camera.target}，由{camera.start_framing}到{camera.end_framing}，{camera.easing}。")
    lines.append(f"结束状态：{canonical(decision.ending_state)}。禁止跳切、额外人物、身份漂移、未授权道具变化和音频生成。")
    return "\n".join(lines)


def quality_gate_v4(*, assets: list[AssetDesignDecisionIR], decisions: list[DirectorDecisionIR], keyframe_prompts: list[str], video_prompts: list[str], llm_calls: int = 0, expected_llm_calls: int = 0) -> dict[str, Any]:
    schema_dump_count = sum(1 for prompt in [render_asset_provider_prompt(asset) for asset in assets] if SCHEMA_DUMP_RE.search(prompt))
    keyframe_internal = sum(1 for prompt in keyframe_prompts if any(ref in prompt for ref in REJECTED_INTERNAL_REFS))
    generic_body = sum(1 for decision in decisions for beat in decision.performance_beats for reason in validate_physical_beats([beat])["reasons"] if "UNRESOLVED" in reason or "INTERNAL" in reason)
    generic_hand = sum(1 for decision in decisions for beat in decision.performance_beats if any(token in _text(beat.get("hand_action")) for token in ("一次明确", "抓取、放置或停顿", "完成一次")))
    generic_eye = sum(1 for decision in decisions for beat in decision.performance_beats if any(token in _text(beat.get("eye_action")) for token in ("当前", "交互目标", "关注点", "线索")))
    ending_unresolved = sum(1 for decision in decisions if validate_ending_state(decision.ending_state)["status"] != "PASS")
    dialogue_reports = [validate_dialogue_plans(decision.dialogue_beats, decision.duration_seconds) for decision in decisions]
    duplicated = sum(len(report["duplicated_windows"]) for report in dialogue_reports)
    overflow = sum(len(report["overflow"]) for report in dialogue_reports)
    source_conflicts = sum(validate_source_facts(decision, decision.source_facts)["count"] for decision in decisions)
    repetition = cross_shot_repetition_audit(decisions)
    timeline = timeline_repetition_audit(decisions)
    unresolved = sum(len(semantic_placeholder_reasons(prompt)) for prompt in keyframe_prompts + video_prompts)
    blockers = schema_dump_count + keyframe_internal + generic_body + generic_hand + generic_eye + ending_unresolved + duplicated + overflow + source_conflicts + unresolved
    return {
        "unresolved_semantic_placeholder": unresolved,
        "generic_action_placeholder": generic_body,
        "generic_hand_action": generic_hand,
        "generic_eye_target": generic_eye,
        "dialogue_duplicated_windows": duplicated,
        "dialogue_duration_overflow": overflow,
        "fixed_timeline_count": timeline["fixed_timeline_count"],
        "cross_shot_action_template_collapse": repetition["status"] == "BLOCK",
        "keyframe_internal_plan_references": keyframe_internal,
        "ending_state_unresolved_fields": ending_unresolved,
        "asset_schema_dump_count": schema_dump_count,
        "source_fact_conflicts": source_conflicts,
        "real_llm_calls": llm_calls,
        "expected_llm_calls": expected_llm_calls,
        "status": "PASS" if blockers == 0 and (expected_llm_calls == 0 or llm_calls == expected_llm_calls) else "BLOCK",
        "blocker_count": blockers + (1 if expected_llm_calls and llm_calls != expected_llm_calls else 0),
    }


__all__ = [
    "AssetDesignDecisionIR", "KeyframeBlockingIR", "DialoguePerformancePlan", "CameraChoreographyIR", "DirectorDecisionIR",
    "estimate_dialogue_duration", "split_dialogue_phrases", "build_dialogue_performance_plan", "validate_source_facts",
    "validate_llm_director_payload",
    "validate_dialogue_plans", "validate_physical_beats", "validate_camera_beats", "validate_keyframe_blocks", "validate_ending_state",
    "cross_shot_repetition_audit", "timeline_repetition_audit", "semantic_placeholder_reasons", "render_asset_provider_prompt",
    "render_keyframe_provider_prompt", "render_video_provider_prompt", "quality_gate_v4", "fingerprint", "SCHEMA_DUMP_RE",
]
