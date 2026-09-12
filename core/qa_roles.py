"""Explicit QA responsibility boundaries and production-pass metrics.

Validator diagnostics answer whether an artifact is structurally/operationally
correct.  Director QA supplies creative recommendations, while Human Review is
reserved for an intentional creative decision or explicit approval.  These
helpers are deterministic and can be consumed by existing QA/readiness APIs.
"""
from __future__ import annotations

from typing import Any

VALIDATOR = "validator"
DIRECTOR_QA = "director_qa"
HUMAN_REVIEW = "human_review"

_VALIDATOR_TERMS = (
    "schema", "fact", "gender", "relationship", "asset", "reference", "media",
    "continuity", "screen_direction", "executability", "duration", "action_overloaded",
    "shot_plan", "shotplan", "prompt_ir", "compiler", "provider", "binding", "structure",
)
_DIRECTOR_TERMS = ("style", "pacing", "rhythm", "emotion", "hook", "flat", "repetitive", "motivation", "reveal")
_HUMAN_TERMS = ("approval", "approve", "choice", "creative_decision", "human_review", "confirm")


def classify_qa_role(issue: dict[str, Any]) -> str:
    """Classify one issue without changing its severity or source fields."""
    if not isinstance(issue, dict):
        return HUMAN_REVIEW
    explicit = str(issue.get("qa_role") or issue.get("role") or "").strip().lower()
    if explicit in {VALIDATOR, DIRECTOR_QA, HUMAN_REVIEW}:
        return explicit
    code = str(issue.get("code") or issue.get("issue_code") or issue.get("type") or "").strip().lower()
    text = " ".join(str(issue.get(key) or "").lower() for key in ("title", "description", "message"))
    if any(term in code or term in text for term in _HUMAN_TERMS):
        return HUMAN_REVIEW
    if any(term in code or term in text for term in _VALIDATOR_TERMS):
        return VALIDATOR
    if any(term in code or term in text for term in _DIRECTOR_TERMS):
        return DIRECTOR_QA
    # Unknown machine diagnostics are safer in the human queue until a
    # deterministic validator contract is declared.
    return HUMAN_REVIEW


def _iter_issues(value: Any):
    if isinstance(value, list):
        for item in value:
            yield from _iter_issues(item)
    elif isinstance(value, dict):
        if any(key in value for key in ("code", "issue_code", "severity", "message")):
            yield value
        else:
            for key in ("issues", "diagnostics", "checks", "blocking", "warnings", "errors"):
                if isinstance(value.get(key), (list, dict)):
                    yield from _iter_issues(value[key])


def build_production_pass_metrics(source: Any) -> dict[str, Any]:
    """Return the release-gate hard metrics while preserving all issue rows."""
    issues = list(_iter_issues(source))
    def code(item: dict[str, Any]) -> str:
        return str(item.get("code") or item.get("issue_code") or "").strip().lower()
    def severity(item: dict[str, Any]) -> str:
        return str(item.get("severity") or "").strip().lower()

    blocked = [item for item in issues if severity(item) in {"blocked", "blocker", "error", "critical"}]
    def count(predicate) -> int:
        return sum(1 for item in issues if predicate(code(item), severity(item), item))
    metrics = {
        "hard_error_count": sum(1 for item in issues if severity(item) in {"error", "critical"}),
        "production_blocker_count": len(blocked),
        "missing_required_asset_count": count(lambda c, _s, _i: any(term in c for term in ("missing_asset", "required_asset", "asset_binding", "scene_asset"))),
        "broken_reference_count": count(lambda c, _s, _i: any(term in c for term in ("reference_url", "broken_reference", "reference_unavailable"))),
        "shotplan_violation_count": count(lambda c, _s, _i: "shot_plan" in c or "shotplan" in c),
        "continuity_hard_conflict_count": count(lambda c, s, _i: ("continuity" in c or "screen_direction" in c or "state_jump" in c) and s in {"blocked", "blocker", "error", "critical"}),
        "executability_blocked_count": count(lambda c, s, _i: "executability" in c and s in {"blocked", "blocker", "error", "critical"}),
    }
    metrics["production_pass"] = all(value == 0 for key, value in metrics.items() if key.endswith("_count"))
    metrics["issue_count"] = len(issues)
    metrics["issues"] = issues
    return metrics


def annotate_issues(issues: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Add a role field for UI consumers without mutating the input objects."""
    return [{**item, "qa_role": classify_qa_role(item)} for item in (issues or []) if isinstance(item, dict)]

