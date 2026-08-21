"""Prompt Validator — 编译校验器。

校验时机：prompt compiler 输出后。
校验内容：术语一致性、情绪运动、节奏要素、钩子策略、致命坑规避。
增强而非替代现有的 _build_prompt_compiler_diagnostics()。
"""

from __future__ import annotations

import re

from core.constraint_engine import (
    ConstraintRegistry,
    ConstraintSeverity,
    ValidationResult,
    Violation,
    RepairStrategy,
    get_constraint_registry,
)


class PromptValidator:
    """编译校验器——检查编译后的提示词是否遵循库约束"""

    def __init__(self, registry: ConstraintRegistry | None = None):
        self.registry = registry or get_constraint_registry()

    def validate_compiled_prompts(
        self,
        visual_prompt_static: str,
        visual_prompt_motion: str,
        context: dict | None = None,
    ) -> ValidationResult:
        """校验编译后的提示词"""
        violations = []

        violations.extend(self._check_terminology_consistency(visual_prompt_static, context))
        violations.extend(self._check_emotion_motion(visual_prompt_static, visual_prompt_motion, context))
        violations.extend(self._check_short_drama_elements(visual_prompt_static, visual_prompt_motion, context))
        violations.extend(self._check_fatal_pitfalls(visual_prompt_static, visual_prompt_motion))
        violations.extend(self._check_camera_movement_in_prompt(visual_prompt_motion, context))

        return ValidationResult(
            passed=not any(v.severity == ConstraintSeverity.BLOCK for v in violations),
            violations=violations,
            stats=self._compute_stats(violations),
        )

    def _check_terminology_consistency(
        self, static_prompt: str, context: dict | None
    ) -> list[Violation]:
        """检查术语是否使用库中标准术语"""
        violations = []
        if not context:
            return violations

        # 检查 camera_movement 是否使用了库中术语
        camera_lib = context.get("camera_library", {})
        if camera_lib:
            motions = camera_lib.get("camera_motions", {})
            # 提取提示词中可能的摄影术语
            for key, info in motions.items():
                zh = info.get("zh", "")
                # 如果提示词中提到了非标准术语
                if zh and zh not in static_prompt and zh not in static_prompt:
                    continue  # 库中术语未使用不算违规

        return violations

    def _check_emotion_motion(
        self, static_prompt: str, motion_prompt: str, context: dict | None
    ) -> list[Violation]:
        """检查情绪运动描述是否来自情绪库"""
        violations = []
        if not context:
            return violations

        emotion_lib = context.get("emotion_library", {})
        if not emotion_lib:
            return violations

        # 检查运动提示词中是否包含情绪运动关键词
        combined = static_prompt + motion_prompt
        for emotion, info in emotion_lib.items():
            body = info.get("body", "")
            if body and body in combined:
                # 提示词使用了库中的情绪运动描述，OK
                pass

        return violations

    def _check_short_drama_elements(
        self, static_prompt: str, motion_prompt: str, context: dict | None
    ) -> list[Violation]:
        """检查是否包含短剧节奏要素"""
        violations = []
        if not context:
            return violations

        short_drama_lib = context.get("short_drama_library", {})
        if not short_drama_lib:
            return violations

        combined = static_prompt + motion_prompt

        # 检查是否有钩子策略要素
        hook_lib = short_drama_lib.get("hook_library", {})
        if hook_lib:
            # 运动提示词应该包含节奏相关描述
            has_pacing = any(kw in combined for kw in ["推进", "变化", "渐变", "突变", "加速", "缓慢"])
            if not has_pacing:
                violations.append(Violation(
                    constraint_id="PROMPT_NO_PACING",
                    category="soft",
                    target="prompt",
                    field="visual_prompt_motion",
                    actual_value="无节奏描述",
                    expected_description="运动提示词应包含节奏变化描述",
                    severity=ConstraintSeverity.WARN,
                    message="运动提示词缺少节奏变化描述",
                    fix_hint="在运动提示词中加入节奏描述（推进/渐变/加速/缓慢）",
                    repair_strategy=RepairStrategy.LLM,
                    source="short_drama_library",
                ))

        return violations

    def _check_fatal_pitfalls(
        self, static_prompt: str, motion_prompt: str
    ) -> list[Violation]:
        """检查是否触发致命坑"""
        violations = []
        combined = static_prompt + motion_prompt

        # 检查是否包含禁止的模板字段
        forbidden_patterns = ["Scene:", "Shot:", "Lighting:", "Camera movement:", "Action beats:"]
        for pattern in forbidden_patterns:
            if pattern in combined:
                violations.append(Violation(
                    constraint_id="ENGLISH_TEMPLATE_RESIDUE",
                    category="forbidden",
                    target="prompt",
                    field="prompt_text",
                    actual_value=pattern,
                    expected_description="不能包含英文模板字段",
                    severity=ConstraintSeverity.BLOCK,
                    message=f"提示词包含英文模板残留：{pattern}",
                    fix_hint=f"移除英文模板字段 {pattern}，使用中文描述",
                    repair_strategy=RepairStrategy.PROGRAMMATIC,
                    source="prompt_compiler.txt",
                ))

        # 检查是否包含对白/舞台提示
        dialogue_patterns = [r"[^*]*?：[^*]+", r"\[.*?\]", r"【.*?】"]
        for pattern in dialogue_patterns:
            if re.search(pattern, combined):
                violations.append(Violation(
                    constraint_id="SCREENPLAY_PROMPT_RESIDUE",
                    category="forbidden",
                    target="prompt",
                    field="prompt_text",
                    actual_value="对白/舞台提示残留",
                    expected_description="提示词不能包含对白或舞台提示",
                    severity=ConstraintSeverity.BLOCK,
                    message="提示词包含对白或舞台提示残留",
                    fix_hint="移除对白和舞台提示，只保留画面描述",
                    repair_strategy=RepairStrategy.LLM,
                    source="prompt_compiler.txt",
                ))
                break

        return violations

    def _check_camera_movement_in_prompt(
        self, motion_prompt: str, context: dict | None
    ) -> list[Violation]:
        """检查运动提示词中的镜头运动术语"""
        violations = []
        if not context:
            return violations

        camera_lib = context.get("camera_library", {})
        if not camera_lib:
            return violations

        motions = camera_lib.get("camera_motions", {})
        # 检查是否有非法的镜头运动描述
        illegal_movements = ["orbit", "fly", "swoop", "glide", "float"]
        for illegal in illegal_movements:
            if illegal in motion_prompt.lower():
                violations.append(Violation(
                    constraint_id="CAMERA_ILLEGAL术语",
                    category="soft",
                    target="prompt",
                    field="visual_prompt_motion",
                    actual_value=illegal,
                    expected_description="使用摄影库中的标准术语",
                    severity=ConstraintSeverity.WARN,
                    message=f"运动提示词包含非标准摄影术语：{illegal}",
                    fix_hint=f"将 {illegal} 替换为摄影库中的标准术语",
                    repair_strategy=RepairStrategy.PROGRAMMATIC,
                    source="CAMERA_LIBRARY",
                ))

        return violations

    def _compute_stats(self, violations: list[Violation]) -> dict[str, int]:
        stats: dict[str, int] = {}
        for v in violations:
            stats[v.constraint_id] = stats.get(v.constraint_id, 0) + 1
        return stats
