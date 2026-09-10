"""Utilities for cache-friendly, auditable LLM prompt construction.

MiMo's cache is provider-side prefix reuse.  These helpers deliberately do
not invent provider-specific request fields; they make the byte/token prefix
stable and provide fingerprints for local de-duplication and telemetry.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    """Serialize JSON deterministically for prompt content and fingerprints."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def prompt_fingerprint(*parts: Any) -> str:
    """Return a non-secret fingerprint for a complete prompt request."""

    encoded_parts = []
    for part in parts:
        if isinstance(part, (dict, list, tuple)):
            encoded_parts.append(canonical_json(part))
        else:
            encoded_parts.append(str(part or ""))
    return hashlib.sha256("\n--prompt-part--\n".join(encoded_parts).encode("utf-8")).hexdigest()


def model_request_snapshot(profile: dict[str, Any] | None) -> dict[str, Any]:
    """Return the non-secret model/parameter portion of a request identity.

    Provider credentials and URLs are deliberately excluded.  Parameters are
    canonicalized so changing temperature, thinking, response format or token
    budget creates a new idempotency branch instead of reusing an incompatible
    candidate.
    """

    profile = profile if isinstance(profile, dict) else {}
    raw_params = profile.get("default_params")
    params = raw_params if isinstance(raw_params, dict) else {}
    allowed = {"temperature", "max_tokens", "thinking", "response_format", "top_p", "seed"}
    safe_params = {key: params[key] for key in sorted(allowed) if key in params}
    return {
        "profile_id": str(profile.get("id") or ""),
        "provider": str(profile.get("provider") or ""),
        "model_name": str(profile.get("model_name") or ""),
        "parameters": safe_params,
    }


def llm_request_fingerprint(*, system: Any, user: Any, profile: dict[str, Any] | None = None, extra: Any = None) -> str:
    """Fingerprint prompt bytes plus safe model parameters for deduplication."""

    return prompt_fingerprint(
        model_request_snapshot(profile),
        system,
        user,
        extra if extra is not None else {},
    )


def summarize_audit_records(records: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Aggregate bounded ``core.llm`` audit records for durable storage."""

    items = [item for item in (records or []) if isinstance(item, dict)]
    if not items:
        return {"attempt_count": 0, "last": {}}
    last = items[-1]
    usage_items = [item.get("usage") for item in items if isinstance(item.get("usage"), dict)]
    def total(key: str) -> int:
        return sum(int(item.get(key) or 0) for item in usage_items)
    prompt_tokens = total("prompt_tokens")
    cached_tokens = total("cached_tokens")
    return {
        "attempt_count": len(items),
        "vendor_models": sorted({str(item.get("vendor_model") or "") for item in items if item.get("vendor_model")}),
        "vendor_hosts": sorted({str(item.get("vendor_host") or "") for item in items if item.get("vendor_host")}),
        "prompt_tokens": prompt_tokens,
        "cached_tokens": cached_tokens,
        "completion_tokens": total("completion_tokens"),
        "total_tokens": total("total_tokens"),
        "cache_hit_rate": round(cached_tokens / prompt_tokens, 6) if prompt_tokens else None,
        "last_request_fingerprint": str(last.get("request_fingerprint") or ""),
        "last_latency_ms": float(last.get("latency_ms") or 0),
        "last_http_status": int(last.get("http_status") or 0),
        "last_parse_ok": bool(last.get("parse_ok")),
    }


def cache_metrics(usage: dict[str, Any] | None) -> dict[str, int | float | None]:
    """Normalize MiMo/OpenAI usage details without assuming cache support."""

    usage = usage if isinstance(usage, dict) else {}
    details = usage.get("prompt_tokens_details")
    details = details if isinstance(details, dict) else {}
    prompt_tokens = _as_int(usage.get("prompt_tokens"))
    cached_tokens = _as_int(details.get("cached_tokens"))
    completion_tokens = _as_int(usage.get("completion_tokens"))
    total_tokens = _as_int(usage.get("total_tokens"))
    hit_rate = None
    if prompt_tokens and cached_tokens is not None:
        hit_rate = round(max(0, cached_tokens) / prompt_tokens, 6)
    return {
        "prompt_tokens": prompt_tokens,
        "cached_tokens": cached_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cache_hit_rate": hit_rate,
    }


def _as_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
