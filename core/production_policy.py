"""Production workflow policy and unified artifact state protocol.

This module is deliberately deterministic and side-effect free.  It is the
single place where callers decide whether an artifact may cross the
production boundary; legacy ``status`` fields remain compatibility data.
"""
from __future__ import annotations

from typing import Any, Mapping

WORKFLOW_PROFILES = {"creative_draft", "production"}
EXECUTION_STATUSES = {"queued", "running", "succeeded", "failed"}
QUALITY_STATUSES = {"draft", "needs_information", "needs_review", "repairing", "qualified", "rejected"}
PRODUCTION_STATUSES = {"blocked", "ready", "locked", "superseded"}


def resolve_workflow_profile(requested: str | None = None, *, deployment_env: str | None = None) -> str:
    """Normalize a profile without allowing unknown values to silently pass.

    Backward-compatible callers with no profile keep the creative draft
    behavior.  Production/staging deployments must opt into ``production``
    explicitly until the rollout gate is enabled for the whole deployment.
    """
    value = str(requested or "").strip().lower()
    if not value:
        return "creative_draft"
    if value not in WORKFLOW_PROFILES:
        raise ValueError(f"workflow_profile must be one of: {', '.join(sorted(WORKFLOW_PROFILES))}")
    return value


def _reason(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def evaluate_production_boundary(
    workflow_profile: str | None,
    *,
    script_ir_qualified: bool = False,
    director_treatment_approved: bool = False,
    scene_blocking_approved: bool = False,
    shot_plan_approved: bool = False,
    compiler_phase_a_pass: bool = False,
    executability_pass: bool = False,
    required_assets_ready: bool = False,
) -> dict[str, Any]:
    """Return a fail-closed, actionable production-boundary decision.

    ``creative_draft`` is intentionally always blocked from production even
    when all individual inputs happen to be present.
    """
    profile = resolve_workflow_profile(workflow_profile)
    if profile == "creative_draft":
        return {
            "workflow_profile": profile,
            "allowed": False,
            "production_status": "blocked",
            "blocking_reasons": [_reason("CREATIVE_DRAFT_BOUNDARY", "creative_draft 只能用于创作预览，不能进入正式生产。")],
        }

    checks = (
        ("SCRIPT_IR_NOT_QUALIFIED", script_ir_qualified, "缺少已合格 ScriptIR。"),
        ("DIRECTOR_TREATMENT_NOT_APPROVED", director_treatment_approved, "DirectorTreatment 尚未批准。"),
        ("SCENE_BLOCKING_NOT_APPROVED", scene_blocking_approved, "SceneBlocking 尚未批准。"),
        ("SHOT_PLAN_NOT_APPROVED", shot_plan_approved, "缺少已批准 ShotPlan。"),
        ("COMPILER_PHASE_A_NOT_PASSED", compiler_phase_a_pass, "Prompt Compiler Phase A 未通过。"),
        ("EXECUTABILITY_NOT_PASSED", executability_pass, "镜头可拍性预检未通过。"),
        ("REQUIRED_ASSETS_NOT_READY", required_assets_ready, "必需资产或锁定参考图未就绪。"),
    )
    reasons = [_reason(code, message) for code, passed, message in checks if not passed]
    return {
        "workflow_profile": profile,
        "allowed": not reasons,
        "production_status": "ready" if not reasons else "blocked",
        "blocking_reasons": reasons,
    }


def normalize_artifact_states(
    *,
    execution_status: str = "queued",
    quality_status: str = "draft",
    production_status: str = "blocked",
    workflow_profile: str = "creative_draft",
) -> dict[str, str]:
    """Validate and normalize the four persisted state fields."""
    values = {
        "execution_status": str(execution_status or "").strip().lower(),
        "quality_status": str(quality_status or "").strip().lower(),
        "production_status": str(production_status or "").strip().lower(),
        "workflow_profile": resolve_workflow_profile(workflow_profile),
    }
    allowed = {
        "execution_status": EXECUTION_STATUSES,
        "quality_status": QUALITY_STATUSES,
        "production_status": PRODUCTION_STATUSES,
    }
    for key, choices in allowed.items():
        if values[key] not in choices:
            raise ValueError(f"{key} must be one of: {', '.join(sorted(choices))}")
    if values["workflow_profile"] == "creative_draft":
        values["production_status"] = "blocked"
    return values


def artifact_state_from_mapping(data: Mapping[str, Any] | None) -> dict[str, str]:
    """Read state fields from arbitrary model/API payloads with safe defaults."""
    source = data if isinstance(data, Mapping) else {}
    return normalize_artifact_states(
        execution_status=str(source.get("execution_status") or "queued"),
        quality_status=str(source.get("quality_status") or "draft"),
        production_status=str(source.get("production_status") or "blocked"),
        workflow_profile=str(source.get("workflow_profile") or "creative_draft"),
    )

