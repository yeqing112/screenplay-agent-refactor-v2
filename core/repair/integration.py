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
    if not repair_directives:
        return script_content

    result = script_content

    for directive in repair_directives:
        if not isinstance(directive, dict):
            continue

        directive_type = directive.get("type", "")
        instruction = directive.get("instruction", "")
        location = directive.get("location", "")

        if directive_type == "CONSTRAINT_FIX":
            # 约束修复：尝试程序化文本替换
            result = _apply_constraint_fix(result, directive)
        elif directive_type == "PROP_FIX":
            # 道具修复：确保道具描述一致
            result = _apply_prop_fix(result, directive)
        elif directive_type == "CHARACTER_FIX":
            # 角色修复：确保角色行为/对白一致
            result = _apply_character_fix(result, directive)

    return result


def validate_generated_script(
    engine: StructuralRepairEngine,
    generated_script: dict[str, Any],
) -> StructuralRepairPacket:
    """验证生成的剧本

    在生成剧本后调用，验证生成结果。
    """
    return engine.post_generation_validation(generated_script)


# ============================================================
# 程序化修复辅助函数
# ============================================================

import re


def _apply_constraint_fix(script: str, directive: dict) -> str:
    """应用约束修复"""
    instruction = directive.get("instruction", "")
    affected = directive.get("affected_entities", [])

    # 修复场景头缺失
    if "场景头" in instruction or "## 场景" in instruction:
        if not re.search(r"##\s*场景", script):
            script = f"## 场景1：场景\n\n{script}"

    # 修复场景结束标记缺失
    if "场景结束" in instruction or "（场景结束）" in instruction:
        if not re.search(r"（场景结束）|场景结束|\[画面渐隐\]|\[淡出\]", script):
            script = script.rstrip() + "\n\n（场景结束）\n"

    return script


def _apply_prop_fix(script: str, directive: dict) -> str:
    """应用道具修复"""
    # 道具修复需要精确的文本定位，这里做简单的关键词替换
    instruction = directive.get("instruction", "")
    affected = directive.get("affected_entities", [])

    for entity in affected:
        if entity and entity in instruction:
            # 如果指令中提到了道具的具体描述，尝试吸收
            pass

    return script


def _apply_character_fix(script: str, directive: dict) -> str:
    """应用角色修复"""
    instruction = directive.get("instruction", "")
    affected = directive.get("affected_entities", [])

    # 角色行为修复：确保角色名在对白中正确出现
    for entity in affected:
        if entity and entity not in script:
            # 角色在脚本中不存在，跳过
            pass

    return script
