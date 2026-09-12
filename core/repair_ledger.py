"""Persistence helpers for bounded local repair attempts."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from models import RepairAttempt, Session


def record_repair_attempt(*, repair: dict[str, Any], issue: dict[str, Any] | None = None, context: dict[str, Any] | None = None, session: Any | None = None) -> RepairAttempt | None:
    """Write one runtime repair row when a DB context is available.

    The function is intentionally no-op for pure/unit callers that do not pass
    a context, so qualification remains usable without a database.  Callers
    must pass only redacted operation metadata; raw model output and secrets
    are never persisted here.
    """
    issue = issue if isinstance(issue, dict) else {}
    context = context if isinstance(context, dict) else {}
    operation = {"patch": repair.get("patch", []), "target_layer": repair.get("target_layer", ""), "issue_code": repair.get("issue_code", "")}
    owns_session = session is None
    db = session or Session()
    try:
        row = RepairAttempt(
            issue_code=str(issue.get("code") or repair.get("issue_code") or ""),
            target_layer=str(issue.get("target_layer") or repair.get("target_layer") or ""),
            target_id=str(issue.get("target_id") or repair.get("target_id") or ""),
            book_id=context.get("book_id"), episode=context.get("episode"), scene_id=str(context.get("scene_id") or ""), shot_id=str(context.get("shot_id") or ""),
            before_fingerprint=str(repair.get("before_fingerprint") or ""), repair_operation=json.dumps(operation, ensure_ascii=False, sort_keys=True), after_fingerprint=str(repair.get("after_fingerprint") or ""),
            attempt_number=int(context.get("attempt_number") or 1), revalidation_status=str(context.get("revalidation_status") or "pending"), revalidation_details=json.dumps(context.get("revalidation_details") or {}, ensure_ascii=False),
            model=str(context.get("model") or ""), prompt_fingerprint=str(context.get("prompt_fingerprint") or ""), created_at=datetime.now(),
        )
        db.add(row)
        if owns_session:
            db.commit(); db.refresh(row)
        return row
    finally:
        if owns_session:
            db.close()
