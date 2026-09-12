"""Deterministic aggregation of production diagnostics into root causes.

The aggregator is a presentation/triage layer only.  It never removes or
rewrites source diagnostics; every symptom remains attached to the root cause
that explains it and the complete flattened list is returned in the report.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Iterable


_SEVERITY_RANK = {"info": 0, "warning": 1, "warn": 1, "error": 2, "blocker": 3, "blocked": 3, "critical": 4}

# Prefixes are intentionally semantic rather than book/sample specific.  New
# codes fall back to a stable token derived from their own code.
_TAXONOMY: tuple[tuple[str, tuple[str, ...], str, str], ...] = (
    ("RC_FACT_SCRIPT_INCOMPLETE", ("fact", "gender", "relationship", "script_ir", "script_", "legacy_reconstruction"), "事实或 ScriptIR 不完整", "补齐来源证据并确认 FactSnapshot/ScriptIR 后再继续。"),
    ("RC_DIRECT_LLM_BYPASS", ("direct_llm", "llm_bypass", "free_generation", "storyboard_agent"), "自由 LLM 绕过生产中间层", "改为 Approved ShotPlan → Storyboard Materializer，并保留生产门禁。"),
    ("RC_SCENE_ASSET_MISSING", ("scene_asset", "scene_canonical", "location_asset", "missing_scene"), "结构化场景资产缺失", "从 qualified ScriptIR 同步资产主卡并完成必要参考图绑定。"),
    ("RC_REQUIRED_ASSET_MISSING", ("asset_", "missing_asset", "required_asset", "asset_binding"), "生产所需资产或绑定缺失", "确认必需资产、作用域和绑定关系，不要在 Prompt 文本中虚构资产。"),
    ("RC_COMPILER_STATE_MISSING", ("prompt_ir", "phase_a", "compiler", "prompt_compiler", "prompt_diagnostics"), "Prompt Compiler 派生状态缺失或过期", "重新运行 deterministic Phase A，并校验 source/evidence fingerprint。"),
    ("RC_EXECUTABILITY_BLOCKED", ("executability", "action_overloaded", "duration", "dialogue_budget", "motion_conflict"), "镜头不可拍或动作超出时长预算", "在 ShotPlan/Executability 层拆镜或补齐动作节拍，不能缩短 Prompt 掩盖。"),
    ("RC_CONTINUITY_CONFLICT", ("continuity", "screen_direction", "state_jump", "entry_state", "exit_state"), "镜头连续性合同冲突", "补齐相邻镜头的 entry/exit state 与承接约束后重新校验。"),
    ("RC_MEDIA_REFERENCE_UNAVAILABLE", ("media", "reference_url", "reference", "image_url", "provider"), "参考媒体不可访问或供应商能力不匹配", "完成媒体可达性/模型能力预检后再提交外部生成。"),
    ("RC_STATE_SEMANTICS_MIXED", ("state_in_canonical", "look_in_canonical", "canonical_state", "semantic"), "资产本体与镜头状态语义混用", "将临时天气、光线和造型变体迁回镜头层，保留可复用资产本体。"),
)


def _flatten_diagnostics(value: Any) -> list[dict[str, Any]]:
    """Extract diagnostic dicts from common report envelopes without loss."""
    if isinstance(value, list):
        result: list[dict[str, Any]] = []
        for item in value:
            result.extend(_flatten_diagnostics(item))
        return result
    if not isinstance(value, dict):
        return []
    # A diagnostic itself is a leaf.  Keep arbitrary extra fields for audit.
    if any(key in value for key in ("code", "issue_code", "severity", "message")):
        return [dict(value)]
    result = []
    for key in ("diagnostics", "issues", "checks", "blocking", "warnings", "errors", "unresolved"):
        nested = value.get(key)
        if isinstance(nested, (list, dict)):
            result.extend(_flatten_diagnostics(nested))
    return result


def _code(item: dict[str, Any]) -> str:
    return str(item.get("code") or item.get("issue_code") or "UNSPECIFIED").strip().lower()


def _token(value: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return token.upper() or "UNSPECIFIED"


def _root_for(item: dict[str, Any]) -> tuple[str, str, str]:
    code = _code(item)
    for root_id, terms, summary, action in _TAXONOMY:
        if any(term in code for term in terms):
            return root_id, summary, action
    # Unknown codes remain grouped by their own stable semantic code, ensuring
    # no unrelated symptoms are accidentally merged.
    token = _token(code)
    return f"RC_{token}", str(item.get("summary") or item.get("message") or code), "查看原始诊断并补充对应责任层的确定性修复。"


def _collect_ids(item: dict[str, Any], *keys: str) -> set[str]:
    values: set[str] = set()
    for key in keys:
        value = item.get(key)
        if isinstance(value, (str, int)) and str(value).strip():
            values.add(str(value))
        elif isinstance(value, (list, tuple, set)):
            values.update(str(v) for v in value if str(v).strip())
    return values


def aggregate_root_causes(diagnostics: Any) -> dict[str, Any]:
    """Aggregate diagnostics while retaining an auditable symptom index.

    ``diagnostics`` may be a list of issue dicts or a report envelope containing
    ``diagnostics``/``issues``/``checks``.  Counts are derived from identifiers
    present on each symptom; no sample/project identifiers are hard-coded.
    """
    symptoms = _flatten_diagnostics(diagnostics)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for symptom in symptoms:
        root_id, _, _ = _root_for(symptom)
        groups[root_id].append(symptom)

    roots: list[dict[str, Any]] = []
    for root_id in sorted(groups):
        items = groups[root_id]
        _, summary, action = _root_for(items[0])
        severity = max((str(item.get("severity") or "warning").lower() for item in items), key=lambda value: _SEVERITY_RANK.get(value, 1))
        scenes: set[str] = set()
        shots: set[str] = set()
        for item in items:
            scenes.update(_collect_ids(item, "scene_id", "scene", "target_scene_id", "affected_scene_id", "scene_ids"))
            shots.update(_collect_ids(item, "shot_id", "shot", "target_id", "target_shot_id", "affected_shot_id", "shot_ids"))
        roots.append({
            "root_cause_id": root_id,
            "severity": severity,
            "summary": summary,
            "affected_scene_count": len(scenes),
            "affected_shot_count": len(shots),
            "symptom_count": len(items),
            "recommended_action": action,
            "symptoms": items,
        })

    return {
        "root_causes": roots,
        "root_cause_count": len(roots),
        "symptom_count": len(symptoms),
        # Explicit source index makes it impossible for a consumer to mistake
        # aggregated counts for the complete diagnostic set.
        "symptoms": symptoms,
    }


def aggregate_diagnostics(diagnostics: Any) -> dict[str, Any]:
    """Compatibility alias used by report builders."""
    return aggregate_root_causes(diagnostics)


class RootCauseAggregator:
    """Small state-free facade for dependency injection in API/report code."""

    def aggregate(self, diagnostics: Any) -> dict[str, Any]:
        return aggregate_root_causes(diagnostics)

