"""Programmatic Repair — 程序化修复引擎。

确定性、无 LLM、毫秒级。用于修复枚举类和格式类违规。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from core.constraint_engine import (
    Constraint,
    ConstraintRegistry,
    ConstraintSeverity,
    RepairStrategy,
    Violation,
    ValidationResult,
    find_closest_enum,
    get_constraint_registry,
)


@dataclass
class RepairResult:
    """修复结果"""
    repaired_violations: list[Violation] = field(default_factory=list)
    unrepaired_violations: list[Violation] = field(default_factory=list)
    modified_data: dict[str, Any] = field(default_factory=dict)
    repair_log: list[dict[str, Any]] = field(default_factory=list)


class ProgrammaticRepair:
    """程序化修复引擎——确定性、无 LLM、毫秒级"""

    def __init__(self, registry: ConstraintRegistry | None = None):
        self.registry = registry or get_constraint_registry()

    def repair_shot(self, shot: dict, violations: list[Violation]) -> RepairResult:
        """修复单个镜头的违规"""
        result = RepairResult()
        repaired_shot = copy.deepcopy(shot)

        for violation in violations:
            if violation.repair_strategy != RepairStrategy.PROGRAMMATIC:
                result.unrepaired_violations.append(violation)
                continue

            constraint = self.registry.get(violation.constraint_id)
            if not constraint:
                result.unrepaired_violations.append(violation)
                continue

            success = False
            if constraint.rule == "enum_match":
                success = self._repair_enum(repaired_shot, violation, constraint)
            elif constraint.rule == "range":
                success = self._repair_range(repaired_shot, violation, constraint)
            elif constraint.rule == "forbidden":
                success = self._repair_forbidden(repaired_shot, violation, constraint)
            elif constraint.rule == "min_length":
                # min_length 不能程序化修复
                pass

            if success:
                result.repaired_violations.append(violation)
                result.repair_log.append({
                    "constraint_id": violation.constraint_id,
                    "field": violation.field,
                    "old_value": violation.actual_value,
                    "new_value": repaired_shot.get(violation.field),
                    "strategy": "programmatic",
                })
            else:
                result.unrepaired_violations.append(violation)

        result.modified_data = repaired_shot
        return result

    def repair_scene(self, shots: list[dict], violations: list[Violation]) -> RepairResult:
        """修复整个场景的违规"""
        result = RepairResult()
        repaired_shots = copy.deepcopy(shots)

        # 按镜头分组违规
        shot_violations: dict[int, list[Violation]] = {}
        for v in violations:
            # 解析 location 中的 shot 索引
            shot_idx = self._parse_shot_index(v.location)
            if shot_idx is not None and shot_idx < len(repaired_shots):
                shot_violations.setdefault(shot_idx, []).append(v)
            else:
                result.unrepaired_violations.append(v)

        # 逐镜头修复
        for idx, shot_violations_list in shot_violations.items():
            shot_result = self.repair_shot(repaired_shots[idx], shot_violations_list)
            repaired_shots[idx] = shot_result.modified_data
            result.repaired_violations.extend(shot_result.repaired_violations)
            result.unrepaired_violations.extend(shot_result.unrepaired_violations)
            result.repair_log.extend(shot_result.repair_log)

        result.modified_data = repaired_shots
        return result

    def _repair_enum(self, shot: dict, violation: Violation, constraint: Constraint) -> bool:
        """修复枚举违规：模糊匹配替换为最接近的合法值"""
        params = constraint.rule_params
        valid_keys = params.get("valid_keys", set())
        valid_values = params.get("valid_values", set())

        actual = str(violation.actual_value or "").strip()
        closest = find_closest_enum(actual, valid_keys, valid_values)

        if closest is not None:
            shot[violation.field] = closest
            return True
        return False

    def _repair_range(self, shot: dict, violation: Violation, constraint: Constraint) -> bool:
        """修复范围违规：clamp 到合法范围"""
        params = constraint.rule_params
        min_val = params.get("min")
        max_val = params.get("max")

        try:
            value = float(violation.actual_value)
            if min_val is not None and value < min_val:
                shot[violation.field] = min_val
                return True
            if max_val is not None and value > max_val:
                shot[violation.field] = max_val
                return True
        except (ValueError, TypeError):
            pass
        return False

    def _repair_forbidden(self, shot: dict, violation: Violation, constraint: Constraint) -> bool:
        """修复禁用违规：替换为默认值"""
        # 禁用值不能直接替换，需要根据上下文选择替代
        # 这里用简单的默认值策略
        field_defaults = {
            "shot_purpose": "emotion",
            "camera_movement": "static",
            "camera_angle": "MS",
            "transition": "cut",
            "camera_speed": "slow",
        }
        default = field_defaults.get(violation.field)
        if default:
            shot[violation.field] = default
            return True
        return False

    def _parse_shot_index(self, location: str) -> int | None:
        """从 location 中解析镜头索引"""
        import re
        match = re.search(r"shot_(\d+)", location)
        if match:
            return int(match.group(1))
        return None
