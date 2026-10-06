"""Append-only Director LLM forensic attempt ledger helpers."""
from __future__ import annotations

import copy
from typing import Any, Mapping


def append_director_attempt(
    info: Mapping[str, Any] | None,
    *,
    request_fingerprint: str,
    raw_response_sha256: str,
    authorization_id: str,
    status: str = "RAW_PERSISTED",
) -> dict[str, Any]:
    """Return updated model info without dropping prior attempts."""
    result = copy.deepcopy(dict(info or {}))
    history = result.get("director_llm_attempts")
    history = copy.deepcopy(history) if isinstance(history, list) else []
    attempt_id = f"attempt-{len(history) + 1}"
    history.append({
        "attempt_id": attempt_id,
        "authorization_id": str(authorization_id or ""),
        "request_fingerprint": str(request_fingerprint or ""),
        "raw_response_sha256": str(raw_response_sha256 or ""),
        "status": str(status or "RAW_PERSISTED"),
    })
    result["director_llm_attempts"] = history
    return result


def hydrate_director_attempt_history(
    info: Mapping[str, Any] | None,
    canonical_attempts: list[Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Idempotently merge immutable historical attempts by ``attempt_id``."""
    result = copy.deepcopy(dict(info or {}))
    existing = result.get("director_llm_attempts")
    history = copy.deepcopy(existing) if isinstance(existing, list) else []
    by_id = {str(item.get("attempt_id")): item for item in history if isinstance(item, Mapping) and str(item.get("attempt_id") or "")}
    duplicates = 0
    for item in canonical_attempts:
        attempt_id = str(item.get("attempt_id") or "")
        if not attempt_id:
            continue
        if attempt_id in by_id:
            if by_id[attempt_id] == dict(item):
                duplicates += 1
            continue
        by_id[attempt_id] = copy.deepcopy(dict(item))
        history.append(copy.deepcopy(dict(item)))
    changed = history != (existing if isinstance(existing, list) else [])
    result["director_llm_attempts"] = history
    return result, {"changed": changed, "writes": 1 if changed else 0, "duplicates": duplicates, "history_row_count": len(history)}


__all__ = ["append_director_attempt", "hydrate_director_attempt_history"]
