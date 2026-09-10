"""Model Adapter — 将 Prompt IR 适配到不同图像/视频生成模型。

参考方案：AI 影视生产系统 V1.0：Shot Schema / Prompt IR / Model Adapter
分层。

这个模块的职责不是再次调用 LLM，而是把已经规则化的 ``ShotIR``
稳定序列化成模型可消费的静态提示词、运动提示词和负面约束。LLM
Polish 可以在它之后做自然语言润色，但 Adapter 输出必须能作为确定性
baseline 和兜底结果存在。
"""

from __future__ import annotations

import re
from typing import Any

from core.prompt_ir import ShotIR


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()


STORYBOARD_ASSET_TEMPLATE_FRAGMENTS = (
    "人物定妆设定板",
    "角色设定板",
    "人物分镜精调定妆设定板",
    "展示同一个角色的六个视角",
    "六个视角",
    "上排为脸部特写",
    "下排为全身展示",
    "正面、侧面、45度",
    "正面、侧面、背面",
    "保持面部一致性",
    "发型一致性",
    "服装一致性",
    "体型一致性",
    "适合影视角色建模",
    "标准六视图参考",
    "六个极正视角",
    "2行3列",
    "纯白色纯净背景",
    "专业产品影棚摄影",
)


def _clean_visual_prompt_text(value: object) -> str:
    text = _clean_text(value)
    terminal_punctuation = text[-1] if text and text[-1] in "。！？" else ""
    # Bracketed stage directions are screenplay residue, not a hard length
    # bounded field.  The previous 300-character cap left long action blocks
    # wrapped in ``[...]`` untouched, which then tripped the compiler's
    # screenplay-residue gate during deterministic adapter fallback.  Strip
    # the wrappers for any bounded prompt-sized block while preserving its
    # visual content; the downstream label/punctuation normalisation remains
    # responsible for removing instruction syntax inside the block.
    text = re.sub(r"【(.*?)】", r"\1", text)
    text = re.sub(r"\[(.*?)\]", r"\1", text)
    text = re.sub(r"（(?:大笑|停顿|沉默)）", "", text)
    text = re.sub(r"\blegacy-[A-Za-z0-9_-]{1,80}\b", "", text)
    text = re.sub(r"Temporary cloned scene asset for source book \d+\.?", "", text)
    text = text.replace("真实项目克隆验证场景，保持原镜头空间、光线和氛围", "")
    text = text.replace("真实项目克隆验证场景", "")
    text = text.replace("画面切到", "同一连续画面中转向")
    text = text.replace("画面切出", "画面自然结束")
    text = text.replace("画面切，", "画面转为")
    text = text.replace("画面切：", "画面转为")
    text = text.replace("画面切 ", "画面转为")
    text = text.replace("画面切", "画面转为")
    text = re.sub(r"画面开场[：:，,\s]*", "", text)
    text = re.sub(r"镜头开场[：:，,\s]*", "", text)
    text = text.replace("镜头切到", "同一连续镜头中转向")
    text = text.replace("镜头切出", "镜头自然结束")
    text = text.replace("镜头切，", "镜头转为")
    text = text.replace("镜头切：", "镜头转为")
    text = text.replace("镜头切", "镜头转为")
    text = text.replace("切到", "连续转向")
    text = text.replace("切出", "自然结束")
    text = text.replace("说出对白", "开口回应")
    text = text.replace("念出对白", "开口回应")
    text = text.replace("对白内容", "口型与表情")
    text = text.replace("对白", "口型动作")
    text = text.replace("台词内容", "口型与表情")
    text = text.replace("台词", "口型动作")
    text = re.sub(r"镜头推进为[：:，,\s]*", "镜头继续推进到", text)
    text = re.sub(r"镜头运动为[：:，,\s]*", "镜头运动中", text)
    text = re.sub(r"运动过程为[：:，,\s]*", "运动过程中", text)
    text = re.sub(r"动作过程为[：:，,\s]*", "动作过程中", text)
    text = re.sub(r"动作推进为[：:，,\s]*", "随后", text)
    text = text.replace("：", "，").replace(":", "，")
    parts = [item.strip() for item in re.split(r"[。；;\n\r]+", text) if item.strip()]
    kept_parts = [
        part
        for part in parts
        if not any(fragment in part for fragment in STORYBOARD_ASSET_TEMPLATE_FRAGMENTS)
    ]
    result = _clean_text("。".join(kept_parts) if parts else text)
    if terminal_punctuation and result and result[-1:] not in "。！？":
        result += terminal_punctuation
    return result


