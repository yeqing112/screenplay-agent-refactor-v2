"""Model Adapter — 将 Prompt IR 适配到不同图像/视频生成模型。

参考方案：AI 影视生产系统 V1.0 第 15 节
核心思想：不同模型（SD、Midjourney、可灵、Runway）接受不同格式的 prompt，
Adapter 负责将标准化 IR 转换为模型特定格式。
"""

from __future__ import annotations

from typing import Any

from core.prompt_ir import ShotIR


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
    "sd": SDAdapter,
    "stable_diffusion": SDAdapter,
    "keling": KelingAdapter,
    "runway": RunwayAdapter,
}


def get_adapter(model_name: str) -> ModelAdapter:
    """获取模型适配器"""
    adapter_cls = MODEL_ADAPTERS.get(model_name.lower(), SDAdapter)
    return adapter_cls()


def adapt_ir_to_model(ir: ShotIR, model_name: str) -> dict[str, str]:
    """将 IR 适配到指定模型格式"""
    adapter = get_adapter(model_name)
    return {
        "static_prompt": adapter.serialize_static(ir),
        "motion_prompt": adapter.serialize_motion(ir),
        "negative_prompt": adapter.serialize_negative(ir),
    }
