"""Storyboard Validator — 导演 Agent 校验器。

校验时机：每个镜头生成后、每场景完成后。
校验内容：摄影术语、情绪、镜头目的、时长、节奏、连续性。
"""

from __future__ import annotations

from core.constraint_engine import (
    ConstraintRegistry,
    ConstraintSeverity,
    ConstraintTarget,
    ValidationResult,
    Violation,
    get_constraint_registry,
)
from core.validators.programmatic_repair import ProgrammaticRepair, RepairResult


class StoryboardValidator:
    """导演 Agent 校验器"""

    def __init__(self, registry: ConstraintRegistry | None = None):
        self.registry = registry or get_constraint_registry()
        self.repairer = ProgrammaticRepair(self.registry)

    def validate_shot(self, shot: dict) -> ValidationResult:
        """校验单个镜头，返回校验结果"""
        from core.constraint_engine import ConstraintValidator
        validator = ConstraintValidator(self.registry)
        result = validator.validate_shot(shot)
        return result

    def validate_and_repair_shot(self, shot: dict) -> tuple[dict, ValidationResult, RepairResult]:
        """校验 + 自动修复单个镜头"""
        # 1. 校验
        validation = self.validate_shot(shot)

        # 2. 修复
        repair = RepairResult()
        repaired_shot = shot
        if validation.violations:
            repair = self.repairer.repair_shot(shot, validation.violations)
            repaired_shot = repair.modified_data

            # 3. 重新校验修复后的结果
            re_validation = self.validate_shot(repaired_shot)

            # 合并结果：修复后仍然存在的违规 = 未修复
            repaired_ids = {v.constraint_id for v in repair.repaired_violations}
            still_violating = [v for v in re_validation.violations
                             if v.constraint_id not in repaired_ids]
            validation = ValidationResult(
                passed=re_validation.passed,
                violations=still_violating,
                stats=re_validation.stats,
            )

        return repaired_shot, validation, repair

    def validate_scene(self, shots: list[dict]) -> ValidationResult:
        """校验整个场景"""
        from core.constraint_engine import ConstraintValidator
        validator = ConstraintValidator(self.registry)
        result = validator.validate_scene(shots)

        # 场景级别补充检查
        extra_violations = self._check_scene_level(shots)
        existing_locations = {(v.constraint_id, v.location) for v in result.violations}
        extra_violations = [
            v for v in extra_violations
            if (v.constraint_id, v.location) not in existing_locations
        ]
        result.violations.extend(extra_violations)
        result.passed = not any(v.severity == ConstraintSeverity.BLOCK for v in result.violations)
        return result

    def validate_and_repair_scene(self, shots: list[dict]) -> tuple[list[dict], ValidationResult, RepairResult]:
        """校验 + 自动修复整个场景"""
        # 1. 逐镜头校验 + 修复
        repaired_shots = []
        all_repaired = []
        all_unrepaired = []
        all_repair_log = []

        for shot in shots:
            repaired_shot, validation, repair = self.validate_and_repair_shot(shot)
            repaired_shots.append(repaired_shot)
            all_repaired.extend(repair.repaired_violations)
            all_unrepaired.extend(repair.unrepaired_violations)
            all_repair_log.extend(repair.repair_log)

        # 2. 场景级别校验
        scene_validation = self.validate_scene(repaired_shots)

        # 3. 场景级别修复（连续性等）
        if scene_validation.violations:
            scene_repair = self.repairer.repair_scene(repaired_shots, scene_validation.violations)
            repaired_shots = scene_repair.modified_data
            all_repaired.extend(scene_repair.repaired_violations)
            all_unrepaired.extend(scene_repair.unrepaired_violations)
            all_repair_log.extend(scene_repair.repair_log)

            # 重新校验
            scene_validation = self.validate_scene(repaired_shots)

        repair_result = RepairResult(
            repaired_violations=all_repaired,
            unrepaired_violations=all_unrepaired,
            modified_data=repaired_shots,
            repair_log=all_repair_log,
        )

        return repaired_shots, scene_validation, repair_result

    def _check_scene_level(self, shots: list[dict]) -> list[Violation]:
        """场景级别检查"""
        violations = []

        if not shots:
            return violations

        # 1. 首镜必须是 hook（短剧规则）
        first_shot = shots[0]
        if first_shot.get("shot_purpose") == "establish":
            violations.append(Violation(
                constraint_id="OPENING_MUST_BE_HOOK",
                category="forbidden",
                target="shot",
                field="shot_purpose",
                actual_value="establish",
                expected_description="首镜必须是 hook",
                severity=ConstraintSeverity.BLOCK,
                message="短剧首镜不能是 establish，必须是 hook",
                fix_hint="将首镜的 shot_purpose 改为 hook，加入冲突/悬念/反差元素",
                repair_strategy="hybrid",
                source="EPISODE_BEAT_ENGINE",
                location="shot_0",
            ))

        # 2. 末镜必须有悬念元素
        last_shot = shots[-1]
        valid_endings = {"suspense", "reveal", "hook", "cliffhanger"}
        if last_shot.get("shot_purpose") not in valid_endings:
            violations.append(Violation(
                constraint_id="ENDING_MUST_HAVE_SUSPENSE",
                category="hard",
                target="shot",
                field="shot_purpose",
                actual_value=last_shot.get("shot_purpose"),
                expected_description=f"末镜必须是以下之一：{', '.join(valid_endings)}",
                severity=ConstraintSeverity.BLOCK,
                message="短剧末镜必须有悬念元素",
                fix_hint="将末镜的 shot_purpose 改为 suspense 或 reveal",
                repair_strategy="hybrid",
                source="EPISODE_BEAT_ENGINE",
                location=f"shot_{len(shots) - 1}",
            ))

        # 3. 镜头间连续性检查
        for i in range(1, len(shots)):
            prev_end = shots[i - 1].get("end_state", "")
            curr_start = shots[i].get("start_state", "")
            if prev_end and curr_start and prev_end.strip() != curr_start.strip():
                # 简单的文本相似度检查
                if not self._states_compatible(prev_end, curr_start):
                    violations.append(Violation(
                        constraint_id="CONTINUITY_BREAK",
                        category="soft",
                        target="shot",
                        field="start_state",
                        actual_value=curr_start[:50],
                        expected_description=f"应与上一镜 end_state 衔接：{prev_end[:50]}",
                        severity=ConstraintSeverity.WARN,
                        message=f"镜头 {i-1} → {i} 连续性可能断裂",
                        fix_hint=f"将镜头 {i} 的 start_state 改为与上一镜 end_state 衔接",
                        repair_strategy="llm",
                        source="continuity",
                        location=f"shot_{i}",
                    ))

        # 4. 总镜头数检查
        if len(shots) < 4:
            violations.append(Violation(
                constraint_id="SHOT_COUNT_LOW",
                category="soft",
                target="scene",
                field="shot_count",
                actual_value=len(shots),
                expected_description="建议 4-8 个镜头",
                severity=ConstraintSeverity.WARN,
                message=f"场景只有 {len(shots)} 个镜头，建议至少 4 个",
                fix_hint="补充更多镜头以覆盖场景的叙事需求",
                repair_strategy="llm",
                source="scene_shots.txt",
                location="scene",
            ))
        elif len(shots) > 8:
            violations.append(Violation(
                constraint_id="SHOT_COUNT_HIGH",
                category="soft",
                target="scene",
                field="shot_count",
                actual_value=len(shots),
                expected_description="建议 4-8 个镜头",
                severity=ConstraintSeverity.WARN,
                message=f"场景有 {len(shots)} 个镜头，建议不超过 8 个",
                fix_hint="合并相似镜头，精简场景结构",
                repair_strategy="llm",
                source="scene_shots.txt",
                location="scene",
            ))

        return violations

    def _states_compatible(self, prev_end: str, curr_start: str) -> bool:
        """检查两个状态是否兼容"""
        # 简单的关键词重叠检查
        prev_words = set(prev_end)
        curr_words = set(curr_start)
        overlap = len(prev_words & curr_words) / max(len(prev_words | curr_words), 1)
        return overlap > 0.3
