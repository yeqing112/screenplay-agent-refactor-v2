"""Structural Repair Engine - 结构化修复引擎

整合所有结构化验证器，在生成阶段就发现问题并修复。
替代原来的启发式修复循环。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .fact_constraints import (
    FactConstraintValidator,
    ConstraintViolation,
    ConstraintSeverity,
    build_constraint_validator_from_facts,
)
from .prop_tracker import PropTracker, build_prop_tracker_from_facts
from .character_state_machine import CharacterStateMachine, build_state_machine_from_facts


class RepairPhase(Enum):
    """修复阶段"""
    VALIDATION = "validation"          # 验证阶段
    CONSTRAINT_FIX = "constraint_fix"  # 约束修复
    STRUCTURAL_FIX = "structural_fix"  # 结构修复
    VERIFICATION = "verification"      # 验证修复结果


@dataclass
class RepairResult:
    """修复结果"""
    phase: RepairPhase
    violations_before: int
    violations_fixed: int
    violations_remaining: int
    fixes_applied: list[dict[str, Any]]
    remaining_issues: list[dict[str, Any]]


@dataclass
class StructuralRepairPacket:
    """结构化修复包
    
    包含所有验证器的发现和修复建议，
    供 Rewrite Agent 使用。
    """
    constraint_violations: list[ConstraintViolation]
    prop_issues: list[dict[str, Any]]
    character_issues: list[dict[str, Any]]
    fix_instructions: list[dict[str, Any]]
    validation_summary: dict[str, Any]


class StructuralRepairEngine:
    """结构化修复引擎
    
    核心流程：
    1. 在生成前：验证事实约束，发现潜在问题
    2. 在生成中：实时检查道具和角色状态
    3. 在生成后：全面验证，生成修复包
    
    与旧系统的区别：
    - 旧系统：QA发现问题 → 关键词分类 → LLM重写 → 再QA
    - 新系统：生成前验证 → 生成中检查 → 生成后验证 → 确定性修复
    """
    
    def __init__(
        self,
        story_fact_sheet: dict[str, Any],
        scene_execution_cards: list[dict[str, Any]],
    ):
        self.story_fact_sheet = story_fact_sheet
        self.scene_execution_cards = scene_execution_cards
        
        # 初始化验证器
        self.constraint_validator = build_constraint_validator_from_facts(
            story_fact_sheet, scene_execution_cards
        )
        self.prop_tracker = build_prop_tracker_from_facts(
            story_fact_sheet, scene_execution_cards
        )
        self.state_machine = build_state_machine_from_facts(
            story_fact_sheet, scene_execution_cards
        )
    
    def pre_generation_validation(self) -> StructuralRepairPacket:
        """生成前验证
        
        在开始生成剧本前，验证事实约束。
        """
        # 1. 验证约束
        constraint_violations = self.constraint_validator.validate_all()
        
        # 2. 验证道具连续性
        prop_issues = self.prop_tracker.validate_continuity()
        
        # 3. 验证状态转换
        character_issues = self.state_machine.validate_transitions()
        
        # 4. 生成修复指令
        fix_instructions = self._generate_fix_instructions(
            constraint_violations, prop_issues, character_issues
        )
        
        # 5. 生成摘要
        validation_summary = {
            "constraint_violations": len(constraint_violations),
            "prop_issues": len(prop_issues),
            "character_issues": len(character_issues),
            "total_fixes": len(fix_instructions),
            "severity_breakdown": self._count_severity(constraint_violations),
        }
        
        return StructuralRepairPacket(
            constraint_violations=constraint_violations,
            prop_issues=prop_issues,
            character_issues=character_issues,
            fix_instructions=fix_instructions,
            validation_summary=validation_summary,
        )
    
    def post_generation_validation(
        self, generated_script: dict[str, Any]
    ) -> StructuralRepairPacket:
        """生成后验证
        
        在生成剧本后，验证生成结果。
        """
        # 更新验证器状态
        self._update_from_generated_script(generated_script)
        
        # 执行验证
        return self.pre_generation_validation()
    
    def generate_repair_directives(
        self, packet: StructuralRepairPacket
    ) -> list[dict[str, Any]]:
        """生成修复指令
        
        将验证发现转换为确定性的修复指令。
        """
        directives = []
        
        # 处理约束违反
        for violation in packet.constraint_violations:
            directive = self._violation_to_directive(violation)
            if directive:
                directives.append(directive)
        
        # 处理道具问题
        for issue in packet.prop_issues:
            directive = self._prop_issue_to_directive(issue)
            if directive:
                directives.append(directive)
        
        # 处理角色问题
        for issue in packet.character_issues:
            directive = self._character_issue_to_directive(issue)
            if directive:
                directives.append(directive)
        
        return directives
    
    def _generate_fix_instructions(
        self,
        constraint_violations: list[ConstraintViolation],
        prop_issues: list[dict[str, Any]],
        character_issues: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """生成修复指令"""
        instructions = []
        
        # 约束违反的修复指令
        for violation in constraint_violations:
            instructions.append({
                "type": "CONSTRAINT_FIX",
                "priority": self._severity_to_priority(violation.severity),
                "location": violation.location,
                "instruction": violation.fix_suggestion,
                "affected_entities": violation.affected_entities,
            })
        
        # 道具问题的修复指令
        for issue in prop_issues:
            instructions.append({
                "type": "PROP_FIX",
                "priority": 2,
                "location": issue.get("scene", ""),
                "instruction": issue.get("fix", ""),
                "affected_entities": [issue.get("prop", "")],
            })
        
        # 角色问题的修复指令
        for issue in character_issues:
            instructions.append({
                "type": "CHARACTER_FIX",
                "priority": 2,
                "location": issue.get("scene", ""),
                "instruction": issue.get("fix", ""),
                "affected_entities": [issue.get("character", "")],
            })
        
        # 按优先级排序
        instructions.sort(key=lambda x: x.get("priority", 3))
        
        return instructions
    
    def _violation_to_directive(
        self, violation: ConstraintViolation
    ) -> dict[str, Any] | None:
        """将约束违反转换为修复指令"""
        return {
            "type": "CONSTRAINT_VIOLATION",
            "constraint_id": violation.constraint_id,
            "layer": violation.layer.value,
            "severity": violation.severity.value,
            "location": violation.location,
            "instruction": violation.fix_suggestion,
            "affected_entities": violation.affected_entities,
        }
    
    def _prop_issue_to_directive(self, issue: dict[str, Any]) -> dict[str, Any] | None:
        """将道具问题转换为修复指令"""
        return {
            "type": "PROP_ISSUE",
            "issue_type": issue.get("type", ""),
            "location": issue.get("scene", ""),
            "instruction": issue.get("fix", ""),
            "affected_entities": [issue.get("prop", "")],
        }
    
    def _character_issue_to_directive(
        self, issue: dict[str, Any]
    ) -> dict[str, Any] | None:
        """将角色问题转换为修复指令"""
        return {
            "type": "CHARACTER_ISSUE",
            "issue_type": issue.get("type", ""),
            "location": issue.get("scene", ""),
            "instruction": issue.get("fix", ""),
            "affected_entities": [issue.get("character", "")],
        }
    
    def _severity_to_priority(self, severity: ConstraintSeverity) -> int:
        """将严重程度转换为优先级"""
        priority_map = {
            ConstraintSeverity.ERROR: 1,
            ConstraintSeverity.WARNING: 2,
            ConstraintSeverity.INFO: 3,
        }
        return priority_map.get(severity, 3)
    
    def _count_severity(
        self, violations: list[ConstraintViolation]
    ) -> dict[str, int]:
        """统计严重程度分布"""
        counts = {}
        for violation in violations:
            severity = violation.severity.value
            if severity not in counts:
                counts[severity] = 0
            counts[severity] += 1
        return counts
    
    def _update_from_generated_script(self, script: dict[str, Any]):
        """从生成的剧本更新验证器状态"""
        # 更新道具状态
        for prop_data in script.get("props", []):
            prop_name = prop_data.get("name", "")
            if prop_name in self.prop_tracker.props:
                prop = self.prop_tracker.props[prop_name]
                prop.current_holder = prop_data.get("current_holder", prop.current_holder)
                prop.current_location = prop_data.get("location", prop.current_location)
        
        # 更新角色状态
        for char_data in script.get("characters", []):
            char_name = char_data.get("name", "")
            if char_name in self.state_machine.characters:
                char = self.state_machine.characters[char_name]
                char.current_public_state = char_data.get("public_state", char.current_public_state)
                char.current_hidden_state = char_data.get("hidden_state", char.current_hidden_state)
