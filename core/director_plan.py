"""DirectorPlan: shadow-mode planner for the smart director workspace.

Phase 0 only produces a *plan*; it never calls an external model, never
writes to production tables, and never advances an agent session past
``draft``. The plan is a frozen JSON object whose shape mirrors the
DirectorPlan contract defined in the blueprint.

The planner consumes a DecisionPacket-style evidence snapshot and a
list of candidate tool calls (already described by the caller). It then:

- groups steps into the four A / B / C / D tiers;
- records preconditions, blocking issues and rollback anchors;
- derives a stable plan fingerprint using the same hashing rules used
  by ``core.decision_packet``.

The planner is intentionally pure: it has no DB, network, or LLM
dependency. All persistence and execution concerns live in
``api.director_plan_api`` (read-only shadow endpoints).
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

TOOL_TIERS = {"A", "B", "C", "D"}
PLAN_STATUS = {"draft", "awaiting_confirmation", "running", "accepted", "rejected", "blocked", "completed"}
SCOPE_KEY_PATTERN = re.compile(r"[^a-zA-Z0-9_]+")


def _norm(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _norm(value[k]) for k in sorted(value.keys())}
    if isinstance(value, list):
        return [_norm(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _safe_scope_key(value: Any) -> str:
    text = "" if value is None else str(value)
    text = SCOPE_KEY_PATTERN.sub("_", text).strip("_").lower()
    return text or "global"


def _default_evidence_snapshot(evidence: Any) -> dict[str, Any]:
    if isinstance(evidence, list):
        return {"items": evidence}
    if isinstance(evidence, dict):
        return evidence
    return {}


def classify_tool_tier(operation: str) -> str:
    """Map an operation name to its A / B / C / D tier.

    A: read-only diagnosis. B: reversible internal draft. C: versioned
    write. D: external cost or irreversible change. Anything unrecognised
    defaults to D so that unverified operations never become auto-executed.
    """
    name = (operation or "").strip().lower()
    if not name:
        return "D"
    if name in {
        "read_state",
        "diagnose",
        "summarize_evidence",
        "explain_failure",
        "continuity_check",
        "qa_read",
        "script_read",
    }:
        return "A"
    if name in {
        "draft_prompt",
        "draft_repair",
        "draft_storyboard_split",
        "draft_remediation",
        "draft_skill_output",
    }:
        return "B"
    if name in {
        "write_asset_governance",
        "write_prompt_version",
        "adopt_storyboard_split",
        "adopt_script_revision",
    }:
        return "C"
    return "D"


def build_director_plan(
    objective: str,
    scope: dict[str, Any],
    evidence_snapshot: dict[str, Any] | None,
    candidate_operations: list[dict[str, Any]],
    approval_policy: dict[str, Any] | None = None,
    cost_envelope: dict[str, Any] | None = None,
    rollback_anchor: dict[str, Any] | None = None,
    preconditions: list[str] | None = None,
    blocking_issues: list[str] | None = None,
) -> dict[str, Any]:
    """Construct a DirectorPlan and return the plan + its fingerprint.

    The plan only *describes* what the agent would do; it never performs
    the actions. ``candidate_operations`` is a list of dicts each with at
    least ``operation`` and an optional ``description`` / ``params``.
    """
    safe_scope = scope if isinstance(scope, dict) else {}
    steps: list[dict[str, Any]] = []
    tier_counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    for index, raw in enumerate(candidate_operations or []):
        if not isinstance(raw, dict):
            continue
        operation = str(raw.get("operation") or "").strip()
        tier = classify_tool_tier(operation)
        tier_counts[tier] += 1
        steps.append(
            {
                "index": index,
                "operation": operation,
                "description": str(raw.get("description") or ""),
                "tier": tier,
                "requires_confirmation": tier in {"C", "D"},
                "params": raw.get("params") if isinstance(raw.get("params"), dict) else {},
            }
        )

    pre = [str(x) for x in (preconditions or []) if str(x).strip()]
    blocks = [str(x) for x in (blocking_issues or []) if str(x).strip()]

    plan: dict[str, Any] = {
        "objective": str(objective or "").strip(),
        "scope": safe_scope,
        "scope_key": _safe_scope_key(safe_scope.get("key") or safe_scope.get("name") or safe_scope.get("book_id")),
        "evidence_snapshot": _default_evidence_snapshot(evidence_snapshot),
        "steps": steps,
        "tier_counts": tier_counts,
        "preconditions": pre,
        "blocking_issues": blocks,
        "approval_policy": approval_policy if isinstance(approval_policy, dict) else {},
        "cost_envelope": cost_envelope if isinstance(cost_envelope, dict) else {},
        "rollback_anchor": rollback_anchor if isinstance(rollback_anchor, dict) else {},
        "status": "draft",
        "auto_executable": all(step["tier"] in {"A", "B"} for step in steps),
    }
    plan["plan_fingerprint"] = director_plan_fingerprint(plan)
    return plan


def director_plan_fingerprint(plan: dict[str, Any]) -> str:
    """Stable fingerprint for a plan object.

    Mirrors ``decision_packet_fingerprint`` style so audit logs and
    DecisionPacketRecord evidence can be cross-referenced.
    """
    normalized = _norm(
        {
            "objective": plan.get("objective"),
            "scope": plan.get("scope"),
            "evidence_snapshot": plan.get("evidence_snapshot"),
            "steps": [
                {
                    "operation": s.get("operation"),
                    "tier": s.get("tier"),
                    "params": s.get("params"),
                }
                for s in (plan.get("steps") or [])
            ],
            "preconditions": plan.get("preconditions"),
            "blocking_issues": plan.get("blocking_issues"),
            "approval_policy": plan.get("approval_policy"),
            "cost_envelope": plan.get("cost_envelope"),
            "rollback_anchor": plan.get("rollback_anchor"),
        }
    )
    raw = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def summarise_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Return a small, UI-friendly summary for shadow-mode display."""
    return {
        "plan_fingerprint": plan.get("plan_fingerprint"),
        "status": plan.get("status"),
        "tier_counts": plan.get("tier_counts") or {"A": 0, "B": 0, "C": 0, "D": 0},
        "step_count": len(plan.get("steps") or []),
        "blocking_issues": plan.get("blocking_issues") or [],
        "auto_executable": bool(plan.get("auto_executable")),
    }