def sanitize_machine_prompt_text(value: object) -> str:
    """Clean director/script residue from a model-facing machine prompt field."""

    return _clean_visual_prompt_text(value)


def _first_non_empty(*values: object) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""


def _truncate(text: str, limit: int = 90) -> str:
    text = _clean_text(text)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip("，。；、 ") + "…"


def _polish_asset_fact_text(text: str) -> str:
    value = _clean_visual_prompt_text(text)
    value = value.replace("适合影视化建模", "")
    value = value.replace("适合影视角色建模", "")
    value = value.replace("人物为，", "人物为")
    value = value.replace("身份是，", "身份是")
    value = value.replace("气质，", "气质")
    value = value.replace("外貌特征，", "")
    value = value.replace("发型，", "发型")
    value = value.replace("服装，", "服装")
    value = value.replace("基础服装材质", "基础服装，材质")
    value = re.sub(r"，{2,}", "，", value)
    value = re.sub(r"人物为，?岁的，?身份是，?气质", "", value)
    return _clean_text(value).strip("，。；、 ")


def _binding_label(binding) -> str:
    name = _clean_text(getattr(binding, "asset_name", ""))
    token = _clean_text(getattr(binding, "reference_token", ""))
    if token and name:
        return f"{name}（{token}）"
    return token or name


def _scene_label(ir: ShotIR) -> str:
    """Return an audit-friendly scene label that preserves the exact shot scene_name."""

    exact_name = _clean_text(ir.scene_name)
    binding = _binding_label(ir.scene_binding)
    if exact_name and binding and exact_name not in binding:
        return f"{exact_name}（绑定资产：{binding}）"
    return binding or exact_name or "当前场景"


def _binding_fact(binding) -> str:
    parts = []
    asset_type = _clean_text(getattr(binding, "asset_type", ""))
    raw_parts = [item for item in (getattr(binding, "canonical_prompt_parts", []) or []) if isinstance(item, dict)]
    if asset_type == "scene":
        by_key = {_clean_text(item.get("key")).lower(): item for item in raw_parts}
        scene_parts: list[str] = []
        for key, limit in (
            ("canonical_description", 150),
            ("description", 150),
            ("canonical_lighting_mood", 300),
            ("lighting_mood", 300),
        ):
            item = by_key.get(key)
            if not isinstance(item, dict):
                continue
            text = _truncate(_polish_asset_fact_text(item.get("text")), limit)
            if text and text not in scene_parts:
                scene_parts.append(text)
            if len(scene_parts) >= 2:
                break
        if scene_parts:
            return "；".join(scene_parts)

    if asset_type == "character":
        priority = {
            "canonical_hairstyle": 0,
            "hair_style": 0,
            "canonical_outfit": 1,
            "refined_outfit": 1,
            "outfit_prompt": 1,
            "canonical_makeup_expression": 2,
            "makeup_spec": 2,
            "canonical_scene_effects": 3,
            "scene_prompt_zh": 3,
            "canonical_accessories": 4,
            "refined_accessories": 4,
            "canonical_identity": 5,
            "canonical_temperament": 6,
            "canonical_appearance": 7,
            "canonical_consistency": 8,
            "consistency_notes": 8,
        }
        raw_parts = sorted(
            raw_parts,
            key=lambda item: priority.get(_clean_text(item.get("key")).lower(), 20),
        )

    for item in raw_parts:
        if not isinstance(item, dict):
            continue
        key = _clean_text(item.get("key")).lower()
        if asset_type == "character" and key in {"variant_scope", "variant_name", "stage_name", "shot_ids"}:
            continue
        if asset_type == "character" and key == "canonical_appearance" and parts:
            continue
        text = _polish_asset_fact_text(item.get("text"))
        if text:
            parts.append(text)
        max_parts = 1 if asset_type == "scene" else 2
        if len(parts) >= max_parts:
            break
    if not parts:
        raw = _polish_asset_fact_text(getattr(binding, "authority_prompt_raw", ""))
        if raw:
            parts.append(raw)
    limit = 180 if asset_type == "scene" else 90
    return _truncate("；".join(parts), limit)


