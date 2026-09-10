"""Decidable QA resolution criteria.

A QA issue only enters the automated edit loop when it carries a criterion that
can be evaluated deterministically (or by a judge without ambiguity).  Subjective
items (motivation, pacing, hook "impact", prop ambiguity) have no such criterion
and are routed to a human queue, never auto-rewritten.
"""

from __future__ import annotations

import re
from typing import Any

from core.script_beat import build_script_beats, normalize_text

_STRUCTURAL_TYPES = {"format", "output_completeness", "structure", "scene_boundary"}
_SCENE_END_TOKENS = ("场景结束", "结束标记", "缺少结束", "没有结束", "未结束", "缺结束")
_VISUAL_PROOF_MISSING = ("缺失", "缺少", "未给出", "未完整", "截断", "没有")


def build_resolution_criteria(issue: dict[str, Any], beat_ids: list[str]) -> dict[str, Any]:
    """Return a decidable criterion, or ``requires_human`` when none can be fixed."""
    issue_type = str(issue.get("type") or issue.get("rule_family") or "").strip().lower()
    text = " ".join([str(issue.get("title") or ""), str(issue.get("description") or "")])

    if issue_type not in _STRUCTURAL_TYPES:
        return {"kind": "requires_human", "beat_ids": beat_ids, "reason": "该问题为创作主观项，无法给出可判定通过条件，转人工定稿。"}

    if any(token in text for token in _SCENE_END_TOKENS):
        # Adding a scene-end marker creates a NEW structural beat; the decidable
        # criterion is that such a beat now exists, not that the edited beat
        # literally contains the marker.
        return {"kind": "structure_present", "beat_ids": beat_ids, "required_message": "[场景结束]"}

    proof = re.search(r"视觉证明\s*([0-9零一二三四五六七八九十]+)", text)
    if proof and any(token in text for token in _VISUAL_PROOF_MISSING):
        return {"kind": "structure_present", "beat_ids": beat_ids, "required_message": f"视觉证明{proof.group(1)}"}

    return {"kind": "requires_human", "beat_ids": beat_ids, "reason": "该问题无明确可判定条件，转人工定稿。"}


def evaluate_resolution_criteria(content: str, episode: int, criteria: dict[str, Any]) -> tuple[bool, str]:
    """Evaluate one criterion against the current script text.

    ``requires_human`` is not an automated gate: it reports ``True`` so it never
    blocks, but the caller must route it to a human queue rather than treat it
    as a resolved structural issue.
    """
    if not isinstance(criteria, dict):
        return False, "缺少判定条件。"
    kind = criteria.get("kind")
    beats = build_script_beats(content, episode)

    if kind == "requires_human":
        return True, "转人工（不自动断言）。"

    if kind == "contains_required":
        required = normalize_text(str(criteria.get("required") or ""))
        if not required:
            return False, "contains_required 缺少 required。"
        beat_ids = set(criteria.get("beat_ids") or [])
        target = [b for b in beats if b.beat_id in beat_ids] if beat_ids else beats
        hit = [b for b in target if required in normalize_text(b.content)]
        return bool(hit), f"required {'命中' if hit else '未命中'}: {str(criteria.get('required'))}"

    if kind == "structure_present":
        msg = normalize_text(str(criteria.get("required_message") or ""))
        if not msg:
            return False, "structure_present 缺少 required_message。"
        hit = [b for b in beats if msg in normalize_text(b.content)]
        return bool(hit), f"structure {'存在' if hit else '缺失'}: {str(criteria.get('required_message'))}"

    return False, f"未知判定类型：{kind}"


def route_issue(issue: dict[str, Any], beat_anchor_reliable: bool, criteria: dict[str, Any]) -> str:
    """Decide whether an issue should be auto-fixed or routed to a human queue.

    Return ``"auto"`` only when the anchor is reliable AND the criterion is
    decidable (contains_required / structure_present).  Anything else is
    ``"human"`` and must never enter an automatic rewrite loop.
    """
    if not beat_anchor_reliable:
        return "human"
    kind = criteria.get("kind") if isinstance(criteria, dict) else ""
    if kind in {"contains_required", "structure_present"}:
        return "auto"
    return "human"
