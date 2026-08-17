"""Structural Validation Integration - 结构化验证集成

将结构化验证引擎集成到现有的生产技能系统中。
"""

from __future__ import annotations

from typing import Any

from core.repair import (
    StructuralRepairEngine,
    build_constraint_validator_from_facts,
    build_prop_tracker_from_facts,
    build_state_machine_from_facts,
)


def extract_facts_from_foundation(foundation: dict[str, Any]) -> dict[str, Any]:
    """从 foundation 提取故事事实表"""
    story_fact_sheet = {
        "characters": [],
        "props": [],
        "scenes": [],
    }
    
    # 提取角色信息
    character_cards = foundation.get("character_state_cards", [])
    for card in character_cards:
        if not isinstance(card, dict):
            continue
        story_fact_sheet["characters"].append({
            "name": card.get("name", ""),
            "public_persona": card.get("public_persona", ""),
            "hidden_layer": card.get("hidden_layer", ""),
            "speech_style": card.get("speech_style", ""),
            "visible_state": card.get("visible_state", ""),
            "hidden_state": card.get("hidden_state", ""),
            "state_transition_trigger": card.get("state_transition_trigger", ""),
            "persona_layer_guardrail": card.get("persona_layer_guardrail", ""),
        })
    
    # 提取道具信息
    prop_cards = foundation.get("prop_cards", foundation.get("key_props", []))
    for card in prop_cards:
        if not isinstance(card, dict):
            continue
        story_fact_sheet["props"].append({
            "name": card.get("name", ""),
            "type": card.get("type", "普通道具"),
            "owner": card.get("owner", ""),
            "location": card.get("location", ""),
            "state": card.get("state", ""),
            "first_appearance": card.get("first_appearance", ""),
        })
    
    # 提取场景信息（修复：添加 content 字段）
    scene_cards = foundation.get("scene_goal_cards", [])
    for card in scene_cards:
        if not isinstance(card, dict):
            continue
        story_fact_sheet["scenes"].append({
            "name": card.get("scene_name", ""),
            "characters": card.get("characters", []),
            "props": card.get("props", []),
            "content": card.get("content", ""),  # 添加 content 字段
        })
    
    return story_fact_sheet


def build_structural_validation_block(
    foundation: dict[str, Any],
    scene_execution_cards: list[dict[str, Any]],
) -> dict[str, Any]:
    """构建结构化验证块"""
    # 提取事实
    story_fact_sheet = extract_facts_from_foundation(foundation)
    
    # 创建结构化引擎
    engine = StructuralRepairEngine(
        story_fact_sheet=story_fact_sheet,
        scene_execution_cards=scene_execution_cards,
    )
    
    # 执行预验证
    packet = engine.pre_generation_validation()
    
    # 构建验证块
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
        "repair_directives": packet.fix_instructions,
        "engine": engine,
    }


def format_structural_validation_for_prompt(validation_block: dict[str, Any]) -> str:
    """将结构化验证结果格式化为 prompt 块"""
    validation = validation_block.get("structural_validation", {})
    directives = validation_block.get("repair_directives", [])
    
    lines = ["## Structural Validation Results"]
    
    # 验证摘要
    summary = validation.get("validation_summary", {})
    lines.append(f"Total constraint violations: {summary.get('constraint_violations', 0)}")
    lines.append(f"Total prop issues: {summary.get('prop_issues', 0)}")
    lines.append(f"Total character issues: {summary.get('character_issues', 0)}")
    lines.append(f"Total fixes needed: {summary.get('total_fixes', 0)}")
    
    # 约束违反
    violations = validation.get("constraint_violations", [])
    if violations:
        lines.append("\n### Constraint Violations")
        for v in violations:
            lines.append(f"- [{v.get('severity', 'info')}] {v.get('message', '')}")
            if v.get('fix_suggestion'):
                lines.append(f"  Fix: {v.get('fix_suggestion', '')}")
    
    # 道具问题
    prop_issues = validation.get("prop_issues", [])
    if prop_issues:
        lines.append("\n### Prop Issues")
        for issue in prop_issues:
            lines.append(f"- [{issue.get('type', '')}] {issue.get('message', '')}")
            if issue.get('fix'):
                lines.append(f"  Fix: {issue.get('fix', '')}")
    
    # 角色问题
    char_issues = validation.get("character_issues", [])
    if char_issues:
        lines.append("\n### Character Issues")
        for issue in char_issues:
            lines.append(f"- [{issue.get('type', '')}] {issue.get('message', '')}")
            if issue.get('fix'):
                lines.append(f"  Fix: {issue.get('fix', '')}")
    
    # 修复指令
    if directives:
        lines.append("\n### Structural Fix Directives")
        lines.append("Apply these fixes in priority order:")
        for i, d in enumerate(directives[:10], 1):  # 只显示前10个
            lines.append(f"{i}. [{d.get('type', '')}] {d.get('instruction', '')[:100]}...")
    
    return "\n".join(lines)