def _visual_fact_label(fact) -> str:
    asset_name = _clean_visual_prompt_text(getattr(fact, "asset_name", ""))
    fact_text = _clean_visual_prompt_text(getattr(fact, "fact", ""))
    if asset_name and fact_text:
        return f"{asset_name}：{fact_text}"
    return fact_text


def _append_unique_prompt_part(parts: list[str], value: str, *, limit: int = 120) -> None:
    text = _truncate(_clean_visual_prompt_text(value), limit)
    if not text:
        return
    normalized = re.sub(r"\s+", "", text)
    if any(normalized and normalized in re.sub(r"\s+", "", existing) for existing in parts):
        return
    parts.append(text)


def _camera_motion_zh(ir: ShotIR) -> str:
    movement = _clean_text(ir.camera_movement).lower().replace("_", "-")
    speed = _clean_text(ir.camera_speed).lower()
    # Accept composed structured values (e.g. ``slow_push_in``) while keeping
    # provider-facing text in the canonical camera vocabulary.
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
        "static": "固定不动",
        "push-in": f"{speed_prefix}向主体推进",
        "pushin": f"{speed_prefix}向主体推进",
        "pull-out": f"{speed_prefix}后撤拉开空间",
        "pan-left": f"{speed_prefix}向左摇移",
        "pan-right": f"{speed_prefix}向右摇移",
        "tilt-up": f"{speed_prefix}向上摇移",
        "tilt-down": f"{speed_prefix}向下摇移",
        "dolly": f"{speed_prefix}滑轨移动",
        "zoom": f"{speed_prefix}变焦",
        "handheld": "轻微手持晃动但保持可控",
        "orbit-left": f"{speed_prefix}向左环绕主体",
        "orbit-right": f"{speed_prefix}向右环绕主体",
    }
    return mapping.get(movement, f"{speed_prefix}{ir.camera_movement or '稳定运镜'}")


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


def _declared_action_timeline(ir: ShotIR) -> str:
    """Serialize only actions declared in the structured shot plan.

    ``action_process`` remains a legacy fallback for records that have not yet
    been migrated to action beats; once beats exist, it must not leak extra
    prose actions into a model-facing motion prompt.
    """
    beats = []
    for item in ir.action_beats or []:
        if not isinstance(item, dict):
            continue
        text = _clean_visual_prompt_text(item.get("description") or item.get("action") or "")
        if text:
            beats.append(_truncate(text, 120))
    if beats:
        return "，随后".join(beats)
    return _truncate(_clean_visual_prompt_text(ir.action_process), 150)


class ModelAdapter:
    """模型适配器基类"""

    def serialize_static_sections(self, ir: ShotIR) -> dict[str, Any]:
        return {}

    def serialize_static(self, ir: ShotIR) -> str:
        raise NotImplementedError

    def serialize_motion(self, ir: ShotIR) -> str:
        raise NotImplementedError

    def serialize_negative(self, ir: ShotIR) -> str:
        raise NotImplementedError


