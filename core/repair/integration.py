"""Structural Repair Integration - 结构化修复集成

将结构化修复引擎集成到生产技能系统中。
"""

from __future__ import annotations

from typing import Any

from core.repair import (
    StructuralRepairEngine,
    StructuralRepairPacket,
    build_constraint_validator_from_facts,
    build_prop_tracker_from_facts,
    build_state_machine_from_facts,
)


def build_structural_repair_context(
    book_id: int,
    episode: int,
    story_fact_sheet: dict[str, Any],
    scene_execution_cards: list[dict[str, Any]],
) -> dict[str, Any]:
    """构建结构化修复上下文
    
    在生成剧本前调用，提供结构化验证结果。
    """
    # 创建结构化引擎
    engine = StructuralRepairEngine(
        story_fact_sheet=story_fact_sheet,
        scene_execution_cards=scene_execution_cards,
    )
    
    # 执行预验证
    packet = engine.pre_generation_validation()
    
    # 生成修复指令
    directives = engine.generate_repair_directives(packet)
    
    return {
        "structural_validation": {
            "constraint_violations": [
                {
                    "constraint_id": v.constraint_id,
                    "layer": v.layer.value,
                    "severity": v.severity.value,
                    "message": v.message,
                    "location": v.location,
                    "fix_suggestion": v.fix_suggestion,
                }
                for v in packet.constraint_violations
            ],
            "prop_issues": packet.prop_issues,
            "character_issues": packet.character_issues,
            "validation_summary": packet.validation_summary,
        },
        "repair_directives": directives,
        "engine": engine,  # 保留引擎实例用于后续验证
    }


def apply_structural_repair_directives(
    script_content: str,
    repair_directives: list[dict[str, Any]],
) -> str:
    """应用结构化修复指令
    
    在生成剧本后调用，应用确定性修复。
    """
    # 这里需要实现具体的文本替换逻辑
    # 目前返回原始内容，后续可以扩展
    return script_content


def validate_generated_script(
    engine: StructuralRepairEngine,
    generated_script: dict[str, Any],
) -> StructuralRepairPacket:
    """验证生成的剧本
    
    在生成剧本后调用，验证生成结果。
    """
    return engine.post_generation_validation(generated_script)
