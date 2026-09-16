"""Scope-bound runtime authorization for the Director V3 Phase A runner.

Authorization is deliberately loaded from a caller-supplied file outside the
tracked repository.  This prevents writing an authorization token from
changing the immutable execution-base commit while still making the exact
scope auditable in the run manifest.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "director_v3_phase_a_runtime_authorization_v1"
SCOPE = "DIRECTOR_V3_AUTHORIZED_EVALUATION_UPSTREAM_PHASE_A"
SOURCE_PACKAGE_ID = "SRC79f12d1b7f5eb828"
SOURCE_VERSION_ID = "SRC79f12d1b7f5eb828:V01:d001bab5cc82"
ALLOWED_STAGES = ("FACT_EXTRACTION", "SCRIPT_IR")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def authorization_fingerprint(authorization: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(authorization)).hexdigest()


def load_runtime_authorization(path: str | Path) -> dict[str, Any]:
    """Load and validate an external authorization contract, fail closed."""
    auth_path = Path(path)
    try:
        payload = json.loads(auth_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"authorization_unreadable:{exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("authorization_must_be_object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("authorization_schema_mismatch")
    if payload.get("scope") != SCOPE:
        raise ValueError("authorization_scope_mismatch")
    if payload.get("source_package_id") != SOURCE_PACKAGE_ID:
        raise ValueError("authorization_source_package_mismatch")
    if payload.get("source_version_id") != SOURCE_VERSION_ID:
        raise ValueError("authorization_source_version_mismatch")
    execution_base = str(payload.get("authorized_execution_base") or "").strip()
    if len(execution_base) != 40 or any(ch not in "0123456789abcdefABCDEF" for ch in execution_base):
        raise ValueError("authorization_execution_base_invalid")
    stages = payload.get("allowed_stages")
    if stages != list(ALLOWED_STAGES):
        raise ValueError("authorization_allowed_stages_mismatch")
    try:
        max_calls = int(payload.get("max_provider_calls"))
        retries = int(payload.get("retries"))
    except (TypeError, ValueError) as exc:
        raise ValueError("authorization_call_budget_invalid") from exc
    if max_calls != 2:
        raise ValueError("authorization_call_budget_must_be_two")
    if retries != 0:
        raise ValueError("authorization_retries_must_be_zero")
    if payload.get("issued_from_external_authorization") is not True:
        raise ValueError("authorization_external_issuer_required")
    authorization_id = str(payload.get("authorization_id") or "").strip()
    if not authorization_id:
        raise ValueError("authorization_id_required")
    return {
        "schema_version": SCHEMA_VERSION,
        "authorization_id": authorization_id,
        "scope": SCOPE,
        "source_package_id": SOURCE_PACKAGE_ID,
        "source_version_id": SOURCE_VERSION_ID,
        "authorized_execution_base": execution_base.lower(),
        "allowed_stages": list(ALLOWED_STAGES),
        "max_provider_calls": 2,
        "retries": 0,
        "issued_from_external_authorization": True,
        "authorization_hash": authorization_fingerprint(payload),
        "authorization_path": str(auth_path),
    }


def authorization_gate(
    authorization: dict[str, Any] | None,
    *,
    head: str,
    remote_head: str,
    dirty: list[str],
    source_package_id: str,
    source_version_id: str,
    predicted_calls: int,
) -> tuple[bool, list[str]]:
    """Evaluate runtime authorization without any provider side effects."""
    reasons: list[str] = []
    if not authorization:
        reasons.append("RUNTIME_AUTHORIZATION_MISSING")
        return False, reasons
    if authorization.get("authorized_execution_base") != head or head != remote_head:
        reasons.append("RUNTIME_AUTHORIZATION_EXECUTION_BASE_MISMATCH")
    if dirty:
        reasons.append("WORKTREE_NOT_CLEAN_FOR_REAL_PROVIDER_RUN")
    if authorization.get("source_package_id") != source_package_id:
        reasons.append("RUNTIME_AUTHORIZATION_SOURCE_PACKAGE_MISMATCH")
    if authorization.get("source_version_id") != source_version_id:
        reasons.append("RUNTIME_AUTHORIZATION_SOURCE_VERSION_MISMATCH")
    if predicted_calls > int(authorization.get("max_provider_calls") or 0):
        reasons.append("RUNTIME_AUTHORIZATION_CALL_BUDGET_EXCEEDED")
    if authorization.get("retries") != 0:
        reasons.append("RUNTIME_AUTHORIZATION_RETRIES_NOT_ZERO")
    return not reasons, reasons


__all__ = [
    "SCHEMA_VERSION",
    "SCOPE",
    "SOURCE_PACKAGE_ID",
    "SOURCE_VERSION_ID",
    "ALLOWED_STAGES",
    "authorization_fingerprint",
    "load_runtime_authorization",
    "authorization_gate",
]