class SDAdapter(ModelAdapter):
    """Stable Diffusion 适配器 — 自然中文 + 负面提示词"""

    def serialize_static(self, ir: ShotIR) -> str:
        sections = []
        if ir.scene_binding.asset_name:
            sections.append(f"场景：{ir.scene_binding.asset_name}")
        for char in ir.character_bindings:
            if char.asset_name:
                variant = f"（{char.variant_name}）" if char.variant_name else ""
                sections.append(f"人物：{char.asset_name}{variant}")
        if ir.lighting:
            sections.append(f"光影：{ir.lighting}")
        if ir.emotion_arc.start:
            sections.append(f"情绪：{ir.emotion_arc.start}")
        return "，".join(sections) if sections else ir.start_state

    def serialize_motion(self, ir: ShotIR) -> str:
        parts = []
        camera_desc = ir.camera_movement
        if ir.camera_speed in ("slow", "medium", "fast"):
            speed_zh = {"slow": "缓慢", "medium": "中速", "fast": "快速"}.get(ir.camera_speed, "")
            camera_desc = f"{speed_zh}{ir.camera_movement}"
        parts.append(f"镜头{camera_desc}")
        if ir.action_process:
            parts.append(ir.action_process)
        return "，".join(parts)

    def serialize_negative(self, ir: ShotIR) -> str:
        defaults = ["低质量", "模糊", "变形", "水印"]
        return "，".join(defaults)


