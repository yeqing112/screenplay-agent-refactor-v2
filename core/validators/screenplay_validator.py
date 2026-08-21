"""Screenplay Validator — 编剧 Agent 校验器。

校验时机：每个场景生成后、整集完成后。
校验内容：冲突类型、情绪卡点、对白风格、节奏、钩子策略、致命坑。
"""

from __future__ import annotations

import re

from core.constraint_engine import (
    Constraint,
    ConstraintCategory,
    ConstraintRegistry,
    ConstraintSeverity,
    ConstraintTarget,
    RepairStrategy,
    ValidationResult,
    Violation,
    get_constraint_registry,
)
from core.validators.programmatic_repair import ProgrammaticRepair, RepairResult


# ============================================================
# 编剧专属约束
# ============================================================

def _generate_screenplay_constraints() -> list[Constraint]:
    """生成编剧专属约束"""
    from core.short_drama_library import (
        HOOK_LIBRARY,
        SHORT_DRAMA_CONFLICT_PATTERNS,
        SHORT_DRAMA_DIALOGUE_RULES,
        COMMON_PITFALLS,
    )

    constraints = []

    # 冲突类型枚举
    valid_conflicts = set(SHORT_DRAMA_CONFLICT_PATTERNS.keys())
    constraints.append(Constraint(
        id="CONFLICT_TYPE_ENUM",
        category=ConstraintCategory.HARD,
        target=ConstraintTarget.SCENE,
        field="conflict_type",
        rule="enum_match",
        rule_params={"valid_keys": valid_conflicts, "valid_values": valid_conflicts},
        source="SHORT_DRAMA_CONFLICT_PATTERNS",
        severity=ConstraintSeverity.BLOCK,
        message="冲突类型必须使用短剧冲突库中的标准类型",
        fix_hint="从以下合法值中选择：identity_inversion, public_humiliation_reversal, revenge_rebirth, forced_proximity, power_imbalance, secret_revelation, ticking_clock, love_triangle",
        repair_strategy=RepairStrategy.LLM,
    ))

    # 对白长度检查（每句 ≤ 15 字）
    constraints.append(Constraint(
        id="DIALOGUE_LENGTH",
        category=ConstraintCategory.SOFT,
        target=ConstraintTarget.SCENE,
        field="dialogue",
        rule="max_dialogue_length",
        rule_params={"max_chars": 15},
        source="SHORT_DRAMA_DIALOGUE_RULES",
        severity=ConstraintSeverity.WARN,
        message="短剧对白应简短锋利，每句不超过 15 字",
        fix_hint="将长句拆分为短句，删除冗余词汇",
        repair_strategy=RepairStrategy.LLM,
    ))

    return constraints


# ============================================================
# Screenplay Validator
# ============================================================

