"""Unified first-pass qualification loop with bounded local repairs."""
from __future__ import annotations

import copy
from typing import Any, Callable

from core.issue_router import route_issues
from core.local_repair import apply_local_repair, fingerprint


Validator = Callable[[dict[str, Any]], list[dict[str, Any]]]


def _repair_unavailable(blockers: list[dict[str, Any]]) -> bool:
    """Return whether at least one blocker has no explicit executable patch.

    The qualification loop is intentionally conservative: it must not invent a
    repair from a diagnostic that only describes a problem.  Exposing this bit
    in the result lets callers distinguish "bounded attempts exhausted" from
    "no repair was supplied" without pretending that another attempt would
    make progress.
    """
    return any(not isinstance(item.get("patch"), list) or not item.get("patch") for item in blockers)


def qualify_candidate(candidate: dict[str, Any], validators: list[Validator] | None = None, *, max_attempts: int = 2) -> dict[str, Any]:
    current = copy.deepcopy(candidate)
    attempts: list[dict[str, Any]] = []
    limit = max(0, int(max_attempts))
    for attempt in range(limit + 1):
        issues: list[dict[str, Any]] = []
        for validator in validators or []:
            result = validator(current) or []
            issues.extend(item for item in result if isinstance(item, dict))
        routed = route_issues(issues)
        blockers = [item for item in routed if item.get("blocking")]
        if not blockers:
            return {"status": "qualified", "candidate": current, "attempts": attempts, "unresolved": routed, "repair_unavailable": False, "final_fingerprint": fingerprint(current)}
        if attempt >= limit:
            return {"status": "needs_review", "candidate": current, "attempts": attempts, "unresolved": routed, "repair_unavailable": _repair_unavailable(blockers), "final_fingerprint": fingerprint(current)}
        repairs = []
        changed = False
        for issue in blockers:
            if not isinstance(issue.get("patch"), list) or not issue["patch"]:
                continue
            repair = apply_local_repair(current, issue)
            current = repair["candidate"]
            repairs.append({"issue_code": issue.get("code"), **{key: repair[key] for key in ("before_fingerprint", "after_fingerprint", "target_layer", "changed", "rollback_candidate")}})
            changed = changed or repair["changed"]
        attempts.append({"attempt": attempt + 1, "issues": routed, "repairs": repairs, "changed": changed})
        if not changed:
            return {"status": "needs_review", "candidate": current, "attempts": attempts, "unresolved": routed, "repair_unavailable": _repair_unavailable(blockers), "final_fingerprint": fingerprint(current)}
    return {"status": "needs_review", "candidate": current, "attempts": attempts, "unresolved": [], "repair_unavailable": False, "final_fingerprint": fingerprint(current)}
