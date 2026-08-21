"""Constraint Engine — 约束定义与自动生成。

核心思想：从 17 个基础库自动生成可校验的约束规则，
Agent 输出必须通过约束校验，违规必须有明确的修复路径。

约束分类：
- HARD: 必须通过，否则拦截
- SOFT: 不通过则降分，不拦截
- FORBIDDEN: 触发则直接拒绝
- CONTRACT: 输出格式合约
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


# ============================================================
# 1. 约束数据模型
# ============================================================

class ConstraintCategory(Enum):
    """约束类别"""
    HARD = "hard"           # 必须满足
    SOFT = "soft"           # 建议满足，违反则降分
    FORBIDDEN = "forbidden" # 禁止触发
    CONTRACT = "contract"   # 输出格式合约


class ConstraintSeverity(Enum):
    """违规严重程度"""
    BLOCK = "block"         # 硬拦截
    WARN = "warn"           # 告警
    PENALTY = "penalty"     # 降分


class ConstraintTarget(Enum):
    """约束作用对象"""
    SHOT = "shot"           # 单个镜头
    SCENE = "scene"         # 整个场景
    EPISODE = "episode"     # 整集
    PROMPT = "prompt"       # 编译后的提示词


class RepairStrategy(Enum):
    """修复策略"""
    PROGRAMMATIC = "programmatic"  # 程序化修复
    HYBRID = "hybrid"             # 混合修复
    LLM = "llm"                   # LLM 修复
    NONE = "none"                 # 不可修复


@dataclass
class Constraint:
    """单条约束规则"""
    id: str
    category: ConstraintCategory
    target: ConstraintTarget
    field: str
    rule: str                    # 规则类型: enum_match / range / pattern / custom
    rule_params: dict[str, Any] = field(default_factory=dict)
    source: str = ""             # 来源库名
    severity: ConstraintSeverity = ConstraintSeverity.WARN
    message: str = ""
    fix_hint: str = ""           # 修复提示（喂给 LLM 的反馈）
    repair_strategy: RepairStrategy = RepairStrategy.NONE


@dataclass
class Violation:
    """约束违规记录"""
    constraint_id: str
    category: ConstraintCategory
    target: ConstraintTarget
    field: str
    actual_value: Any
    expected_description: str
    severity: ConstraintSeverity
    message: str
    fix_hint: str
    repair_strategy: RepairStrategy
    source: str = ""
    location: str = ""           # 场景名或镜头 ID


@dataclass
class ValidationResult:
    """校验结果"""
    passed: bool
    violations: list[Violation] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)


# ============================================================
# 2. 规则检查器
# ============================================================

def _check_enum_match(value: Any, valid_keys: set[str], valid_values: set[str]) -> bool:
    """枚举匹配：值必须在合法集合中"""
    value_str = str(value).strip()
    if not value_str:
        return False
    return value_str in valid_keys or value_str in valid_values


def _check_range(value: Any, min_val: float | None, max_val: float | None) -> bool:
    """范围检查：值必须在 [min, max] 范围内"""
    if value is None:
        return True
    try:
        num = float(value)
        if min_val is not None and num < min_val:
            return False
        if max_val is not None and num > max_val:
            return False
        return True
    except (ValueError, TypeError):
        return False


def _check_pattern(value: Any, pattern: str) -> bool:
    """正则匹配：值必须匹配指定模式"""
    value_str = str(value).strip() if value is not None else ""
    if not value_str:
        return False
    return bool(re.search(pattern, value_str))


def _check_forbidden(value: Any, forbidden_values: set[str]) -> bool:
    """禁用检查：值不能在禁用集合中"""
    if not value:
        return True
    return str(value).strip() not in forbidden_values


def _check_min_length(value: Any, min_len: int) -> bool:
    """最小长度检查"""
    if value is None:
        return False
    return len(str(value)) >= min_len


# ============================================================
# 3. 库约束自动生成器
# ============================================================

def generate_camera_constraints() -> list[Constraint]:
    """从摄影库自动生成枚举约束"""
    from core.camera_library import CAMERA_LIBRARY, SHOT_SIZE_LIBRARY, CAMERA_ANGLE_LIBRARY, TRANSITION_LIBRARY, LIGHTING_LIBRARY

    constraints = []

    # camera_movement 枚举
    valid_movements = set(CAMERA_LIBRARY.keys())
    valid_movement_zh = {v["zh"] for v in CAMERA_LIBRARY.values()}
    constraints.append(Constraint(
        id="CAMERA_MOVEMENT_ENUM",
        category=ConstraintCategory.HARD,
        target=ConstraintTarget.SHOT,
        field="camera_movement",
        rule="enum_match",
        rule_params={"valid_keys": valid_movements, "valid_values": valid_movement_zh},
        source="CAMERA_LIBRARY",
        severity=ConstraintSeverity.BLOCK,
        message="镜头运动必须使用摄影库中的标准术语",
        fix_hint="从以下合法值中选择：{valid_values}",
        repair_strategy=RepairStrategy.PROGRAMMATIC,
    ))

    # camera_angle / shot_size 枚举
    valid_angles = set(SHOT_SIZE_LIBRARY.keys())
    valid_angle_zh = {v["zh"] for v in SHOT_SIZE_LIBRARY.values()}
    constraints.append(Constraint(
        id="SHOT_SIZE_ENUM",
        category=ConstraintCategory.HARD,
        target=ConstraintTarget.SHOT,
        field="camera_angle",
        rule="enum_match",
        rule_params={"valid_keys": valid_angles, "valid_values": valid_angle_zh},
        source="SHOT_SIZE_LIBRARY",
        severity=ConstraintSeverity.BLOCK,
        message="景别必须使用景别库中的标准术语",
        fix_hint="从以下合法值中选择：{valid_values}",
        repair_strategy=RepairStrategy.PROGRAMMATIC,
    ))

    # camera_angles 枚举（仰拍/俯拍等）
    valid_cam_angles = set(CAMERA_ANGLE_LIBRARY.keys())
    valid_cam_angle_zh = {v["zh"] for v in CAMERA_ANGLE_LIBRARY.values()}
    constraints.append(Constraint(
        id="CAMERA_ANGLE_ENUM",
        category=ConstraintCategory.SOFT,
        target=ConstraintTarget.SHOT,
        field="camera_angle_detail",
        rule="enum_match",
        rule_params={"valid_keys": valid_cam_angles, "valid_values": valid_cam_angle_zh},
        source="CAMERA_ANGLE_LIBRARY",
        severity=ConstraintSeverity.WARN,
        message="角度描述建议使用角度库中的标准术语",
        fix_hint="从以下合法值中选择：{valid_values}",
        repair_strategy=RepairStrategy.PROGRAMMATIC,
    ))

    # transition 枚举
    valid_transitions = set(TRANSITION_LIBRARY.keys())
    valid_transition_zh = {v["zh"] for v in TRANSITION_LIBRARY.values()}
    constraints.append(Constraint(
        id="TRANSITION_ENUM",
        category=ConstraintCategory.SOFT,
        target=ConstraintTarget.SHOT,
        field="transition",
        rule="enum_match",
        rule_params={"valid_keys": valid_transitions, "valid_values": valid_transition_zh},
        source="TRANSITION_LIBRARY",
        severity=ConstraintSeverity.WARN,
        message="转场方式建议使用转场库中的标准术语",
        fix_hint="从以下合法值中选择：{valid_values}",
        repair_strategy=RepairStrategy.PROGRAMMATIC,
    ))

    return constraints


def generate_emotion_constraints() -> list[Constraint]:
    """从情绪库自动生成枚举约束"""
    from core.emotion_library import EMOTION_MOTION_LIBRARY

    valid_emotions = set(EMOTION_MOTION_LIBRARY.keys())

    return [Constraint(
        id="EMOTION_ENUM",
        category=ConstraintCategory.HARD,
        target=ConstraintTarget.SHOT,
        field="emotion",
        rule="enum_match",
        rule_params={"valid_keys": valid_emotions, "valid_values": valid_emotions},
        source="EMOTION_MOTION_LIBRARY",
        severity=ConstraintSeverity.BLOCK,
        message="情绪必须使用情绪库中的标准术语",
        fix_hint="从以下合法值中选择：{valid_values}",
        repair_strategy=RepairStrategy.PROGRAMMATIC,
    )]


def generate_shot_purpose_constraints() -> list[Constraint]:
    """镜头目的枚举约束"""
    valid_purposes = {"establish", "emotion", "action", "reaction", "transition", "suspense", "reveal", "hook", "cliffhanger"}
    return [Constraint(
        id="SHOT_PURPOSE_ENUM",
        category=ConstraintCategory.HARD,
        target=ConstraintTarget.SHOT,
        field="shot_purpose",
        rule="enum_match",
        rule_params={"valid_keys": valid_purposes, "valid_values": valid_purposes},
        source="scene_shots.txt",
        severity=ConstraintSeverity.BLOCK,
        message="镜头目的必须是合法的枚举值",
        fix_hint="从以下合法值中选择：establish, emotion, action, reaction, transition, suspense, reveal, hook, cliffhanger",
        repair_strategy=RepairStrategy.PROGRAMMATIC,
    )]


def generate_speed_constraints() -> list[Constraint]:
    """运镜速度枚举约束"""
    valid_speeds = {"very_slow", "slow", "medium", "fast"}
    return [Constraint(
        id="SPEED_ENUM",
        category=ConstraintCategory.HARD,
        target=ConstraintTarget.SHOT,
        field="camera_speed",
        rule="enum_match",
        rule_params={"valid_keys": valid_speeds, "valid_values": valid_speeds},
        source="scene_shots.txt",
        severity=ConstraintSeverity.BLOCK,
        message="运镜速度必须是合法的枚举值",
        fix_hint="从以下合法值中选择：very_slow, slow, medium, fast",
        repair_strategy=RepairStrategy.PROGRAMMATIC,
    )]


def generate_duration_constraints() -> list[Constraint]:
    """镜头时长范围约束"""
    return [Constraint(
        id="DURATION_RANGE",
        category=ConstraintCategory.CONTRACT,
        target=ConstraintTarget.SHOT,
        field="duration",
        rule="range",
        rule_params={"min": 2, "max": 6},
        source="scene_shots.txt",
        severity=ConstraintSeverity.BLOCK,
        message="镜头时长必须在 2-6 秒之间",
        fix_hint="将时长调整到 2-6 秒范围内",
        repair_strategy=RepairStrategy.PROGRAMMATIC,
    )]


def generate_short_drama_constraints() -> list[Constraint]:
    """从短剧库自动生成约束"""
    from core.short_drama_library import (
        EPISODE_BEAT_ENGINE,
        HOOK_LIBRARY,
        COMMON_PITFALLS,
        SHORT_DRAMA_PACING_TEMPLATES,
        EMOTION_CHECKPOINT_LIBRARY,
    )

    constraints = []

    # 开场必须是 hook（不能是 establish）
    constraints.append(Constraint(
        id="OPENING_MUST_BE_HOOK",
        category=ConstraintCategory.FORBIDDEN,
        target=ConstraintTarget.SCENE,
        field="shot_purpose",
        rule="forbidden",
        rule_params={"forbidden_values": {"establish"}},
        source="EPISODE_BEAT_ENGINE",
        severity=ConstraintSeverity.BLOCK,
        message="短剧首镜不能是 establish（建立镜头），必须是 hook（钩子镜头）",
        fix_hint="将首镜的 shot_purpose 改为 hook，加入冲突/悬念/反差元素",
        repair_strategy=RepairStrategy.HYBRID,
    ))

    # 结尾必须有悬念元素
    constraints.append(Constraint(
        id="ENDING_MUST_HAVE_SUSPENSE",
        category=ConstraintCategory.HARD,
        target=ConstraintTarget.SCENE,
        field="shot_purpose",
        rule="enum_match",
        rule_params={"valid_keys": {"suspense", "reveal", "hook", "cliffhanger"}, "valid_values": {"suspense", "reveal", "hook", "cliffhanger"}},
        source="EPISODE_BEAT_ENGINE",
        severity=ConstraintSeverity.BLOCK,
        message="短剧末镜必须有悬念元素（suspense/reveal/hook/cliffhanger）",
        fix_hint="将末镜的 shot_purpose 改为 suspense 或 reveal，制造悬念结尾",
        repair_strategy=RepairStrategy.HYBRID,
    ))

    # 情绪卡点枚举
    valid_checkpoints = set(EMOTION_CHECKPOINT_LIBRARY.keys())
    constraints.append(Constraint(
        id="EMOTION_CHECKPOINT_ENUM",
        category=ConstraintCategory.SOFT,
        target=ConstraintTarget.EPISODE,
        field="emotion_checkpoint",
        rule="enum_match",
        rule_params={"valid_keys": valid_checkpoints, "valid_values": valid_checkpoints},
        source="EMOTION_CHECKPOINT_LIBRARY",
        severity=ConstraintSeverity.WARN,
        message="情绪卡点应使用库中的标准类型",
        fix_hint="从以下合法值中选择：abuse, satisfy, sweet,燃, suspense",
        repair_strategy=RepairStrategy.PROGRAMMATIC,
    ))

    return constraints


def generate_format_constraints() -> list[Constraint]:
    """输出格式合约约束"""
    return [
        Constraint(
            id="STATIC_PROMPT_MIN_CHARS",
            category=ConstraintCategory.CONTRACT,
            target=ConstraintTarget.PROMPT,
            field="visual_prompt_static",
            rule="min_length",
            rule_params={"min_len": 24},
            source="prompt_compiler.txt",
            severity=ConstraintSeverity.WARN,
            message="静态提示词不少于 24 字",
            fix_hint="补充场景空间、主体人物、光线氛围等细节",
            repair_strategy=RepairStrategy.LLM,
        ),
        Constraint(
            id="MOTION_PROMPT_MIN_CHARS",
            category=ConstraintCategory.CONTRACT,
            target=ConstraintTarget.PROMPT,
            field="visual_prompt_motion",
            rule="min_length",
            rule_params={"min_len": 28},
            source="prompt_compiler.txt",
            severity=ConstraintSeverity.WARN,
            message="运动提示词不少于 28 字",
            fix_hint="补充运镜方式、人物动作推进、节奏变化等细节",
            repair_strategy=RepairStrategy.LLM,
        ),
    ]


# ============================================================
# 4. 约束注册表
# ============================================================

class ConstraintRegistry:
    """约束注册表——管理所有约束规则"""

    def __init__(self):
        self._constraints: dict[str, Constraint] = {}
        self._auto_generate()

    def _auto_generate(self):
        """从所有库自动生成约束"""
        generators = [
            generate_camera_constraints,
            generate_emotion_constraints,
            generate_shot_purpose_constraints,
            generate_speed_constraints,
            generate_duration_constraints,
            generate_short_drama_constraints,
            generate_format_constraints,
        ]
        for gen in generators:
            for constraint in gen():
                self._constraints[constraint.id] = constraint

    def register(self, constraint: Constraint):
        """注册自定义约束"""
        self._constraints[constraint.id] = constraint

    def get(self, constraint_id: str) -> Constraint | None:
        return self._constraints.get(constraint_id)

    def get_by_target(self, target: ConstraintTarget) -> list[Constraint]:
        return [c for c in self._constraints.values() if c.target == target]

    def get_by_category(self, category: ConstraintCategory) -> list[Constraint]:
        return [c for c in self._constraints.values() if c.category == category]

    def get_all(self) -> list[Constraint]:
        return list(self._constraints.values())

    def get_enum_valid_values(self, constraint_id: str) -> set[str]:
        """获取枚举约束的合法值集合"""
        constraint = self._constraints.get(constraint_id)
        if not constraint or constraint.rule != "enum_match":
            return set()
        params = constraint.rule_params
        return params.get("valid_keys", set()) | params.get("valid_values", set())


# ============================================================
# 5. 通用校验器
# ============================================================

class ConstraintValidator:
    """通用约束校验器"""

    def __init__(self, registry: ConstraintRegistry | None = None):
        self.registry = registry or ConstraintRegistry()

    def validate_shot(self, shot: dict) -> ValidationResult:
        """校验单个镜头"""
        violations = []
        shot_constraints = self.registry.get_by_target(ConstraintTarget.SHOT)

        for constraint in shot_constraints:
            value = shot.get(constraint.field)
            passed = self._check_constraint(value, constraint)
            if not passed:
                violations.append(self._make_violation(constraint, value, shot))

        return ValidationResult(
            passed=not any(v.severity == ConstraintSeverity.BLOCK for v in violations),
            violations=violations,
            stats=self._compute_stats(violations),
        )

    def validate_scene(self, shots: list[dict]) -> ValidationResult:
        """校验整个场景"""
        all_violations = []
        for i, shot in enumerate(shots):
            result = self.validate_shot(shot)
            for v in result.violations:
                v.location = f"shot_{i}"
            all_violations.extend(result.violations)

        all_violations.extend(self._validate_scene_constraints(shots))

        return ValidationResult(
            passed=not any(v.severity == ConstraintSeverity.BLOCK for v in all_violations),
            violations=all_violations,
            stats=self._compute_stats(all_violations),
        )

    def validate_episode(self, scenes: list[list[dict]]) -> ValidationResult:
        """校验整集"""
        all_violations = []

        # 逐场景校验
        for scene_idx, shots in enumerate(scenes):
            result = self.validate_scene(shots)
            for v in result.violations:
                v.location = f"scene_{scene_idx}/{v.location}"
            all_violations.extend(result.violations)

        # 集级别校验
        episode_constraints = self.registry.get_by_target(ConstraintTarget.EPISODE)
        # 集级别校验需要聚合数据，这里预留接口

        return ValidationResult(
            passed=not any(v.severity == ConstraintSeverity.BLOCK for v in all_violations),
            violations=all_violations,
            stats=self._compute_stats(all_violations),
        )

    def _check_constraint(self, value: Any, constraint: Constraint) -> bool:
        """根据规则类型执行校验"""
        if constraint.rule == "enum_match":
            params = constraint.rule_params
            return _check_enum_match(
                value,
                params.get("valid_keys", set()),
                params.get("valid_values", set()),
            )
        elif constraint.rule == "range":
            params = constraint.rule_params
            return _check_range(value, params.get("min"), params.get("max"))
        elif constraint.rule == "pattern":
            return _check_pattern(value, constraint.rule_params.get("pattern", ""))
        elif constraint.rule == "forbidden":
            return _check_forbidden(value, constraint.rule_params.get("forbidden_values", set()))
        elif constraint.rule == "min_length":
            return _check_min_length(value, constraint.rule_params.get("min_len", 0))
        return True

    def _validate_scene_constraints(self, shots: list[dict]) -> list[Violation]:
        """Validate constraints that require scene position context."""
        if not shots:
            return []

        violations: list[Violation] = []
        constraints = {c.id: c for c in self.registry.get_by_target(ConstraintTarget.SCENE)}

        opening = constraints.get("OPENING_MUST_BE_HOOK")
        first_shot = shots[0]
        if opening and not self._check_constraint(first_shot.get(opening.field), opening):
            violation = self._make_violation(opening, first_shot.get(opening.field), first_shot)
            violation.location = "shot_0"
            violations.append(violation)

        ending = constraints.get("ENDING_MUST_HAVE_SUSPENSE")
        last_shot = shots[-1]
        if ending and not self._check_constraint(last_shot.get(ending.field), ending):
            violation = self._make_violation(ending, last_shot.get(ending.field), last_shot)
            violation.location = f"shot_{len(shots) - 1}"
            violations.append(violation)

        return violations

    def _make_violation(self, constraint: Constraint, actual_value: Any, context: dict) -> Violation:
        """构造违规记录"""
        expected_desc = self._format_expected(constraint)
        message = f"{constraint.message}（实际值：{actual_value}）"
        fix_hint = constraint.fix_hint
        if "{valid_values}" in fix_hint:
            valid_vals = self.registry.get_enum_valid_values(constraint.id)
            fix_hint = fix_hint.replace("{valid_values}", ", ".join(sorted(valid_vals)[:20]))

        return Violation(
            constraint_id=constraint.id,
            category=constraint.category,
            target=constraint.target,
            field=constraint.field,
            actual_value=actual_value,
            expected_description=expected_desc,
            severity=constraint.severity,
            message=message,
            fix_hint=fix_hint,
            repair_strategy=constraint.repair_strategy,
            source=constraint.source,
        )

    def _format_expected(self, constraint: Constraint) -> str:
        """格式化期望值描述"""
        if constraint.rule == "enum_match":
            params = constraint.rule_params
            valid = params.get("valid_keys", set()) | params.get("valid_values", set())
            return f"必须是以下之一：{', '.join(sorted(valid)[:15])}"
        elif constraint.rule == "range":
            params = constraint.rule_params
            return f"范围 [{params.get('min', '?')}, {params.get('max', '?')}]"
        elif constraint.rule == "forbidden":
            params = constraint.rule_params
            return f"不能是：{', '.join(sorted(params.get('forbidden_values', set())))}"
        elif constraint.rule == "min_length":
            params = constraint.rule_params
            return f"长度 ≥ {params.get('min_len', 0)}"
        return ""

    def _compute_stats(self, violations: list[Violation]) -> dict[str, int]:
        """统计违规分布"""
        stats: dict[str, int] = {}
        for v in violations:
            stats[v.constraint_id] = stats.get(v.constraint_id, 0) + 1
        return stats


# ============================================================
# 6. 模糊匹配（用于程序化修复）
# ============================================================

def find_closest_enum(value: str, valid_keys: set[str], valid_values: set[str]) -> str | None:
    """从合法值集合中找到最接近的匹配"""
    if not value:
        return None
    value_lower = value.strip().lower()

    # 1. 精确匹配
    if value in valid_keys or value in valid_values:
        return value

    # 2. 包含匹配
    for key in valid_keys:
        if value_lower in key.lower() or key.lower() in value_lower:
            return key
    for val in valid_values:
        if value_lower in val.lower() or val.lower() in value_lower:
            return val

    # 3. 编辑距离
    best_match = None
    best_distance = float("inf")
    for key in valid_keys:
        d = _levenshtein(value_lower, key.lower())
        if d < best_distance:
            best_distance = d
            best_match = key
    for val in valid_values:
        d = _levenshtein(value_lower, val.lower())
        if d < best_distance:
            best_distance = d
            best_match = val

    if best_distance <= 3:
        return best_match
    return None


def _levenshtein(s1: str, s2: str) -> int:
    """编辑距离"""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]


# ============================================================
# 7. 全局实例
# ============================================================

_registry: ConstraintRegistry | None = None


def get_constraint_registry() -> ConstraintRegistry:
    """获取全局约束注册表（懒加载）"""
    global _registry
    if _registry is None:
        _registry = ConstraintRegistry()
    return _registry


def get_constraint_validator() -> ConstraintValidator:
    """获取全局约束校验器"""
    return ConstraintValidator(get_constraint_registry())
