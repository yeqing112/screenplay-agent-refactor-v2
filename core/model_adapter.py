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

from core.prompt_ir import ShotIR


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()


def _clean_visual_prompt_text(value: object) -> str:
    text = _clean_text(value)
    text = re.sub(r"【([^】]{1,300})】", r"\1", text)
    text = re.sub(r"\[([^\]]{1,300})\]", r"\1", text)
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
    return _clean_text(text)


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
    for item in getattr(binding, "canonical_prompt_parts", []) or []:
        if not isinstance(item, dict):
            continue
        text = _clean_visual_prompt_text(item.get("text"))
        if text:
            parts.append(text)
        if len(parts) >= 2:
            break
    if not parts:
        raw = _clean_visual_prompt_text(getattr(binding, "authority_prompt_raw", ""))
        if raw:
            parts.append(raw)
    return _truncate("；".join(parts), 120)


def _visual_fact_label(fact) -> str:
    asset_name = _clean_visual_prompt_text(getattr(fact, "asset_name", ""))
    fact_text = _clean_visual_prompt_text(getattr(fact, "fact", ""))
    if asset_name and fact_text:
        return f"{asset_name}需保留{fact_text}"
    return fact_text


def _camera_motion_zh(ir: ShotIR) -> str:
    movement = _clean_text(ir.camera_movement).lower().replace("_", "-")
    speed = _clean_text(ir.camera_speed).lower()
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


class ModelAdapter:
    """模型适配器基类"""

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

    def serialize_static(self, ir: ShotIR) -> str:
        shot_size = _shot_size_zh(ir)
        scene_label = _scene_label(ir)
        character_labels = [_binding_label(item) for item in ir.character_bindings if _binding_label(item)]
        prop_labels = [_binding_label(item) for item in ir.prop_bindings if _binding_label(item)]

        sections = [
            f"{scene_label}，{shot_size}构图，第一帧只描述当前镜头开始瞬间。",
        ]
        if character_labels:
            sections.append(f"主体人物为{'、'.join(character_labels)}，外观、脸部、发型和服装严格继承绑定参考资产。")
        if prop_labels:
            sections.append(f"关键道具为{'、'.join(prop_labels)}，位置与状态清晰可见。")

        asset_facts = []
        for binding in [ir.scene_binding, *ir.character_bindings, *ir.prop_bindings]:
            label = _binding_label(binding)
            fact = _binding_fact(binding)
            if label and fact:
                asset_facts.append(f"{label}保留{fact}")
            if len(asset_facts) >= 3:
                break
        if asset_facts:
            sections.append("视觉事实包括" + "；".join(asset_facts) + "。")

        required_visual_facts = []
        for fact in ir.visual_facts:
            label = _visual_fact_label(fact)
            if label and label not in required_visual_facts:
                required_visual_facts.append(label)
            if len(required_visual_facts) >= 8:
                break
        if required_visual_facts:
            sections.append("当前镜头必须保留以下视觉细节，" + "；".join(required_visual_facts) + "。")

        if ir.start_state:
            sections.append(f"起始状态为{_truncate(_clean_visual_prompt_text(ir.start_state), 120)}。")
        if ir.lighting:
            sections.append(f"光线氛围为{_truncate(_clean_visual_prompt_text(ir.lighting), 60)}。")
        if ir.emotion_arc.start:
            sections.append(f"初始情绪为{ir.emotion_arc.start}，画面情绪服务于{ir.shot_purpose or '当前叙事目的'}。")

        sections.append("画面具备清晰空间层次、稳定构图、电影感光影和可追溯资产一致性。")
        return "".join(sections)

    def serialize_motion(self, ir: ShotIR) -> str:
        camera = _camera_motion_zh(ir)
        duration = f"{ir.duration}秒" if ir.duration else "本镜头"
        sections = [
            f"{duration}内，镜头{camera}，保持首帧构图、场景、人物身份、服装、发型和关键道具连续一致。",
        ]
        if ir.action_process:
            sections.append(f"动作推进为{_truncate(_clean_visual_prompt_text(ir.action_process), 150)}。")
        elif ir.start_state or ir.end_state:
            sections.append(
                f"动作从“{_truncate(_clean_visual_prompt_text(ir.start_state), 70)}”自然过渡到“{_truncate(_clean_visual_prompt_text(ir.end_state), 70)}”。"
            )
        if ir.emotion_arc.start or ir.emotion_arc.end:
            start = ir.emotion_arc.start or "当前情绪"
            end = ir.emotion_arc.end or start
            sections.append(f"情绪从{start}逐步推进到{end}，强度为{ir.emotion_arc.intensity or 'medium'}，避免突兀跳变。")
        if ir.continuity.has_previous and ir.continuity.previous_end_state:
            sections.append(f"开头承接上一镜结束状态为{_truncate(_clean_visual_prompt_text(ir.continuity.previous_end_state), 90)}。")
        if ir.end_state:
            sections.append(f"结束落点为{_truncate(_clean_visual_prompt_text(ir.end_state), 100)}。")
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


def adapt_ir_to_model(ir: ShotIR, model_name: str) -> dict[str, str]:
    """将 IR 适配到指定模型格式"""
    adapter = get_adapter(model_name)
    return {
        "adapter": adapter.__class__.__name__,
        "target_model": str(model_name or "default"),
        "static_prompt": adapter.serialize_static(ir),
        "motion_prompt": adapter.serialize_motion(ir),
        "negative_prompt": adapter.serialize_negative(ir),
    }
