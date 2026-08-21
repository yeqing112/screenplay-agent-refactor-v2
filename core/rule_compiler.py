"""Rule Compiler — 将 Production Skill 规则应用到 Prompt IR。

参考方案：AI 影视生产系统 V1.0 第 12-13 节
核心思想：硬约束直接修改 IR，软偏好排序 section 优先级，禁用模式过滤非法内容。
"""

from __future__ import annotations

import re
from typing import Any

from core.prompt_ir import ShotIR


def apply_hard_constraints(ir: ShotIR, hard_constraints: list[str]) -> ShotIR:
    """应用硬约束到 IR。

    硬约束是必须满足的规则，直接修改 IR 字段。
    """
    for constraint in hard_constraints:
        constraint_lower = str(constraint).lower()

        if "不能" in constraint_lower or "禁止" in constraint_lower:
            _add_forbidden_pattern(ir, str(constraint))
        elif "必须" in constraint_lower:
            _add_required_element(ir, str(constraint))
        elif "镜头" in constraint_lower and ("固定" in constraint_lower or "static" in constraint_lower):
            ir.camera_movement = "static"
        elif "景别" in constraint_lower and "特写" in constraint_lower:
            ir.camera_angle = "CU"
        elif "时长" in constraint_lower:
            duration_match = re.search(r"(\d+)", str(constraint))
            if duration_match:
                ir.duration = min(ir.duration, int(duration_match.group(1)))

    return ir


def apply_soft_preferences(ir: ShotIR, soft_preferences: list[str]) -> ShotIR:
    """应用软偏好到 IR。

    软偏好是建议性的，影响 section 排序但不强制修改。
    """
    for pref in soft_preferences:
        pref_str = str(pref)
        if "特写" in pref_str:
            _add_static_section(ir, "使用特写镜头增强情绪表达")
        elif "运镜" in pref_str or "运动" in pref_str:
            _add_motion_section(ir, "使用动态运镜增加节奏感")
        elif "光影" in pref_str or "光线" in pref_str:
            _add_static_section(ir, "强调光影对比增强氛围")
        elif "留白" in pref_str:
            _add_static_section(ir, "画面适当留白增加意境")

    return ir


def filter_forbidden_patterns(ir: ShotIR, forbidden_patterns: list[str]) -> ShotIR:
    """过滤禁用模式。

    检查 IR 中的文本是否包含禁用模式，如果包含则添加警告。
    """
    all_text = f"{ir.start_state} {ir.action_process} {ir.end_state} {ir.dialogue}"

    for pattern in forbidden_patterns:
        pattern_str = str(pattern)
        if pattern_str and pattern_str in all_text:
            ir.warnings.append(f"检测到禁用模式「{pattern_str}」，建议移除")

    return ir


def compile_output_contracts(ir: ShotIR, output_contracts: dict) -> ShotIR:
    """根据输出合约调整 IR。

    输出合定义了最终输出必须包含的字段和格式。
    """
    if not isinstance(output_contracts, dict):
        return ir

    static_contract = output_contracts.get("static_prompt", {})
    if isinstance(static_contract, dict):
        min_chars = int(static_contract.get("min_chars") or 0)
        if min_chars > 0:
            ir.metadata["static_min_chars"] = min_chars

    motion_contract = output_contracts.get("motion_prompt", {})
    if isinstance(motion_contract, dict):
        min_chars = int(motion_contract.get("min_chars") or 0)
        if min_chars > 0:
            ir.metadata["motion_min_chars"] = min_chars

    return ir


def compile_rules(ir: ShotIR, production_skill_runtime: dict) -> ShotIR:
    """主入口：将所有规则应用到 IR"""
    if not isinstance(production_skill_runtime, dict):
        return ir

    hard_constraints = production_skill_runtime.get("hard_constraints", [])
    if isinstance(hard_constraints, list):
        ir = apply_hard_constraints(ir, hard_constraints)

    soft_preferences = production_skill_runtime.get("soft_preferences", [])
    if isinstance(soft_preferences, list):
        ir = apply_soft_preferences(ir, soft_preferences)

    forbidden_patterns = production_skill_runtime.get("forbidden_patterns", [])
    if isinstance(forbidden_patterns, list):
        ir = filter_forbidden_patterns(ir, forbidden_patterns)

    output_contracts = production_skill_runtime.get("output_contracts", {})
    if isinstance(output_contracts, dict):
        ir = compile_output_contracts(ir, output_contracts)

    return ir


def _add_forbidden_pattern(ir: ShotIR, pattern: str) -> None:
    ir.metadata.setdefault("forbidden_patterns_applied", []).append(pattern)


def _add_required_element(ir: ShotIR, element: str) -> None:
    ir.metadata.setdefault("required_elements", []).append(element)


def _add_static_section(ir: ShotIR, section: str) -> None:
    if section not in ir.static_sections:
        ir.static_sections.append(section)


def _add_motion_section(ir: ShotIR, section: str) -> None:
    if section not in ir.motion_sections:
        ir.motion_sections.append(section)