class StoryboardChineseAdapter(ModelAdapter):
    """中文影视生产通用 Adapter。

    适用于即梦、可灵、Seedance 这类以中文自然语言为主的图像/视频
    生成链路。输出强调：资产锚点、首帧画面、动作时间线、一致性约束。
    """

    negative_defaults = [
        "低质量",
        "模糊",
        "字幕",
        "水印",
        "logo",
        "人物变形",
        "多余手指",
        "错误服装",
        "错误场景",
        "身份漂移",
    ]

    def serialize_static_sections(self, ir: ShotIR) -> dict[str, Any]:
        shot_size = _shot_size_zh(ir)
        scene_label = _scene_label(ir)
        character_labels = [_binding_label(item) for item in ir.character_bindings if _binding_label(item)]
        prop_labels = [_binding_label(item) for item in ir.prop_bindings if _binding_label(item)]

        frame_focus = f"{scene_label}，{shot_size}构图，电影感首帧画面"
        if ir.start_state:
            frame_focus += f"。开场画面中，{_truncate(_clean_visual_prompt_text(ir.start_state), 150)}"

        asset_anchors: list[dict[str, str]] = []
        if scene_label:
            asset_anchors.append({"role": "scene", "label": scene_label})
        for label in character_labels:
            asset_anchors.append({"role": "character", "label": label})
        for label in prop_labels:
            asset_anchors.append({"role": "prop", "label": label})

        composition_parts = [f"{shot_size}构图"]
        if character_labels:
            composition_parts.append(f"主体人物为{'、'.join(character_labels)}")
        if prop_labels:
            composition_parts.append(f"关键道具为{'、'.join(prop_labels)}，位置与状态清晰可见")

        frozen_action = _truncate(_clean_visual_prompt_text(ir.start_state or ir.action_process), 180)

        visual_facts: list[dict[str, str]] = []
        for binding in [ir.scene_binding, *ir.character_bindings, *ir.prop_bindings]:
            label = _binding_label(binding)
            fact = _binding_fact(binding)
            if not label or not fact:
                continue
            role = _clean_text(getattr(binding, "asset_type", "")) or "asset"
            asset_fact_limit = 320 if role == "scene" else 120
            fact_text = _truncate(fact, asset_fact_limit)
            normalized = re.sub(r"\s+", "", f"{role}:{label}:{fact_text}")
            if any(normalized == re.sub(r"\s+", "", f"{item.get('role')}:{item.get('label')}:{item.get('fact')}") for item in visual_facts):
                continue
            visual_facts.append({"role": role, "label": label, "fact": fact_text})
            if len(visual_facts) >= 5:
                break

        required_visual_facts = []
        for fact in ir.visual_facts:
            label = _visual_fact_label(fact)
            _append_unique_prompt_part(required_visual_facts, label, limit=90)
            if len(required_visual_facts) >= 2:
                break

        lighting_emotion_parts = []
        if ir.lighting:
            lighting_emotion_parts.append(f"光线氛围为{_truncate(_clean_visual_prompt_text(ir.lighting), 80)}")
        if ir.emotion_arc.start:
            lighting_emotion_parts.append(f"初始情绪为{ir.emotion_arc.start}，画面情绪服务于{ir.shot_purpose or '当前叙事目的'}")

        return {
            "schema_version": "storyboard_image_prompt_sections_v1",
            "frame_focus": frame_focus,
            "asset_anchors": asset_anchors,
            "composition": "，".join(composition_parts),
            "frozen_action": frozen_action,
            "asset_visual_facts": visual_facts,
            "required_visual_facts": required_visual_facts,
            "lighting_emotion": "。".join(lighting_emotion_parts),
            "constraints": "身份、脸型、发型和服装以对应参考图为准；空间层次清晰，构图稳定，光影真实；不新增未声明人物、道具、文字、水印或设定板排版。",
            "flattening_note": "模型提交文本应由这些结构段落自然编译，不直接转成字段清单。",
        }

    def serialize_static(self, ir: ShotIR) -> str:
        static_sections = self.serialize_static_sections(ir)
        character_labels = [
            item.get("label", "")
            for item in static_sections.get("asset_anchors", [])
            if isinstance(item, dict) and item.get("role") == "character" and item.get("label")
        ]
        prop_labels = [
            item.get("label", "")
            for item in static_sections.get("asset_anchors", [])
            if isinstance(item, dict) and item.get("role") == "prop" and item.get("label")
        ]
        sections = [
            f"{static_sections.get('frame_focus', '')}。",
        ]
        if character_labels:
            sections.append(f"主体人物为{'、'.join(character_labels)}，身份、脸型、发型和服装以对应参考图为准。")
        if prop_labels:
            sections.append(f"关键道具为{'、'.join(prop_labels)}，位置与状态清晰可见。")

        asset_facts = []
        for item in static_sections.get("asset_visual_facts", []):
            if not isinstance(item, dict):
                continue
            label = _clean_text(item.get("label"))
            fact = _clean_text(item.get("fact"))
            if label and fact:
                asset_fact_limit = 320 if _clean_text(item.get("role")) == "scene" else 120
                _append_unique_prompt_part(asset_facts, f"{label}：{fact}", limit=asset_fact_limit)
            if len(asset_facts) >= 3:
                break
        if asset_facts:
            sections.append("画面细节包含" + "；".join(asset_facts) + "。")

        required_visual_facts = static_sections.get("required_visual_facts", [])
        if required_visual_facts and len(asset_facts) < 2:
            sections.append("补充视觉锚点包含" + "；".join([_clean_text(item) for item in required_visual_facts if _clean_text(item)]) + "。")
        if static_sections.get("lighting_emotion"):
            sections.append(f"{static_sections.get('lighting_emotion')}。")

        sections.append("空间层次清晰，构图稳定，光影真实，不新增未声明人物或道具。")
        return "".join(sections)

    def serialize_motion(self, ir: ShotIR) -> str:
        camera = _camera_motion_zh(ir)
        duration = f"{ir.duration}秒" if ir.duration else "本镜头"
        sections = [
            f"{duration}内，镜头{camera}，保持首帧构图、场景、人物身份、服装、发型和关键道具连续一致。",
        ]
        declared_timeline = _declared_action_timeline(ir)
        if declared_timeline:
            sections.append(f"动作推进为{declared_timeline}。")
        if ir.emotion_arc.start or ir.emotion_arc.end:
            start = ir.emotion_arc.start or "当前情绪"
            end = ir.emotion_arc.end or start
            sections.append(f"情绪从{start}逐步推进到{end}，强度为{ir.emotion_arc.intensity or 'medium'}，避免突兀跳变。")
        sections.append("全过程不改变脸型、服装、场景布局和道具状态，不出现突然变形或无依据新增元素。")
        return "".join(sections)

    def serialize_negative(self, ir: ShotIR) -> str:
        parts = list(self.negative_defaults)
        for section in ir.negative_sections:
            text = _clean_text(section)
            if text:
                parts.append(text)
        return "，".join(dict.fromkeys(parts))


