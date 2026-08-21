"""Prompt IR (Intermediate Representation) — 编译中间表示数据模型。

参考方案：AI 影视生产系统 V1.0 第 12-14 节
核心思想：Prompt 不再是字符串拼接，而是结构化 IR，可被规则、诊断、适配层分别处理。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AssetBinding:
    """资产绑定信息"""
    asset_type: str = ""
    asset_id: str = ""
    asset_name: str = ""
    reference_token: str = ""
    reference_status: str = ""
    authority_prompt_raw: str = ""
    canonical_prompt_parts: list[dict[str, str]] = field(default_factory=list)
    variant_scope: str = ""
    variant_name: str = ""


@dataclass
class VisualFact:
    """视觉事实条目"""
    asset_name: str = ""
    fact: str = ""
    source: str = ""
    priority: int = 0


@dataclass
class ContinuityConstraint:
    """连续性约束"""
    has_previous: bool = False
    previous_shot_id: int = 0
    previous_end_state: str = ""
    previous_scene_name: str = ""


@dataclass
class RetentionConstraint:
    """Retention 约束"""
    face: str = "fully_preserved"
    hair: str = "fully_preserved"
    costume: str = "fully_preserved"
    background: str = "mostly_preserved"
    composition: str = "free"


@dataclass
class EmotionArc:
    """情绪弧线"""
    start: str = ""
    end: str = ""
    intensity: str = "medium"


@dataclass
class ShotIR:
    """单镜头 Prompt 中间表示"""
    shot_id: int = 0
    scene_name: str = ""
    duration: int = 3
    camera_angle: str = "MS"
    camera_movement: str = "static"
    camera_speed: str = "slow"
    transition: str = "cut"
    shot_purpose: str = "emotion"
    emotion_arc: EmotionArc = field(default_factory=EmotionArc)
    start_state: str = ""
    action_process: str = ""
    end_state: str = ""
    dialogue: str = ""
    lighting: str = ""
    style_key: str = "default"

    scene_binding: AssetBinding = field(default_factory=AssetBinding)
    character_bindings: list[AssetBinding] = field(default_factory=list)
    prop_bindings: list[AssetBinding] = field(default_factory=list)

    visual_facts: list[VisualFact] = field(default_factory=list)
    required_used_assets: list[str] = field(default_factory=list)
    continuity: ContinuityConstraint = field(default_factory=ContinuityConstraint)
    retention: RetentionConstraint = field(default_factory=RetentionConstraint)

    static_sections: list[str] = field(default_factory=list)
    motion_sections: list[str] = field(default_factory=list)
    negative_sections: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def build_shot_ir_from_context(context: dict) -> ShotIR:
    """从编译上下文构建 ShotIR"""
    shot = ShotIR()
    shot.shot_id = int(context.get("shot_id") or 0)
    shot.scene_name = str(context.get("scene_name") or "").strip()
    shot.duration = int(context.get("duration") or 3)
    shot.camera_angle = str(context.get("camera_angle") or "MS").strip()
    shot.camera_movement = str(context.get("camera_movement") or "static").strip()
    shot.camera_speed = str(context.get("camera_speed") or "slow").strip()
    shot.transition = str(context.get("transition") or "cut").strip()
    shot.shot_purpose = str(context.get("shot_purpose") or "emotion").strip()
    shot.start_state = str(context.get("start_state") or "").strip()
    shot.action_process = str(context.get("action_process") or "").strip()
    shot.end_state = str(context.get("end_state") or "").strip()
    shot.dialogue = str(context.get("dialogue") or "").strip()
    shot.lighting = str(context.get("lighting") or "").strip()
    shot.style_key = str(context.get("style_key") or "default").strip()

    emotion_arc_data = context.get("emotion_arc", {})
    if isinstance(emotion_arc_data, dict):
        shot.emotion_arc = EmotionArc(
            start=str(emotion_arc_data.get("start") or "").strip(),
            end=str(emotion_arc_data.get("end") or "").strip(),
            intensity=str(emotion_arc_data.get("intensity") or "medium").strip(),
        )

    retention_data = context.get("retention", {})
    if isinstance(retention_data, dict):
        shot.retention = RetentionConstraint(
            face=str(retention_data.get("face") or "fully_preserved").strip(),
            hair=str(retention_data.get("hair") or "fully_preserved").strip(),
            costume=str(retention_data.get("costume") or "fully_preserved").strip(),
            background=str(retention_data.get("background") or "mostly_preserved").strip(),
            composition=str(retention_data.get("composition") or "free").strip(),
        )

    continuity_data = context.get("continuity", {})
    if isinstance(continuity_data, dict):
        shot.continuity = ContinuityConstraint(
            has_previous=bool(continuity_data.get("has_previous")),
            previous_shot_id=int(continuity_data.get("previous_shot_id") or 0),
            previous_end_state=str(continuity_data.get("previous_end_state") or "").strip(),
            previous_scene_name=str(continuity_data.get("previous_scene_name") or "").strip(),
        )

    shot.required_used_assets = [
        str(item).strip()
        for item in (context.get("required_used_assets") or [])
        if str(item).strip()
    ]

    visual_fact_targets = context.get("visual_fact_targets", [])
    if isinstance(visual_fact_targets, list):
        for vf in visual_fact_targets:
            if not isinstance(vf, dict):
                continue
            asset_name = str(vf.get("asset_name") or "").strip()
            for fact in (vf.get("required_facts") or []):
                if str(fact).strip():
                    shot.visual_facts.append(VisualFact(
                        asset_name=asset_name,
                        fact=str(fact).strip(),
                        source="visual_fact_target",
                    ))

    asset_bindings = context.get("asset_bindings", {})
    if isinstance(asset_bindings, dict):
        scene_data = asset_bindings.get("scene", {})
        if isinstance(scene_data, dict) and scene_data:
            shot.scene_binding = AssetBinding(
                asset_type="scene",
                asset_id=str(scene_data.get("asset_id") or "").strip(),
                asset_name=str(scene_data.get("asset_name") or "").strip(),
                reference_token=str(scene_data.get("reference_token") or "").strip(),
                reference_status=str(scene_data.get("reference_status") or "").strip(),
                authority_prompt_raw=str(scene_data.get("authority_prompt_raw") or "").strip(),
                canonical_prompt_parts=scene_data.get("canonical_prompt_parts", []),
                variant_scope=str(scene_data.get("variant_scope") or "").strip(),
            )

        for char_data in (asset_bindings.get("characters") or []):
            if not isinstance(char_data, dict):
                continue
            shot.character_bindings.append(AssetBinding(
                asset_type="character",
                asset_id=str(char_data.get("asset_id") or "").strip(),
                asset_name=str(char_data.get("asset_name") or "").strip(),
                reference_token=str(char_data.get("reference_token") or "").strip(),
                reference_status=str(char_data.get("reference_status") or "").strip(),
                authority_prompt_raw=str(char_data.get("authority_prompt_raw") or "").strip(),
                canonical_prompt_parts=char_data.get("canonical_prompt_parts", []),
                variant_scope=str(char_data.get("variant_scope") or "").strip(),
                variant_name=str(char_data.get("variant_name") or "").strip(),
            ))

        for prop_data in (asset_bindings.get("props") or []):
            if not isinstance(prop_data, dict):
                continue
            shot.prop_bindings.append(AssetBinding(
                asset_type="prop",
                asset_id=str(prop_data.get("asset_id") or "").strip(),
                asset_name=str(prop_data.get("asset_name") or "").strip(),
                reference_token=str(prop_data.get("reference_token") or "").strip(),
                reference_status=str(prop_data.get("reference_status") or "").strip(),
                authority_prompt_raw=str(prop_data.get("authority_prompt_raw") or "").strip(),
                canonical_prompt_parts=prop_data.get("canonical_prompt_parts", []),
                variant_scope=str(prop_data.get("variant_scope") or "").strip(),
            ))

    shot.warnings = list(context.get("warnings", []))
    shot.metadata = {
        "camera_library": context.get("camera_library", {}),
        "emotion_library": context.get("emotion_library", {}),
        "shot_size_library": context.get("shot_size_library", {}),
        "production_skill": context.get("production_skill", {}),
    }

    return shot


def serialize_shot_ir(ir: ShotIR) -> dict:
    """将 ShotIR 序列化为 JSON 兼容 dict"""
    return {
        "shot_id": ir.shot_id,
        "scene_name": ir.scene_name,
        "duration": ir.duration,
        "camera_angle": ir.camera_angle,
        "camera_movement": ir.camera_movement,
        "camera_speed": ir.camera_speed,
        "transition": ir.transition,
        "shot_purpose": ir.shot_purpose,
        "emotion_arc": {
            "start": ir.emotion_arc.start,
            "end": ir.emotion_arc.end,
            "intensity": ir.emotion_arc.intensity,
        },
        "start_state": ir.start_state,
        "action_process": ir.action_process,
        "end_state": ir.end_state,
        "dialogue": ir.dialogue,
        "lighting": ir.lighting,
        "style_key": ir.style_key,
        "scene_binding": {
            "asset_id": ir.scene_binding.asset_id,
            "asset_name": ir.scene_binding.asset_name,
            "reference_token": ir.scene_binding.reference_token,
        },
        "character_bindings": [
            {
                "asset_id": c.asset_id,
                "asset_name": c.asset_name,
                "reference_token": c.reference_token,
                "variant_scope": c.variant_scope,
            }
            for c in ir.character_bindings
        ],
        "prop_bindings": [
            {
                "asset_id": p.asset_id,
                "asset_name": p.asset_name,
                "reference_token": p.reference_token,
            }
            for p in ir.prop_bindings
        ],
        "retention": {
            "face": ir.retention.face,
            "hair": ir.retention.hair,
            "costume": ir.retention.costume,
            "background": ir.retention.background,
            "composition": ir.retention.composition,
        },
        "continuity": {
            "has_previous": ir.continuity.has_previous,
            "previous_end_state": ir.continuity.previous_end_state,
        },
        "visual_facts_count": len(ir.visual_facts),
        "required_used_assets": ir.required_used_assets,
        "static_sections": ir.static_sections,
        "motion_sections": ir.motion_sections,
        "warnings": ir.warnings,
    }
