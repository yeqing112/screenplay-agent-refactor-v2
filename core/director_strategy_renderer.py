"""Human-readable Director Brief renderer for Canonical Strategy V3.

Rendering resolves references for display only; it never decides whether a
reference is valid and therefore cannot bypass the deterministic validator.
"""
from __future__ import annotations

from typing import Any


def _text(value: Any) -> str: return str(value or "").strip()
def _dict(value: Any) -> dict[str, Any]: return value if isinstance(value, dict) else {}
def _list(value: Any) -> list[Any]: return value if isinstance(value, list) else []


def render_director_brief_v3(*, strategy: dict[str, Any], contract: dict[str, Any] | None = None) -> str:
    contract = _dict(contract); beats = _dict(contract.get("beats")); lines = [f"# Director Brief — {_text(strategy.get('scene_id'))}", "", "## 导演命题", "", _text(strategy.get("dramatic_objective")), "", "## 观众问题", "", _text(strategy.get("scene_question")), "", "## 视觉命题", "", _text(strategy.get("visual_thesis")), "", "## 场面推进", ""]
    for phase in _list(strategy.get("scene_phases")):
        if not isinstance(phase, dict): continue
        refs = _list(_dict(phase.get("information")).get("reveal_refs")); labels = []
        for ref in refs:
            kind, _, ident = _text(ref).partition(":")
            labels.append(_text(_dict(beats.get(ident)).get("event")) if kind == "beat" and ident in beats else _text(ref))
        lines += [f"### {_text(phase.get('phase_id'))} · beats {', '.join(_text(x) for x in _list(phase.get('beat_ids')))}", "", f"- 明示信息：{'; '.join(labels) or '无'}", f"- 观众猜测：{'; '.join(_text(_dict(x).get('claim')) for x in _list(_dict(phase.get('information')).get('audience_suspicions')) if isinstance(x, dict)) or '无'}", f"- 导演推理：{'; '.join(_text(_dict(x).get('claim')) for x in _list(_dict(phase.get('information')).get('director_inferences')) if isinstance(x, dict)) or '无'}", ""]
    lines += ["## 保留与风险", "", "- 必须保留：" + "；".join(_text(x) for x in _list(strategy.get("must_preserve"))), "- 避免：" + "；".join(_text(x) for x in _list(strategy.get("must_avoid"))), "- 创作风险：" + "；".join(_text(x) for x in _list(strategy.get("creative_risks"))), ""]
    return "\n".join(lines)


__all__ = ["render_director_brief_v3"]
