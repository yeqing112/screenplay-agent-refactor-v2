"""Single authority for Smart Director tool permissions and handoff states."""
from __future__ import annotations

from typing import Any

from core.director_plan import classify_tool_tier


TOOL_REGISTRY: dict[str, dict[str, Any]] = {
    "read_state": {"label": "读取项目状态", "execution": "read_only"},
    "diagnose": {"label": "诊断生产状态", "execution": "read_only"},
    "continuity_check": {"label": "诊断镜头连续性", "execution": "read_only"},
    "qa_read": {"label": "读取 QA 问题", "execution": "read_only"},
    "draft_prompt": {"label": "创建提示词候选草案", "execution": "handoff"},
    "draft_repair": {"label": "创建修复候选草案", "execution": "handoff"},
    "write_prompt_version": {"label": "写入 Prompt Version", "execution": "handoff"},
    "write_asset_governance": {"label": "确认资产治理结果", "execution": "handoff"},
    "image_generation": {"label": "提交图片生成", "execution": "handoff"},
    "video_generation": {"label": "提交视频生成", "execution": "handoff"},
}


def resolve_tool(operation: str) -> dict[str, Any]:
    name = str(operation or "").strip()
    tier = classify_tool_tier(name)
    spec = TOOL_REGISTRY.get(name, {"label": name or "未声明操作", "execution": "blocked"})
    return {
        "operation": name,
        "label": spec["label"],
        "tier": tier,
        "execution": spec["execution"],
        "requires_confirmation": tier in {"C", "D"},
        "external_cost": tier == "D",
        "state_before_confirmation": "awaiting_confirmation" if tier in {"C", "D"} else "ready_for_handoff",
        "state_after_confirmation": "handoff_required",
    }


def list_tools() -> list[dict[str, Any]]:
    return [resolve_tool(operation) for operation in sorted(TOOL_REGISTRY)]