class KlingStoryboardAdapter(StoryboardChineseAdapter):
    """Kling 目标 Adapter。

    保持中文可读，但显式组织为主体、镜头、动作、约束四段，便于后续映射
    到可灵 API 的 reference / prompt 字段。
    """

    def serialize_static(self, ir: ShotIR) -> str:
        return "可灵主体与首帧段。" + super().serialize_static(ir)

    def serialize_motion(self, ir: ShotIR) -> str:
        return "可灵镜头与动作段。" + super().serialize_motion(ir)


class VeoStoryboardAdapter(StoryboardChineseAdapter):
    """Veo 目标 Adapter：偏连续镜头自然语言。"""

    def serialize_static(self, ir: ShotIR) -> str:
        return "Veo连续镜头首帧描述。" + super().serialize_static(ir)

    def serialize_motion(self, ir: ShotIR) -> str:
        return "Veo连续镜头运动描述。" + super().serialize_motion(ir)


class SeedanceStoryboardAdapter(StoryboardChineseAdapter):
    """Seedance 目标 Adapter：强调短视频节奏与动作阶段。"""

    def serialize_static(self, ir: ShotIR) -> str:
        return "Seedance竖屏短剧首帧描述。" + super().serialize_static(ir)

    def serialize_motion(self, ir: ShotIR) -> str:
        return "Seedance短视频动作节奏描述。" + super().serialize_motion(ir)


class KelingAdapter(ModelAdapter):
    """可灵适配器 — 支持结构化 JSON 输入"""

    def serialize_static(self, ir: ShotIR) -> str:
        return ir.start_state or ir.action_process

    def serialize_motion(self, ir: ShotIR) -> str:
        return ir.action_process

    def serialize_negative(self, ir: ShotIR) -> str:
        return ""


class RunwayAdapter(ModelAdapter):
    """Runway 适配器 — 英文 motion prompt"""

    def serialize_static(self, ir: ShotIR) -> str:
        return ir.start_state

    def serialize_motion(self, ir: ShotIR) -> str:
        return ir.action_process

    def serialize_negative(self, ir: ShotIR) -> str:
        return ""


MODEL_ADAPTERS: dict[str, type[ModelAdapter]] = {
    "default": StoryboardChineseAdapter,
    "storyboard": StoryboardChineseAdapter,
    "jimeng": StoryboardChineseAdapter,
    "poyo": StoryboardChineseAdapter,
    "seedance": SeedanceStoryboardAdapter,
    "kling": KlingStoryboardAdapter,
    "veo": VeoStoryboardAdapter,
    "sd": SDAdapter,
    "stable_diffusion": SDAdapter,
    "keling": StoryboardChineseAdapter,
    "keling_legacy": KelingAdapter,
    "runway": RunwayAdapter,
}


def get_adapter(model_name: str) -> ModelAdapter:
    """获取模型适配器"""
    adapter_cls = MODEL_ADAPTERS.get(str(model_name or "").lower(), StoryboardChineseAdapter)
    return adapter_cls()


def adapt_ir_to_model(ir: ShotIR, model_name: str) -> dict[str, Any]:
    """将 IR 适配到指定模型格式"""
    adapter = get_adapter(model_name)
    return {
        "adapter": adapter.__class__.__name__,
        "target_model": str(model_name or "default"),
        "static_prompt_sections": adapter.serialize_static_sections(ir),
        "static_prompt": adapter.serialize_static(ir),
        "motion_prompt": adapter.serialize_motion(ir),
        "negative_prompt": adapter.serialize_negative(ir),
    }
