"""DirectorPlan shadow API (read-only).

Phase 0 exposes a single ``POST /api/agent/plan`` endpoint that returns
a DirectorPlan derived from a frozen evidence snapshot. The endpoint:

- never calls an external model;
- never mutates production tables;
- optionally persists the plan as a draft row in ``agent_plans`` when
  ``persist=True`` is provided, and even then status stays ``draft``.

The route is intentionally *not* wired into ``api/server.py`` until
Phase 1, so other agents' in-progress work is not affected.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from core.director_plan import build_director_plan, summarise_plan
from core.director_plan_shadow import persist_shadow_plan
from core.director_skills import apply_skill, list_skills

router = APIRouter(prefix="/api/agent", tags=["agent-shadow"])


class ShadowPlanRequest(BaseModel):
    objective: str = ""
    scope: dict[str, Any] = Field(default_factory=dict)
    evidence_snapshot: dict[str, Any] = Field(default_factory=dict)
    candidate_operations: list[dict[str, Any]] = Field(default_factory=list)
    approval_policy: dict[str, Any] = Field(default_factory=dict)
    cost_envelope: dict[str, Any] = Field(default_factory=dict)
    rollback_anchor: dict[str, Any] = Field(default_factory=dict)
    preconditions: list[str] = Field(default_factory=list)
    blocking_issues: list[str] = Field(default_factory=list)
    persist: bool = False
    skill_id: str | None = None


@router.get("/skills")
def get_registered_skills() -> dict[str, Any]:
    return {"skills": list_skills(), "mutated": False}


@router.post("/plan")
def build_shadow_plan(req: ShadowPlanRequest) -> dict[str, Any]:
    try:
        skill, operations = apply_skill(req.skill_id, req.candidate_operations)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    scope = dict(req.scope)
    if skill:
        scope["skill"] = {key: skill[key] for key in ("id", "version", "label", "required_evidence")}
    plan = build_director_plan(
        req.objective,
        scope,
        req.evidence_snapshot,
        operations,
        approval_policy=req.approval_policy,
        cost_envelope=req.cost_envelope,
        rollback_anchor=req.rollback_anchor,
        preconditions=req.preconditions,
        blocking_issues=req.blocking_issues,
    )
    plan_id = None
    if req.persist:
        plan_id = persist_shadow_plan(plan)
    return {
        "plan": plan,
        "summary": summarise_plan(plan),
        "plan_id": plan_id,
        "status": "draft",
    }
