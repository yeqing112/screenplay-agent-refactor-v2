"""镜头可拍性与时长承载校验。

第一阶段只做纯函数审查，不直接修改镜头数据；结果可被 Prompt IR、QA 和
真实生成门禁复用。
"""

from __future__ import annotations

import re
from typing import Any


_ACTION_SPLIT_RE = re.compile(r"[。！？；]|随后|然后|接着|再将|再把|并将|并把|同时")
_MOTION_ACTION_MARKERS = (
    "扫码", "支付", "掏出", "取出", "拿出", "放在", "放置", "推到", "推向",
    "缩回", "收回", "伸入", "入画", "抬眼", "凝视", "看向", "转身", "离开",
    "拿起", "放下", "递给", "进入", "走向",
)


def _normalized_duration(value: Any) -> int:
    try:
        return max(1, int(value or 3))
    except (TypeError, ValueError):
        return 3


def _count_action_units(text: str) -> int:
    normalized = str(text or "").strip()
    if not normalized:
        return 0
    parts = [part.strip() for part in _ACTION_SPLIT_RE.split(normalized) if part.strip()]
    return max(1, len(parts))


def _action_units(text: str, beats: list[dict[str, Any]]) -> list[str]:
    declared = [_extract_action_text(item) for item in beats if _extract_action_text(item)]
    parts = [part.strip(" ，,；;。！？") for part in _ACTION_SPLIT_RE.split(str(text or "")) if part.strip(" ，,；;。！？")]
    # Keep explicit director event boundaries when an upstream compiler has
    # compressed several events into one beat.  This is a structural count
    # comparison, not keyword-based rewriting of any particular shot.
    return parts if len(parts) > len(declared) else (declared or parts)


def _split_suggestion(units: list[str], seconds: int) -> dict[str, Any]:
    # One candidate per declared visual unit preserves camera/event boundaries.
    # The apply transaction supports arbitrary N, so do not force unrelated
    # reveals or reactions back into a synthetic two-shot split.
    candidates = []
    for index, unit in enumerate(units or ["保留结尾的信息揭示或情绪反应"], start=1):
        candidates.append({
            "sequence": index,
            "recommended_duration": max(2, min(4, seconds)),
            "purpose": "建立动作或信息焦点" if index == 1 else "完成后续揭示或情绪反应",
            "action_beats": [unit],
        })
    return {
        "type": "split_shot",
        "reason": "将动作铺垫与信息揭示/情绪落点拆成连续镜头，降低单镜头时序负担。",
        "candidates": candidates,
    }


def _extract_action_text(beat: dict[str, Any]) -> str:
    return str(
        beat.get("description")
        or beat.get("action")
        or beat.get("text")
        or ""
    ).strip()


def _motion_action_units(text: str) -> list[str]:
    """Extract concrete visual actions from the final submitted motion prompt."""
    units: list[str] = []
    for sentence in re.split(r"[。！？；\n]", str(text or "")):
        normalized = sentence.strip()
        if not normalized or normalized.startswith(("全过程不", "不出现", "保持", "开头承接", "结束落点")):
            continue
        for clause in re.split(r"[，,、]", normalized):
            clause = clause.strip()
            if not clause:
                continue
            if any(marker in clause for marker in _MOTION_ACTION_MARKERS):
                units.append(clause)
    return list(dict.fromkeys(units))


def validate_shot_executability(
    *,
    duration: Any,
    action_process: str = "",
    action_beats: list[dict[str, Any]] | None = None,
    camera_movement: str = "static",
    start_state: str = "",
    end_state: str = "",
    motion_prompt: str = "",
) -> dict[str, Any]:
    """返回可拍性审查结果，不改变输入数据。"""
    seconds = _normalized_duration(duration)
    beats = [item for item in (action_beats or []) if isinstance(item, dict) and _extract_action_text(item)]
    declared_count = len(beats)
    text_count = _count_action_units(action_process)
    action_count = max(declared_count, text_count)
    units = _action_units(action_process, beats)
    motion_units = _motion_action_units(motion_prompt)
    effective_action_count = max(action_count, len(motion_units))

    recommended_max = 2 if seconds <= 4 else 4 if seconds <= 6 else 6
    findings: list[dict[str, Any]] = []
    suggestions: list[dict[str, Any]] = []

    if not action_process.strip() and not beats:
        findings.append({
            "code": "missing_core_action",
            "severity": "blocked",
            "message": "镜头没有可识别的核心动作。",
        })
    elif effective_action_count > recommended_max:
        findings.append({
            "code": "action_overloaded",
            "severity": "warning" if seconds >= 6 else "blocked",
            "message": f"{seconds} 秒镜头包含约 {effective_action_count} 个动作单元，建议不超过 {recommended_max} 个。",
            "action_count": effective_action_count,
            "recommended_max": recommended_max,
        })
        suggestions.extend([
            {"type": "extend_duration", "recommended_duration": min(max(seconds + 2, 6), 15)},
            {"type": "trim_non_core_actions", "keep": "保留唯一核心动作和结束情绪落点"},
            _split_suggestion(motion_units or units, seconds),
        ])

    if motion_units and len(motion_units) > action_count:
        findings.append({
            "code": "motion_prompt_action_drift",
            "severity": "warning" if effective_action_count <= recommended_max else "blocked",
            "message": f"最终运动提示词识别到 {len(motion_units)} 个动作，但结构化节拍仅覆盖约 {action_count} 个；请同步节拍或精简运动提示词。",
            "motion_action_count": len(motion_units),
            "structured_action_count": action_count,
        })

    if camera_movement.strip().lower() not in {"", "static", "固定", "锁定"} and effective_action_count >= 3:
        findings.append({
            "code": "movement_action_conflict",
            "severity": "warning",
            "message": "镜头运动与多动作并行，可能降低生成稳定性。",
        })

    if not start_state.strip() or not end_state.strip():
        findings.append({
            "code": "continuity_state_incomplete",
            "severity": "warning",
            "message": "镜头缺少完整的入镜或出镜状态，前后镜头承接需人工确认。",
        })

    blocked = any(item.get("severity") == "blocked" for item in findings)
    return {
        "status": "blocked" if blocked else "warning" if findings else "pass",
        "duration": seconds,
        "action_count": effective_action_count,
        "structured_action_count": action_count,
        "motion_prompt_action_count": len(motion_units),
        "recommended_max_actions": recommended_max,
        "findings": findings,
        "suggestions": suggestions,
    }
