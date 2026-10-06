"""Append-only Director LLM forensic attempt ledger helpers."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class DirectorAttemptContext:
    """One frozen next-attempt identity shared by execution and append."""

    history_count: int
    ordinal: int
    attempt_id: str
    status_prefix: str
    authoring_stage: str = "BEAT_PLAN"

    def status(self, outcome: str) -> str:
        return f"{self.status_prefix}_{str(outcome or '').strip().upper()}"


def resolve_next_director_attempt_context(info: Mapping[str, Any] | None, *, authoring_stage: str = "BEAT_PLAN") -> DirectorAttemptContext:
    history = info.get("director_llm_attempts") if isinstance(info, Mapping) else None
    history = history if isinstance(history, list) else []
    ordinal = len(history) + 1
    stage = str(authoring_stage or "BEAT_PLAN").strip().upper()
    prefix = "DIRECTOR_CREATIVE_ENRICHMENT" if stage in {"CREATIVE_ENRICHMENT", "STAGE_B", "DIRECTOR_CREATIVE_ENRICHMENT"} else "DIRECTOR_BEAT_PLAN"
    canonical_stage = "CREATIVE_ENRICHMENT" if prefix == "DIRECTOR_CREATIVE_ENRICHMENT" else "BEAT_PLAN"
    return DirectorAttemptContext(
        history_count=len(history), ordinal=ordinal,
        attempt_id=f"attempt-{ordinal}",
        status_prefix=f"{prefix}_ATTEMPT{ordinal}",
        authoring_stage=canonical_stage,
    )


def append_director_attempt(
    info: Mapping[str, Any] | None,
    *,
    request_fingerprint: str,
    raw_response_sha256: str,
    authorization_id: str,
    status: str = "RAW_PERSISTED",
    authoring_stage: str | None = None,
    prompt_fingerprint: str | None = None,
    provider_request_fingerprint_v2: str | None = None,
    attempt_context: DirectorAttemptContext | None = None,
) -> dict[str, Any]:
    """Return updated model info without dropping prior attempts."""
    result = copy.deepcopy(dict(info or {}))
    history = result.get("director_llm_attempts")
    history = copy.deepcopy(history) if isinstance(history, list) else []
    expected = resolve_next_director_attempt_context(result, authoring_stage=authoring_stage or (attempt_context.authoring_stage if attempt_context else "BEAT_PLAN"))
    if attempt_context is not None:
        if attempt_context.history_count != len(history) or attempt_context.attempt_id != expected.attempt_id:
            raise ValueError(f"{expected.status_prefix}_LINEAGE_CONFLICT" if expected.authoring_stage != "BEAT_PLAN" else "DIRECTOR_BEAT_PLAN_ATTEMPT_LINEAGE_CONFLICT")
        attempt_id = attempt_context.attempt_id
    else:
        attempt_id = expected.attempt_id
    attempt = {
        "attempt_id": attempt_id,
        "authorization_id": str(authorization_id or ""),
        "request_fingerprint": str(request_fingerprint or ""),
        "raw_response_sha256": str(raw_response_sha256 or ""),
        "status": str(status or "RAW_PERSISTED"),
    }
    if authoring_stage:
        attempt["authoring_stage"] = str(authoring_stage)
    if prompt_fingerprint:
        attempt["prompt_fingerprint"] = str(prompt_fingerprint)
    if provider_request_fingerprint_v2:
        attempt["provider_request_fingerprint_v2"] = str(provider_request_fingerprint_v2)
    history.append(attempt)
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


__all__ = ["DirectorAttemptContext", "resolve_next_director_attempt_context", "append_director_attempt", "hydrate_director_attempt_history"]
