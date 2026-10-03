"""Dataset-agnostic Prompt Production V2.

This module is a projection boundary. It consumes PromptIR, ShotPlan,
ShotDirection and explicit canonical authority records supplied by callers.
No screenplay names, scene ids, prop labels, or shot-number story facts live
in production code.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from core.storyboard_visual_semantics import scope_continuity_actor_maps

RENDERER_IMAGE_V2 = "image_prompt_renderer_v2"
RENDERER_VIDEO_V2 = "video_i2v_prompt_renderer_v2"
LANGUAGE = "zh-CN"
_INTERNAL_TOKEN = re.compile(r"(?:action_id|beat_ref|event_ref|axis_ref|projection_origin|asset_identity_ref|schema_version|shot_plan|prompt_ir|CONTINUITY_ACTOR|GENERATION_|[A-Z][A-Z0-9_]{3,})")
_PLACEHOLDER = re.compile(r"(?:TODO|TBD|PLACEHOLDER|待补充|未定义|<[^>]+>|\[\[.+?\]\])", re.I)
CAMERA_NAMES = {"WIDE": "广角全景", "MEDIUM_WIDE": "中广角", "MEDIUM": "中景", "MEDIUM_CLOSE": "中近景", "CLOSE": "近景", "INSERT": "特写", "TWO_SHOT": "双人中景", "OVER_SHOULDER": "过肩中景"}
MOVEMENT_NAMES = {"NONE": "静止", "REFRAME": "轻微重新构图", "TRACK": "跟拍", "PAN": "横摇", "DOLLY_IN": "缓慢推近", "ARC": "轻微环绕"}
SIDE_NAMES = {"LEFT": "画面左侧", "RIGHT": "画面右侧", "CENTER": "画面中央"}
LOOK_NAMES = {"SCREEN_LEFT": "看向画面左侧", "SCREEN_RIGHT": "看向画面右侧", "CAMERA": "看向镜头"}


class PromptProductionError(ValueError):
    def __init__(self, code: str, message: str, *, diagnostics: list[dict[str, Any]] | None = None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.diagnostics = diagnostics or [{"code": code, "message": message, "severity": "blocked"}]


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _names(items: Any, *, key: str = "subject_ref") -> list[str]:
    result: list[str] = []
    for item in _list(items):
        name = _text(item.get(key) if isinstance(item, dict) else item)
        if name and name not in result:
            result.append(name)
    return result


def _action_beats(prompt_ir: dict[str, Any], shot_plan: dict[str, Any], shot_direction: dict[str, Any]) -> list[dict[str, Any]]:
    fallback: list[dict[str, Any]] = []
    for source in (prompt_ir, shot_direction, shot_plan):
        action = _dict(source.get("action"))
        beats = _list(action.get("action_beats")) or _list(source.get("action_beats"))
        if beats:
            normalized = [dict(beat) for beat in beats if isinstance(beat, dict)]
            if not fallback:
                fallback = normalized
            if any(_text(item.get("description") or item.get("action") or item.get("text") or item.get("summary")) for item in normalized):
                return normalized
    return fallback


def _action_text(beats: list[dict[str, Any]], subjects: list[str]) -> str:
    parts: list[str] = []
    actors: list[str] = []
    for beat in beats:
        text = _text(beat.get("description") or beat.get("action") or beat.get("text") or beat.get("summary"))
        if text and text not in parts:
            parts.append(text)
        for actor in _names(beat.get("actor_refs") or beat.get("actors"), key="name"):
            if actor not in actors:
                actors.append(actor)
    if parts:
        return "；".join(parts)
    visible = "、".join(actors or subjects)
    return f"{visible}完成当前镜头的单一叙事动作" if visible else "完成当前镜头的单一叙事动作"


def _authority_record(raw: Any, *, identity: str, fallback_description: str = "保持首帧中已锁定的身份与外观") -> dict[str, Any]:
    data = _dict(raw)
    description = _text(data.get("visual_description") or data.get("description") or data.get("appearance") or fallback_description)
    return {"identity": _text(data.get("identity") or data.get("name") or identity), "description": description, "authority_id": _text(data.get("authority_id") or data.get("reference") or identity), "authority_fingerprint": _text(data.get("authority_fingerprint") or _fingerprint(data)), "source": _text(data.get("source") or "CANONICAL_VISUAL_AUTHORITY")}


@dataclass
class PromptProductionContext:
    book_id: int
    episode: int
    shot_number: int
    plan_shot_id: str
    scene_id: str
    scene: dict[str, Any]
    subjects: list[str]
    props: list[str]
    action: str
    action_beats: list[dict[str, Any]]
    action_actors: list[str]
    camera: dict[str, Any]
    continuity: dict[str, Any]
    ending_state: dict[str, Any]
    character_profiles: list[dict[str, Any]]
    visual_style_profile: dict[str, Any]
    reference_bindings: list[dict[str, Any]]
    generation_policy: dict[str, Any]
    authority_provenance: dict[str, Any]
    source_semantic_hash: str
    diagnostics: list[dict[str, Any]] = field(default_factory=list)


def build_reference_bindings(*, book_id: int, episode: int, scene_id: str, subjects: list[str], props: list[str], shot_number: int, authority: dict[str, Any], include_first_frame: bool = False) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    ref_authority = _dict(authority.get("references"))

    def add(role: str, identity: str, fallback_token: str) -> None:
        raw = _dict(ref_authority.get(f"{role}:{identity}") or ref_authority.get(identity))
        item = {"role": role, "identity": identity, "reference_token": _text(raw.get("reference_token") or fallback_token), "status": _text(raw.get("status") or "LOCKED"), "stale_status": _text(raw.get("stale_status") or "FRESH"), "authority_id": _text(raw.get("authority_id") or identity)}
        item["authority_fingerprint"] = _text(raw.get("authority_fingerprint") or _fingerprint(item))
        refs.append(item)

    add("SCENE_REFERENCE", scene_id, f"scene://book-{book_id}/{scene_id}/v1")
    for subject in subjects:
        add("CHARACTER_REFERENCE", subject, f"character://book-{book_id}/{subject}/v1")
    for prop in props:
        add("PROP_REFERENCE", prop, f"prop://book-{book_id}/{prop}/v1")
    style_id = _text(_dict(authority.get("visual_style")).get("identity") or f"episode-{episode}-style")
    add("STYLE_REFERENCE", style_id, f"style://book-{book_id}/episode-{episode}/v1")
    if include_first_frame:
        add("FIRST_FRAME_REFERENCE", f"shot-{shot_number:03d}-official-image", f"frame://book-{book_id}/shot-{shot_number:03d}/official-image-v1")
    return refs


def build_context(prompt_ir: dict[str, Any], *, shot_plan: dict[str, Any] | None = None, shot_direction: dict[str, Any] | None = None, authority: dict[str, Any] | None = None, shot_number: int | None = None, book_id: int = 0, episode: int = 0) -> PromptProductionContext:
    plan, direction, auth = _dict(shot_plan), _dict(shot_direction), _dict(authority)
    scene_id = _text(prompt_ir.get("scene_id") or plan.get("scene_id"))
    prompt_subjects, plan_subjects, direction_subjects = _names(prompt_ir.get("subjects")), _names(plan.get("subjects")), _names(direction.get("subjects"))
    subjects = prompt_subjects or plan_subjects or direction_subjects
    upstream_sets = [set(item) for item in (prompt_subjects, plan_subjects, direction_subjects) if item]
    if upstream_sets and any(item != upstream_sets[0] for item in upstream_sets[1:]):
        raise PromptProductionError("SHOT_SEMANTIC_ACTOR_INTEGRITY", "PromptIR, ShotPlan and ShotDirection actor sets disagree")
    legitimate = set(subjects)
    props = _names(prompt_ir.get("props"), key="prop_ref") or _names(plan.get("props"), key="prop_ref")
    number = shot_number or int(_text(prompt_ir.get("storyboard_shot_id") or "0") or 0)
    camera = _dict(prompt_ir.get("camera") or direction.get("camera") or plan.get("camera_state"))
    continuity_raw = _dict(prompt_ir.get("continuity"))
    sides, looks, scope_errors = scope_continuity_actor_maps(subjects=subjects, screen_side_assignments=continuity_raw.get("screen_side_assignments"), look_direction=continuity_raw.get("look_direction"))
    continuity = {**continuity_raw, "screen_side_assignments": sides, "look_direction": looks}
    # ShotDirection is the downstream, shot-scoped authority.  It may carry a
    # deliberately scoped ending state even when a legacy ShotPlan snapshot
    # still contains all scene participants.
    ending = _dict(direction.get("ending_state") or plan.get("exit_state"))
    ending_characters = _dict(ending.get("characters"))
    explicit_offscreen = set(_names(plan.get("offscreen_actors"), key="name") + _names(direction.get("offscreen_actors"), key="name"))
    ending_bad = sorted((set(ending_characters) - legitimate) - explicit_offscreen)
    beats = _action_beats(prompt_ir, plan, direction)
    action_actors: list[str] = []
    for beat in beats:
        for actor in _names(beat.get("actor_refs") or beat.get("actors"), key="name"):
            if actor not in action_actors:
                action_actors.append(actor)
    action_bad = sorted(set(action_actors) - legitimate)
    target = _text(camera.get("movement_target"))
    target_bad = bool(target and target not in legitimate and target not in explicit_offscreen)
    diagnostics: list[dict[str, Any]] = [{"code": item["code"], "stage": "input", "detected": True, "remediated": True, "survives_to_provider": False, "actor": item.get("actor")} for item in scope_errors]
    if action_bad:
        diagnostics.append({"code": "SHOT_ACTION_ACTOR_MISMATCH", "stage": "cross_layer", "detected": True, "remediated": False, "survives_to_provider": True, "actors": action_bad})
    if ending_bad:
        diagnostics.append({"code": "VIDEO_ENDING_STATE_ACTOR_MISMATCH", "stage": "cross_layer", "detected": True, "remediated": False, "survives_to_provider": True, "actors": ending_bad})
    if target_bad:
        diagnostics.append({"code": "CAMERA_TARGET_OUT_OF_SCOPE", "stage": "cross_layer", "detected": True, "remediated": False, "survives_to_provider": True, "actor": target})
    if action_bad or ending_bad or target_bad:
        raise PromptProductionError("SHOT_SEMANTIC_ACTOR_INTEGRITY", "cross-layer actor integrity failed", diagnostics=diagnostics)
    scene_auth = _authority_record(_dict(auth.get("scenes")).get(scene_id), identity=scene_id, fallback_description="保持 canonical SceneIdentity 的空间布局、时间和光线")
    characters_auth, props_auth = _dict(auth.get("characters")), _dict(auth.get("props"))
    profiles = [_authority_record(characters_auth.get(name), identity=name) for name in subjects]
    style = _authority_record(auth.get("visual_style"), identity="visual-style")
    ending_state = {"source": _text(ending.get("source") or "ShotPlan.exit_state"), "state_ref": _text(ending.get("state_ref") or ending.get("shot_id")), "characters": {name: value for name, value in ending_characters.items() if name in legitimate or name in explicit_offscreen}, "props": _list(ending.get("props"))}
    policy = {"language": LANGUAGE, "image": {"mode": "TEXT_TO_IMAGE", "target_media": "IMAGE"}, "video": {"mode": "IMAGE_TO_VIDEO", "target_media": "VIDEO", "duration_seconds": 5, "aspect_ratio": "16:9", "resolution": "768p", "first_frame_mode": "CURRENT_OFFICIAL_IMAGE", "action_beats": beats}}
    refs = build_reference_bindings(book_id=book_id, episode=episode, scene_id=scene_id, subjects=subjects, props=props, shot_number=number, authority={**auth, "visual_style": style})
    provenance = {"character": {item["identity"]: item for item in profiles}, "scene": scene_auth, "prop": {name: _authority_record(props_auth.get(name), identity=name) for name in props}, "action": {"source": "PromptIR/ShotPlan/ShotDirection", "authority_fingerprint": _fingerprint(beats)}, "camera": {"source": "PromptIR/ShotPlan/ShotDirection", "authority_fingerprint": _fingerprint(camera)}, "continuity": {"source": "PromptIR", "authority_fingerprint": _fingerprint(continuity)}, "ending_state": {"source": ending_state["source"], "authority_fingerprint": _fingerprint(ending_state)}, "visual_style": style}
    source_hash = _fingerprint({"prompt_ir": prompt_ir, "shot_plan": plan, "shot_direction": direction, "authority": auth})
    return PromptProductionContext(book_id=book_id, episode=episode, shot_number=number, plan_shot_id=_text(prompt_ir.get("plan_shot_id") or plan.get("plan_shot_id")), scene_id=scene_id, scene=scene_auth, subjects=subjects, props=props, action=_action_text(beats, subjects), action_beats=beats, action_actors=action_actors or list(subjects), camera=camera, continuity=continuity, ending_state=ending_state, character_profiles=profiles, visual_style_profile=style, reference_bindings=refs, generation_policy=policy, authority_provenance=provenance, source_semantic_hash=source_hash, diagnostics=diagnostics)


def _authority_ready(refs: list[dict[str, Any]]) -> bool:
    return bool(refs) and all(ref.get("status") == "LOCKED" and ref.get("stale_status") == "FRESH" and ref.get("reference_token") for ref in refs)


def validate_semantic_integrity(ctx: PromptProductionContext) -> list[dict[str, Any]]:
    legitimate = set(ctx.subjects)
    result: list[dict[str, Any]] = []
    if set(ctx.action_actors) - legitimate:
        result.append({"code": "SHOT_ACTION_ACTOR_MISMATCH", "actors": sorted(set(ctx.action_actors) - legitimate)})
    if set(ctx.ending_state.get("characters", {})) - legitimate:
        result.append({"code": "VIDEO_ENDING_STATE_ACTOR_MISMATCH", "actors": sorted(set(ctx.ending_state["characters"]) - legitimate)})
    target = _text(ctx.camera.get("movement_target"))
    if target and target not in legitimate:
        result.append({"code": "CAMERA_TARGET_OUT_OF_SCOPE", "actor": target})
    ref_actors = {ref.get("identity") for ref in ctx.reference_bindings if ref.get("role") == "CHARACTER_REFERENCE"}
    if ref_actors != legitimate:
        result.append({"code": "REFERENCE_ACTOR_MISMATCH", "expected": sorted(legitimate), "actual": sorted(ref_actors)})
    return result


def compare_semantic_pair(image_ctx: PromptProductionContext, video_ctx: PromptProductionContext) -> list[dict[str, Any]]:
    """Compare IMAGE and IMAGE_TO_VIDEO semantic sets before provider use."""
    mismatches: list[dict[str, Any]] = []
    for field, left, right in (
        ("scene identity", image_ctx.scene_id, video_ctx.scene_id),
        ("visible actor set", sorted(image_ctx.subjects), sorted(video_ctx.subjects)),
        ("prop set", sorted(image_ctx.props), sorted(video_ctx.props)),
        ("action actor set", sorted(image_ctx.action_actors), sorted(video_ctx.action_actors)),
        ("camera target", _text(image_ctx.camera.get("movement_target")), _text(video_ctx.camera.get("movement_target"))),
        ("ending actor set", sorted(image_ctx.ending_state.get("characters", {})), sorted(video_ctx.ending_state.get("characters", {}))),
    ):
        if left != right:
            mismatches.append({"code": "IMAGE_VIDEO_ACTOR_SET_MISMATCH" if "actor" in field else "IMAGE_VIDEO_SEMANTIC_MISMATCH", "field": field, "image": left, "video": right})
    return mismatches


def _camera_sentence(ctx: PromptProductionContext) -> str:
    framing = CAMERA_NAMES.get(_text(ctx.camera.get("framing_class")), "自然叙事构图")
    movement = MOVEMENT_NAMES.get(_text(ctx.camera.get("movement")), "静止")
    target = _text(ctx.camera.get("movement_target"))
    return f"{framing}，平视，镜头{movement}" + (f"，以{target}为运动目标" if target and movement != "静止" else "")


def _continuity_sentence(ctx: PromptProductionContext) -> str:
    parts: list[str] = []
    for name in ctx.subjects:
        if name in ctx.continuity.get("screen_side_assignments", {}):
            parts.append(f"{name}位于{SIDE_NAMES.get(ctx.continuity['screen_side_assignments'][name], '原定画面位置')}")
        if name in ctx.continuity.get("look_direction", {}):
            parts.append(f"{name}{LOOK_NAMES.get(ctx.continuity['look_direction'][name], '保持原定视线')}")
    return "；".join(parts) if parts else "保持首帧中的人物关系、视线和空间轴线连续"


def _subject_sentence(ctx: PromptProductionContext) -> str:
    return "；".join(f"{item['identity']}：{item['description']}" for item in ctx.character_profiles)


def render_image_prompt(ctx: PromptProductionContext) -> dict[str, Any]:
    integrity = validate_semantic_integrity(ctx)
    if integrity:
        raise PromptProductionError("SHOT_SEMANTIC_ACTOR_INTEGRITY", "semantic integrity failed", diagnostics=integrity)
    if not _authority_ready(ctx.reference_bindings):
        raise PromptProductionError("GENERATION_REFERENCE_AUTHORITY_NOT_READY", "IMAGE references must be locked and fresh")
    props = "、".join(item["description"] for item in ctx.authority_provenance["prop"].values()) if ctx.authority_provenance["prop"] else "无额外道具"
    prompt = "。".join([f"{ctx.scene['description']}。", f"画面中可见人物：{_subject_sentence(ctx)}。", f"动作与互动：{ctx.action}。", f"重要道具：{props}。", f"构图与摄影：{_camera_sentence(ctx)}。", f"连续性：{_continuity_sentence(ctx)}。", f"视觉风格：{ctx.visual_style_profile['description']}。", "保持人物身份、服装、场景布局和关键道具状态稳定，不添加未授权人物或道具。"])
    return _projection(ctx, prompt=prompt, negative_prompt="避免多余人物、错误服装、额外道具、过度饱和、夸张HDR、文字水印", renderer_version=RENDERER_IMAGE_V2, mode="TEXT_TO_IMAGE", target_media="IMAGE")


def render_video_prompt(ctx: PromptProductionContext) -> dict[str, Any]:
    integrity = validate_semantic_integrity(ctx)
    if integrity:
        raise PromptProductionError("SHOT_SEMANTIC_ACTOR_INTEGRITY", "semantic integrity failed", diagnostics=integrity)
    if not _authority_ready(ctx.reference_bindings):
        raise PromptProductionError("GENERATION_REFERENCE_AUTHORITY_NOT_READY", "VIDEO references must be locked and fresh")
    count = len(ctx.action_beats) or 1
    if count > 2:
        raise PromptProductionError("SHOT_ACTION_OVERBUDGET", "A five second shot may contain at most one primary action and one reaction")
    reaction = "随后保留一次自然反应" if count == 2 else ""
    movement = MOVEMENT_NAMES.get(_text(ctx.camera.get("movement")), "静止")
    ending = "；".join(f"{name}保持在原定空间位置" for name in ctx.ending_state.get("characters", {}) if name in ctx.subjects) or "人物与重要道具停留在首帧确立的位置"
    prompt = "。".join(["从当前官方首帧开始，首帧中的人物身份、服装、场景布局和构图保持不变", f"开始：{ctx.action.split('，')[0]}", f"动作：{ctx.action}；{reaction}" if reaction else f"动作：{ctx.action}", "表情与反应：人物以克制、连续的表演完成信息传递", f"镜头：{movement}，全片只保留这一项镜头运动", f"结束：{ending}，回到稳定画面并保持空间轴线连续", "时长五秒，动作简洁真实，不新增人物、道具或叙事事件"])
    return _projection(ctx, prompt=prompt, negative_prompt="避免跳切、变形、人物身份漂移、服装变化、额外动作、额外镜头运动、文字水印", renderer_version=RENDERER_VIDEO_V2, mode="IMAGE_TO_VIDEO", target_media="VIDEO", include_first_frame=True)


def _projection(ctx: PromptProductionContext, *, prompt: str, negative_prompt: str | None, renderer_version: str, mode: str, target_media: str, include_first_frame: bool = False) -> dict[str, Any]:
    refs = build_reference_bindings(book_id=ctx.book_id, episode=ctx.episode, scene_id=ctx.scene_id, subjects=ctx.subjects, props=ctx.props, shot_number=ctx.shot_number, authority={"visual_style": ctx.visual_style_profile, "references": {ref["role"] + ":" + ref["identity"]: ref for ref in ctx.reference_bindings}}, include_first_frame=include_first_frame)
    projection = {"prompt": prompt, "negative_prompt": negative_prompt, "language": LANGUAGE, "reference_bindings": refs, "provider_parameters": {"mode": mode, "target_media": target_media, **(_dict(ctx.generation_policy.get("video")) if target_media == "VIDEO" else {})}, "semantic_source_hash": ctx.source_semantic_hash, "renderer_version": renderer_version}
    projection["generation_payload_fingerprint"] = _fingerprint(projection)
    return projection


def validate_projection(projection: dict[str, Any]) -> list[dict[str, Any]]:
    prompt = _text(projection.get("prompt"))
    errors: list[dict[str, Any]] = []
    if projection.get("language") != LANGUAGE:
        errors.append({"code": "PROMPT_LANGUAGE_INVALID", "severity": "blocked"})
    if _INTERNAL_TOKEN.search(prompt):
        errors.append({"code": "PROVIDER_PROMPT_INTERNAL_TOKEN_LEAK", "severity": "blocked"})
    if _PLACEHOLDER.search(prompt):
        errors.append({"code": "PROMPT_PLACEHOLDER_LEAK", "severity": "blocked"})
    return errors


def context_to_dict(ctx: PromptProductionContext) -> dict[str, Any]:
    return asdict(ctx)


__all__ = ["PromptProductionContext", "PromptProductionError", "build_context", "build_reference_bindings", "render_image_prompt", "render_video_prompt", "validate_projection", "validate_semantic_integrity", "compare_semantic_pair", "context_to_dict", "RENDERER_IMAGE_V2", "RENDERER_VIDEO_V2"]