class ScreenplayValidator:
    """编剧 Agent 校验器"""

    def __init__(self, registry: ConstraintRegistry | None = None):
        self.registry = registry or get_constraint_registry()
        self.repairer = ProgrammaticRepair(self.registry)
        # 注册编剧专属约束
        for c in _generate_screenplay_constraints():
            self.registry.register(c)

    def validate_scene(self, scene_text: str, scene_card: dict | None = None) -> ValidationResult:
        """校验单个场景"""
        violations = []

        # 1. 通用约束校验（如果有结构化数据）
        if scene_card:
            from core.constraint_engine import ConstraintValidator
            validator = ConstraintValidator(self.registry)
            card_result = validator.validate_shot(scene_card)
            violations.extend(card_result.violations)

        # 2. 文本级校验
        violations.extend(self._check_dialogue_length(scene_text))
        violations.extend(self._check_scene_structure(scene_text))
        violations.extend(self._check_fatal_pitfalls(scene_text))

        return ValidationResult(
            passed=not any(v.severity == ConstraintSeverity.BLOCK for v in violations),
            violations=violations,
            stats=self._compute_stats(violations),
        )

    def validate_episode(self, scenes: list[str], scene_cards: list[dict] | None = None) -> ValidationResult:
        """校验整集"""
        all_violations = []

        for i, scene_text in enumerate(scenes):
            card = scene_cards[i] if scene_cards and i < len(scene_cards) else None
            result = self.validate_scene(scene_text, card)
            for v in result.violations:
                v.location = f"scene_{i}/{v.location}"
            all_violations.extend(result.violations)

        # 集级别检查
        all_violations.extend(self._check_episode_hooks(scenes))
        all_violations.extend(self._check_pacing(scenes))

        return ValidationResult(
            passed=not any(v.severity == ConstraintSeverity.BLOCK for v in all_violations),
            violations=all_violations,
            stats=self._compute_stats(all_violations),
        )

    def _check_dialogue_length(self, scene_text: str) -> list[Violation]:
        """检查对白长度"""
        violations = []
        # 匹配对白格式：**角色名：对白内容**
        dialogue_pattern = re.compile(r"\*\*[^*]*?：([^*]+)\*\*")
        for match in dialogue_pattern.finditer(scene_text):
            dialogue = match.group(1).strip()
            # 去掉标点后计算长度
            clean = re.sub(r"[，。！？、；：""''（）\[\]【】]", "", dialogue)
            if len(clean) > 15:
                violations.append(Violation(
                    constraint_id="DIALOGUE_LENGTH",
                    category="soft",
                    target="scene",
                    field="dialogue",
                    actual_value=f"{len(clean)}字",
                    expected_description="每句对白不超过 15 字",
                    severity=ConstraintSeverity.WARN,
                    message=f"对白过长（{len(clean)}字）：{dialogue[:30]}...",
                    fix_hint="将长句拆分为短句，删除冗余词汇",
                    repair_strategy=RepairStrategy.LLM,
                    source="SHORT_DRAMA_DIALOGUE_RULES",
                ))
        return violations

    def _check_scene_structure(self, scene_text: str) -> list[Violation]:
        """检查场景结构"""
        violations = []

        # 检查场景头
        if not re.search(r"##\s*场景", scene_text):
            violations.append(Violation(
                constraint_id="SCENE_HEADER_MISSING",
                category="contract",
                target="scene",
                field="scene_header",
                actual_value="无",
                expected_description="需要场景头（## 场景X：名称）",
                severity=ConstraintSeverity.BLOCK,
                message="场景缺少场景头标记",
                fix_hint="添加场景头：## 场景1：场景名称",
                repair_strategy=RepairStrategy.PROGRAMMATIC,
                source="output_contract",
            ))

        # 检查场景结束标记
        if not re.search(r"（场景结束）|场景结束|\[画面渐隐\]|\[淡出\]", scene_text):
            violations.append(Violation(
                constraint_id="SCENE_ENDING_MISSING",
                category="soft",
                target="scene",
                field="scene_ending",
                actual_value="无",
                expected_description="需要场景结束标记",
                severity=ConstraintSeverity.WARN,
                message="场景缺少结束标记",
                fix_hint="在场景末尾添加（场景结束）或 [画面渐隐]",
                repair_strategy=RepairStrategy.LLM,
                source="output_contract",
            ))

        return violations

    def _check_fatal_pitfalls(self, scene_text: str) -> list[Violation]:
        """检查致命坑"""
        violations = []

        # 开场铺垫检查（前 100 字内不能只有环境描写）
        opening = scene_text[:200] if len(scene_text) > 200 else scene_text
        if re.search(r"阳光|微风|树叶|天空|建筑|街道", opening) and not re.search(r"！|？|：|吵|喊|哭|笑", opening):
            violations.append(Violation(
                constraint_id="SLOW_OPENING",
                category="forbidden",
                target="scene",
                field="opening",
                actual_value="纯铺垫开场",
                expected_description="开场必须有冲突/悬念/反差",
                severity=ConstraintSeverity.BLOCK,
                message="开场铺垫超过 10 秒，观众会直接划走",
                fix_hint="开篇直接上高潮，用冲突/悬念/反差开场",
                repair_strategy=RepairStrategy.LLM,
                source="COMMON_PITFALLS",
            ))

        return violations

    def _check_episode_hooks(self, scenes: list[str]) -> list[Violation]:
        """检查整集钩子策略"""
        violations = []
        if not scenes:
            return violations

        # 首场景必须有钩子
        first_scene = scenes[0]
        if not re.search(r"！|？|冲突|对峙|质问|打脸|背叛|震惊", first_scene):
            violations.append(Violation(
                constraint_id="NO_OPENING_HOOK",
                category="hard",
                target="episode",
                field="opening_hook",
                actual_value="无",
                expected_description="首场景必须有开场钩子",
                severity=ConstraintSeverity.BLOCK,
                message="整集缺少开场钩子，观众会在前 3 秒划走",
                fix_hint="在首场景加入冲突/悬念/反差元素",
                repair_strategy=RepairStrategy.HYBRID,
                source="HOOK_LIBRARY",
            ))

        # 末场景必须有悬念
        last_scene = scenes[-1]
        if not re.search(r"？|悬念|秘密|身份|真相|危机|倒计时", last_scene):
            violations.append(Violation(
                constraint_id="NO_CLIFFHANGER",
                category="hard",
                target="episode",
                field="cliffhanger",
                actual_value="无",
                expected_description="末场景必须有悬念结尾",
                severity=ConstraintSeverity.BLOCK,
                message="整集缺少悬念结尾，观众没有追更欲望",
                fix_hint="在末场景加入悬念元素，在情绪最高点戛然而止",
                repair_strategy=RepairStrategy.HYBRID,
                source="HOOK_LIBRARY",
            ))

        return violations

    def _check_pacing(self, scenes: list[str]) -> list[Violation]:
        """检查节奏"""
        violations = []
        if len(scenes) < 2:
            return violations

        # 检查是否有情绪起伏（不能一直虐或一直爽）
        has虐 = any(re.search(r"被冤枉|被抛弃|被背叛|被羞辱|误解", s) for s in scenes)
        has爽 = any(re.search(r"打脸|复仇|逆袭|身份曝光|真相大白", s) for s in scenes)

        if has虐 and not has爽:
            violations.append(Violation(
                constraint_id="ENDLESS_SUFFERING",
                category="forbidden",
                target="episode",
                field="pacing",
                actual_value="持续虐",
                expected_description="虐-爽交替",
                severity=ConstraintSeverity.BLOCK,
                message="长时间持续虐主角，观众会弃剧",
                fix_hint="在后续场景加入爽点（打脸/复仇/逆袭）",
                repair_strategy=RepairStrategy.LLM,
                source="COMMON_PITFALLS",
            ))

        return violations

    def _compute_stats(self, violations: list[Violation]) -> dict[str, int]:
        """统计违规分布"""
        stats: dict[str, int] = {}
        for v in violations:
            stats[v.constraint_id] = stats.get(v.constraint_id, 0) + 1
        return stats
