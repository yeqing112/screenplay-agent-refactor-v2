"""DirectorPlan shadow-mode persistence.

Phase 0 only persists plans to the ``agent_plans`` table and never
mutates production tables. The function returns a plan dict whose
fingerprint matches ``director_plan_fingerprint`` so audit rows can
reference the same value.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from models import AgentPlan, Session
from models.base import get_kv, set_kv

SHADOW_BOOTSTRAP_KEY = "agent_shadow_bootstrap_v1"


def bootstrap_shadow_state() -> None:
    """Mark that the shadow runtime has been initialised at least once."""
    if get_kv(SHADOW_BOOTSTRAP_KEY):
        return
    set_kv(SHADOW_BOOTSTRAP_KEY, datetime.now().isoformat())


def persist_shadow_plan(plan: dict[str, Any]) -> int:
    """Insert a draft plan row and return the new plan id.

    The function intentionally only ever sets ``status='draft'``. Any
    later transition to ``awaiting_confirmation`` or beyond must go
    through a separate, user-confirmed action.
    """
    if str(plan.get("status") or "draft") != "draft":
        raise ValueError("shadow plans must be saved as draft only")
    with Session() as session:
        row = AgentPlan(
            session_id=0,
            plan_fingerprint=plan.get("plan_fingerprint") or "",
            objective=plan.get("objective") or "",
            scope=json.dumps(plan.get("scope") or {}, ensure_ascii=False),
            evidence_snapshot=json.dumps(plan.get("evidence_snapshot") or {}, ensure_ascii=False),
            steps=json.dumps(plan.get("steps") or [], ensure_ascii=False),
            preconditions=json.dumps(plan.get("preconditions") or [], ensure_ascii=False),
            blocking_issues=json.dumps(plan.get("blocking_issues") or [], ensure_ascii=False),
            approval_policy=json.dumps(plan.get("approval_policy") or {}, ensure_ascii=False),
            cost_envelope=json.dumps(plan.get("cost_envelope") or {}, ensure_ascii=False),
            rollback_anchor=json.dumps(plan.get("rollback_anchor") or {}, ensure_ascii=False),
            status="draft",
        )
        session.add(row)
        session.commit()
        return int(row.id)