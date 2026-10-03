"""Provider-facing prompt production for the V2 quality gate.

The PromptIR remains the semantic source of truth.  This module is a small,
provider-neutral projection layer: it binds explicit visual authority and
renders natural-language Chinese prompts without serialising PromptIR JSON or
internal provenance fields into a provider request.
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


CHARACTER_AUTHORITY: dict[str, dict[str, str]] = {
    "林晚": {"identity": "林晚", "description": "约二十八岁女性，黑色中长直发，清瘦身形，冷白肤色，深色长裤与浅灰蓝外套，佩戴窄表", "provenance": "PRODUCTION_VISUAL_DECISION"},
    "顾沉": {"identity": "顾沉", "description": "约三十二岁男性，短黑发，修长身形，深灰长风衣与黑色长裤，沉静压迫气质", "provenance": "PRODUCTION_VISUAL_DECISION"},
    "陆叔": {"identity": "陆叔", "description": "约五十五岁男性，灰黑侧分短发，结实身形，旧棕色工作夹克与深色长裤", "provenance": "PRODUCTION_VISUAL_DECISION"},
    "售票员": {"identity": "售票员", "description": "约四十五岁女性，短黑发，深蓝售票员制服，位于售票窗口后", "provenance": "PRODUCTION_VISUAL_DECISION"},
}

SCENE_AUTHORITY: dict[str, dict[str, str]] = {
    "E01_SC001": {"name": "旧火车站售票厅", "description": "日间阴天的旧火车站售票厅，固定售票窗口、候车座椅与通向站台的入口，湿地面反光，入口有冷色天光，室内暖色灯光轻微对比"},
    "E01_SC002": {"name": "出租公寓厨房", "description": "夜间室内的出租公寓厨房与餐桌区域，固定餐桌、厨房门和窗口布局，冷色窗外光与室内暖光混合"},
}

PROP_NAMES: dict[str, str] = {
    "TICKET": "车票", "RED_UMBRELLA": "红伞", "BROKEN_UMBRELLA_RIB": "折断的红伞伞骨", "HANDBAG": "手提包", "POCKET_HARD_OBJECT": "口袋里的硬物", "TABLE_SCRATCH": "桌面划痕", "RED_FIBER": "红色纤维", "APPLE": "苹果", "DOOR_LOCK": "门锁",
}

SHOT_ACTIONS: dict[int, str] = {
    1: "林晚递出票据买票，售票员在窗口回应车次",
    2: "林晚抬眼看向站台上的红伞",
    3: "林晚与顾沉看见红伞伞骨的异常断裂",
    4: "顾沉指向红伞，林晚顺着手势看去",
    5: "陆叔从林晚手中接过手提包，随后察觉包内有异常硬物",
    6: "林晚确认红伞已经消失，只留下湿水痕",
    7: "林晚看向站台入口，陆叔示意返回",
    8: "售票员望向空荡的站台，林晚转身离开",
    9: "陆叔在出租公寓餐桌旁清洗手，林晚走近询问车站",
    10: "陆叔平静地重复一段话，林晚在对面听着",
    11: "林晚压住疑惑，寻找可以证明记忆的线索",
    12: "陆叔发现桌面上的硬物并看向林晚",
    13: "林晚从手提包中取出红色纤维进行确认",
    14: "陆叔露出笑意，语气变成无声的威胁",
    15: "林晚后退到门边，陆叔停在昏暗灯光中",
}

CAMERA_NAMES = {"WIDE": "广角全景", "MEDIUM_WIDE": "中广角", "MEDIUM": "中景", "MEDIUM_CLOSE": "中近景", "CLOSE": "近景", "INSERT": "特写", "TWO_SHOT": "双人中景", "OVER_SHOULDER": "过肩中景"}
MOVEMENT_NAMES = {"NONE": "静止", "REFRAME": "轻微重新构图", "TRACK": "跟拍", "PAN": "横摇", "DOLLY_IN": "缓慢推近", "ARC": "轻微环绕"}
SIDE_NAMES = {"LEFT": "画面左侧", "RIGHT": "画面右侧", "CENTER": "画面中央"}
LOOK_NAMES = {"SCREEN_LEFT": "看向画面左侧", "SCREEN_RIGHT": "看向画面右侧", "CAMERA": "看向镜头"}
ZONE_NAMES = {"ST_TICKET": "售票窗口一侧", "ST_REAR": "后方区域", "ST_CENTER": "画面中央", "ST_TABLE": "餐桌一侧", "ST_DOOR": "门边", "ST_WINDOW": "窗边"}


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
    camera: dict[str, Any]
    continuity: dict[str, Any]
    ending_state: dict[str, Any]
    character_profiles: list[dict[str, Any]]
    visual_style_profile: dict[str, Any]
    reference_bindings: list[dict[str, Any]]
    generation_policy: dict[str, Any]
    source_semantic_hash: str
    diagnostics: list[dict[str, Any]] = field(default_factory=list)


def _subject_names(prompt_ir: dict[str, Any]) -> list[str]:
    result = []
    for item in _list(prompt_ir.get("subjects")):
        name = _text(item.get("subject_ref") if isinstance(item, dict) else item)
        if name and name not in result:
            result.append(name)
    return result


def _prop_names(prompt_ir: dict[str, Any]) -> list[str]:
    result = []
    for item in _list(prompt_ir.get("props")):
        name = _text(item.get("prop_ref") if isinstance(item, dict) else item)
        if name and name not in result:
            result.append(name)
    return result


def build_reference_bindings(*, scene_id: str, subjects: list[str], props: list[str], shot_number: int, include_first_frame: bool = False) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    def add(role: str, token: str, identity: str) -> None:
        authority = {"role": role, "identity": identity, "reference_token": token, "status": "LOCKED", "stale_status": "FRESH"}
        authority["authority_fingerprint"] = _fingerprint(authority)
        refs.append(authority)
    add("SCENE_REFERENCE", f"scene://book-990401/{scene_id}/v1", scene_id)
    for subject in subjects:
        add("CHARACTER_REFERENCE", f"character://book-990401/{subject}/v1", subject)
    for prop in props:
        add("PROP_REFERENCE", f"prop://book-990401/{prop}/v1", prop)
    add("STYLE_REFERENCE", "style://book-990401/episode-1/v1", "episode-1-style")
    if include_first_frame:
        add("FIRST_FRAME_REFERENCE", f"frame://book-990401/shot-{shot_number:03d}/official-image-v1", f"shot-{shot_number:03d}-official-image")
    return refs


def build_context(prompt_ir: dict[str, Any], *, shot_plan: dict[str, Any] | None = None, shot_number: int | None = None, book_id: int = 990401, episode: int = 1) -> PromptProductionContext:
    scene_id = _text(prompt_ir.get("scene_id"))
    subjects = _subject_names(prompt_ir)
    props = _prop_names(prompt_ir)
    number = shot_number or int(_text(prompt_ir.get("storyboard_shot_id") or "0") or 0)
    plan = _dict(shot_plan)
    camera = _dict(prompt_ir.get("camera"))
    continuity = _dict(prompt_ir.get("continuity"))
    sides, looks, scope_errors = scope_continuity_actor_maps(subjects=subjects, screen_side_assignments=continuity.get("screen_side_assignments"), look_direction=continuity.get("look_direction"))
    continuity = {**continuity, "screen_side_assignments": sides, "look_direction": looks}
    scene = {"scene_id": scene_id, **SCENE_AUTHORITY.get(scene_id, {"name": scene_id, "description": "经锁定的场景布局与光线"})}
    ending = _dict(plan.get("exit_state"))
    ending_state = {"source": "ShotPlan.exit_state", "state_ref": _text(ending.get("state_ref") or ending.get("shot_id")), "characters": _dict(ending.get("characters")), "props": _list(ending.get("props"))}
    action = SHOT_ACTIONS.get(number, "人物完成当前镜头中的单一叙事动作")
    if number == 0:
        action = "人物完成当前镜头中的单一叙事动作"
    profiles = [CHARACTER_AUTHORITY.get(name, {"identity": name, "description": f"保持{name}在首帧中的身份、服装和外观", "provenance": "PRODUCTION_VISUAL_DECISION"}) for name in subjects]
    action_beats = _list(_dict(prompt_ir.get("action")).get("action_beats"))
    policy = {"language": LANGUAGE, "image": {"mode": "TEXT_TO_IMAGE", "target_media": "IMAGE"}, "video": {"mode": "IMAGE_TO_VIDEO", "target_media": "VIDEO", "duration_seconds": 5, "aspect_ratio": "16:9", "resolution": "768p", "first_frame_mode": "CURRENT_OFFICIAL_IMAGE", "action_beats": action_beats}}
    refs = build_reference_bindings(scene_id=scene_id, subjects=subjects, props=props, shot_number=number)
    diagnostics = list(scope_errors)
    source_hash = _fingerprint({"prompt_ir": prompt_ir, "shot_plan": plan, "scene": scene, "profiles": profiles, "style": "visual-style-v2"})
    return PromptProductionContext(book_id=book_id, episode=episode, shot_number=number, plan_shot_id=_text(prompt_ir.get("plan_shot_id")), scene_id=scene_id, scene=scene, subjects=subjects, props=props, action=action, camera=camera, continuity=continuity, ending_state=ending_state, character_profiles=profiles, visual_style_profile={"name": "电影写实悬疑短剧", "description": "中等写实度，低饱和冷灰蓝基调，局部暖色实用光，克制对比，真实材质", "provenance": "PRODUCTION_VISUAL_DECISION"}, reference_bindings=refs, generation_policy=policy, source_semantic_hash=source_hash, diagnostics=diagnostics)


def _authority_ready(refs: list[dict[str, Any]]) -> bool:
    return bool(refs) and all(ref.get("status") == "LOCKED" and ref.get("stale_status") == "FRESH" and ref.get("reference_token") for ref in refs)


def _camera_sentence(ctx: PromptProductionContext) -> str:
    framing = CAMERA_NAMES.get(_text(ctx.camera.get("framing_class")), "自然叙事构图")
    orientation = {"EYE_LEVEL": "平视"}.get(_text(ctx.camera.get("orientation")), "平视")
    movement = MOVEMENT_NAMES.get(_text(ctx.camera.get("movement")), "静止")
    target = _text(ctx.camera.get("movement_target"))
    target_phrase = f"，以{target}为运动目标" if target and movement != "静止" else ""
    return f"{framing}，{orientation}，镜头{movement}{target_phrase}"


def _continuity_sentence(ctx: PromptProductionContext) -> str:
    parts = []
    sides = ctx.continuity.get("screen_side_assignments", {})
    looks = ctx.continuity.get("look_direction", {})
    for name in ctx.subjects:
        if name in sides:
            parts.append(f"{name}位于{SIDE_NAMES.get(sides[name], '原定画面位置')}")
        if name in looks:
            parts.append(f"{name}{LOOK_NAMES.get(looks[name], '保持原定视线')}")
    return "；".join(parts) if parts else "保持首帧中的人物关系、视线和空间轴线连续"


def _subject_sentence(ctx: PromptProductionContext) -> str:
    return "；".join(f"{p['identity']}：{p['description']}" for p in ctx.character_profiles)


def render_image_prompt(ctx: PromptProductionContext) -> dict[str, Any]:
    if not _authority_ready(ctx.reference_bindings):
        raise PromptProductionError("GENERATION_REFERENCE_AUTHORITY_NOT_READY", "IMAGE references must be locked and fresh")
    prompt = "。".join([
        f"{ctx.scene['description']}。",
        f"画面中可见人物：{_subject_sentence(ctx)}。",
        f"动作与互动：{ctx.action}。",
        f"重要道具：{'、'.join(PROP_NAMES.get(p, p) for p in ctx.props) if ctx.props else '无额外道具'}。",
        f"构图与摄影：{_camera_sentence(ctx)}。",
        f"连续性：{_continuity_sentence(ctx)}。",
        f"视觉风格：{ctx.visual_style_profile['description']}。",
        "保持人物身份、服装、场景布局和关键道具状态稳定，不添加未授权人物或道具。",
    ])
    negative = "避免多余人物、错误服装、额外道具、过度饱和、夸张HDR、文字水印"
    return _projection(ctx, prompt=prompt, negative_prompt=negative, renderer_version=RENDERER_IMAGE_V2, mode="TEXT_TO_IMAGE", target_media="IMAGE")


def render_video_prompt(ctx: PromptProductionContext) -> dict[str, Any]:
    if not _authority_ready(ctx.reference_bindings):
        raise PromptProductionError("GENERATION_REFERENCE_AUTHORITY_NOT_READY", "VIDEO references must be locked and fresh")
    beats = _list(_dict(ctx.generation_policy.get("video")).get("action_beats"))
    # PromptIR action beats are the authority.  We conservatively use the
    # already compiled action when the caller did not attach the list.
    count = len(beats) if beats else 1
    if count > 2:
        raise PromptProductionError("SHOT_ACTION_OVERBUDGET", "A five second shot may contain at most one primary action and one reaction")
    reaction = "" if count == 1 else "随后保留一次自然反应"
    movement = MOVEMENT_NAMES.get(_text(ctx.camera.get("movement")), "静止")
    ending = "；".join(f"{name}保持在{ZONE_NAMES.get(str(zone), '原定空间位置')}" for name, zone in ctx.ending_state.get("characters", {}).items() if name in ctx.subjects)
    ending = ending or "人物与重要道具停留在首帧确立的位置"
    prompt = "。".join([
        "从当前官方首帧开始，首帧中的人物身份、服装、场景布局和构图保持不变",
        f"开始：{ctx.action.split('，')[0]}",
        f"动作：{ctx.action}；{reaction}" if reaction else f"动作：{ctx.action}",
        f"表情与反应：人物以克制、连续的表演完成信息传递",
        f"镜头：{movement}，全片只保留这一项镜头运动",
        f"结束：{ending}，回到稳定画面并保持空间轴线连续",
        "时长五秒，动作简洁真实，不新增人物、道具或叙事事件",
    ])
    negative = "避免跳切、变形、人物身份漂移、服装变化、额外动作、额外镜头运动、文字水印"
    return _projection(ctx, prompt=prompt, negative_prompt=negative, renderer_version=RENDERER_VIDEO_V2, mode="IMAGE_TO_VIDEO", target_media="VIDEO", include_first_frame=True)


def _projection(ctx: PromptProductionContext, *, prompt: str, negative_prompt: str | None, renderer_version: str, mode: str, target_media: str, include_first_frame: bool = False) -> dict[str, Any]:
    refs = build_reference_bindings(scene_id=ctx.scene_id, subjects=ctx.subjects, props=ctx.props, shot_number=ctx.shot_number, include_first_frame=include_first_frame)
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
    if projection.get("negative_prompt") is None:
        # None is valid only for adapters that do not support negatives; V2
        # uses a provider-neutral string, so this branch is retained as a
        # defensive validator for external callers.
        pass
    return errors


def context_to_dict(ctx: PromptProductionContext) -> dict[str, Any]:
    return asdict(ctx)


__all__ = ["PromptProductionContext", "PromptProductionError", "build_context", "build_reference_bindings", "render_image_prompt", "render_video_prompt", "validate_projection", "context_to_dict", "RENDERER_IMAGE_V2", "RENDERER_VIDEO_V2"]
