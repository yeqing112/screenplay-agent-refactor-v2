"""Violation Repair Orchestrator — 统一修复协调器。

统一入口，分级调度：
- Level 1: 程序化修复（枚举/格式）
- Level 2: 混合修复（结构+LLM）
- Level 3: LLM 完全修复（语义类）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from core.constraint_engine import (
    ConstraintRegistry,
    ConstraintSeverity,
    RepairStrategy,
    ValidationResult,
    Violation,
    get_constraint_registry,
)
from core.validators.programmatic_repair import ProgrammaticRepair, RepairResult


@dataclass
class OrchestratorResult:
    """协调器结果"""
    validation: ValidationResult
    repair: RepairResult
    final_data: Any = None
    attempts: int = 0
    strategy_log: list[dict[str, Any]] = field(default_factory=list)


class ViolationRepairOrchestrator:
    """违规修复协调器——统一入口，分级调度"""

    def __init__(self, registry: ConstraintRegistry | None = None):
        self.registry = registry or get_constraint_registry()
        self.programmatic = ProgrammaticRepair(self.registry)

    def repair(
        self,
        data: Any,
        validation: ValidationResult,
        llm_caller: Callable | None = None,
        context: dict | None = None,
        max_retries: int = 2,
    ) -> OrchestratorResult:
        """修复违规"""
        result = OrchestratorResult(
            validation=validation,
            repair=RepairResult(),
            final_data=data,
        )

        if not validation.violations:
            return result

        # 分类违规
        level1, level2, level3 = self._classify_violations(validation.violations)

        # Level 1: 程序化修复
        if level1:
            result.strategy_log.append({
                "level": 1,
                "count": len(level1),
                "violations": [v.constraint_id for v in level1],
            })
            repair_result = self.programmatic.repair_shot(data, level1) if isinstance(data, dict) \
                else self.programmatic.repair_scene(data, level1)
            result.repair.repaired_violations.extend(repair_result.repaired_violations)
            result.repair.repair_log.extend(repair_result.repair_log)
            result.final_data = repair_result.modified_data
            result.attempts += 1

            # 重新分类未修复的
            still_unrepaired = repair_result.unrepaired_violations
            level2.extend([v for v in still_unrepaired if v.repair_strategy == RepairStrategy.HYBRID])
            level3.extend([v for v in still_unrepaired if v.repair_strategy == RepairStrategy.LLM])

        # Level 2 + 3: LLM 修复
        if (level2 or level3) and llm_caller:
            llm_violations = level2 + level3
            for attempt in range(max_retries):
                result.strategy_log.append({
                    "level": "llm",
                    "attempt": attempt + 1,
                    "count": len(llm_violations),
                })

                llm_result = self._llm_repair(
                    result.final_data, llm_violations, llm_caller, context
                )

                if llm_result is not None:
                    result.final_data = llm_result
                    result.attempts += 1

                    # 重新校验
                    re_validation = self._revalidate(result.final_data)
                    if re_validation.passed:
                        result.validation = re_validation
                        break
                    elif re_validation.violations:
                        llm_violations = [v for v in re_validation.violations
                                         if v.repair_strategy in (RepairStrategy.LLM, RepairStrategy.HYBRID)]
                        if not llm_violations:
                            break
                else:
                    break

        # 记录最终违规
        final_validation = self._revalidate(result.final_data)
        result.validation = final_validation
        result.repair.unrepaired_violations = [
            v for v in final_validation.violations
            if v.severity == ConstraintSeverity.BLOCK
        ]

        return result

    def _classify_violations(
        self, violations: list[Violation]
    ) -> tuple[list[Violation], list[Violation], list[Violation]]:
        """分类违规为三个级别"""
        level1 = []  # 程序化
        level2 = []  # 混合
        level3 = []  # LLM

        for v in violations:
            if v.repair_strategy == RepairStrategy.PROGRAMMATIC:
                level1.append(v)
            elif v.repair_strategy == RepairStrategy.HYBRID:
                level2.append(v)
            elif v.repair_strategy == RepairStrategy.LLM:
                level3.append(v)
            # NONE = 不可修复，跳过

        return level1, level2, level3

    def _llm_repair(
        self,
        data: Any,
        violations: list[Violation],
        llm_caller: Callable,
        context: dict | None,
    ) -> Any | None:
        """调用 LLM 修复"""
        prompt = self._build_repair_prompt(data, violations, context)
        try:
            return llm_caller(prompt)
        except Exception:
            return None

    def _build_repair_prompt(
        self, data: Any, violations: list[Violation], context: dict | None
    ) -> str:
        """构建 LLM 修复 prompt"""
        violation_details = []
        for v in violations:
            violation_details.append(
                f"- [{v.constraint_id}] {v.field}: {v.message}\n  修复提示：{v.fix_hint}"
            )

        prompt = f"""## 约束修复任务

你正在修复 Agent 输出的约束违规。

### 违规信息
{chr(10).join(violation_details)}

### 修复要求
- 只修改违规相关的内容
- 不要改变叙事目的
- 不要引入新的违规
- 输出修复后的完整结果

### 当前数据
{data}

### 修复后的结果"""
        return prompt

    def _revalidate(self, data: Any) -> ValidationResult:
        """重新校验数据"""
        from core.constraint_engine import ConstraintValidator
        validator = ConstraintValidator(self.registry)

        if isinstance(data, dict):
            return validator.validate_shot(data)
        elif isinstance(data, list):
            return validator.validate_scene(data)
        return ValidationResult(passed=True)
