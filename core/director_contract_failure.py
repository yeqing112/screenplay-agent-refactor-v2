"""Versioned taxonomy for Director Creative contract failures.

The compiler keeps provider-specific error codes for debugging, while this
module supplies a stable category for metrics, repair routing, and replay.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


CONTRACT_FAILURE_SCHEMA_VERSION = "director_contract_failure_v1"
CONTRACT_FAILURE_CATEGORIES = (
    "PARSE_FAILURE",
    "ENVELOPE_SCHEMA_ERROR",
    "FORBIDDEN_PATCH_PATH",
    "FACT_OVERRIDE_ATTEMPT",
    "UNKNOWN_PLAN_SHOT_ID",
    "INVALID_PATCH_VALUE",
    "INVALID_CHARACTER_REFERENCE",
    "AUXILIARY_UNBOUND_BEAT",
    "AUXILIARY_BUDGET_EXCEEDED",
    "CONTRACT_FINGERPRINT_MISMATCH",
    "OTHER_KNOWN",
    "UNKNOWN_CONTRACT_FAILURE",
)

_CODE_TO_CATEGORY = {
    "UNKNOWN_PLAN_SHOT_ID": "UNKNOWN_PLAN_SHOT_ID",
    "DIRECTOR_FACT_OVERRIDE": "FACT_OVERRIDE_ATTEMPT",
    "FACT_OVERRIDE_ATTEMPT": "FACT_OVERRIDE_ATTEMPT",
    "DIRECTOR_PATCH_PATH_FORBIDDEN": "FORBIDDEN_PATCH_PATH",
    "FORBIDDEN_PATCH_PATH": "FORBIDDEN_PATCH_PATH",
    "INVALID_PATCH_VALUE": "INVALID_PATCH_VALUE",
    "INVALID_CHARACTER_REFERENCE": "INVALID_CHARACTER_REFERENCE",
    "AUXILIARY_UNBOUND_BEAT": "AUXILIARY_UNBOUND_BEAT",
    "AUXILIARY_BUDGET_EXCEEDED": "AUXILIARY_BUDGET_EXCEEDED",
    "CONTRACT_FINGERPRINT_MISMATCH": "CONTRACT_FINGERPRINT_MISMATCH",
    "DIRECTOR_PATCH_SCHEMA_INVALID": "ENVELOPE_SCHEMA_ERROR",
    "DIRECTOR_PATCH_RESULT_INVALID": "ENVELOPE_SCHEMA_ERROR",
    "DIRECTOR_AUXILIARY_SCHEMA_INVALID": "ENVELOPE_SCHEMA_ERROR",
    "DIRECTOR_PATCH_COMPILE_INVALID": "OTHER_KNOWN",
    "DIRECTOR_AUXILIARY_INVALID": "OTHER_KNOWN",
    "UNKNOWN_CONTRACT_FAILURE": "UNKNOWN_CONTRACT_FAILURE",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def classify_contract_failure(error: Any) -> str:
    """Map an exception or error record to a stable taxonomy category."""

    if isinstance(error, dict):
        code = _text(error.get("code") or error.get("issue_code"))
    else:
        code = _text(getattr(error, "code", ""))
    if code in _CODE_TO_CATEGORY:
        return _CODE_TO_CATEGORY[code]
    if code.startswith("PARSE_") or code.endswith("_PARSE_FAILURE"):
        return "PARSE_FAILURE"
    if code.startswith("DIRECTOR_PATCH_SCHEMA") or code.endswith("_SCHEMA_INVALID"):
        return "ENVELOPE_SCHEMA_ERROR"
    if code:
        return "OTHER_KNOWN"
    return "UNKNOWN_CONTRACT_FAILURE"


def build_contract_failure(error: Any, *, plan_shot_id: str = "", path: str = "", message: str = "") -> dict[str, Any]:
    code = _text(error.get("code") or error.get("issue_code")) if isinstance(error, dict) else _text(getattr(error, "code", ""))
    resolved_path = _text(path) or (_text(error.get("path")) if isinstance(error, dict) else _text(getattr(error, "path", "")))
    resolved_target = _text(plan_shot_id) or (_text(error.get("plan_shot_id") or error.get("target_id")) if isinstance(error, dict) else _text(getattr(error, "plan_shot_id", "")))
    resolved_message = _text(message) or (_text(error.get("message")) if isinstance(error, dict) else str(error))
    return {
        "schema_version": CONTRACT_FAILURE_SCHEMA_VERSION,
        "category": classify_contract_failure(error),
        "code": code or "UNKNOWN_CONTRACT_FAILURE",
        "plan_shot_id": resolved_target,
        "path": resolved_path,
        "message": resolved_message,
    }


def aggregate_contract_failures(failures: Iterable[Any]) -> dict[str, Any]:
    rows = [build_contract_failure(item) for item in failures]
    counts = Counter(item["category"] for item in rows)
    return {
        "schema_version": CONTRACT_FAILURE_SCHEMA_VERSION,
        "total": len(rows),
        "counts": {category: int(counts.get(category, 0)) for category in CONTRACT_FAILURE_CATEGORIES if counts.get(category)},
        "failures": rows,
    }


__all__ = ["CONTRACT_FAILURE_SCHEMA_VERSION", "CONTRACT_FAILURE_CATEGORIES", "classify_contract_failure", "build_contract_failure", "aggregate_contract_failures"]
