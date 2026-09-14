"""Explicit model input contract for Director Tail Repair."""
from __future__ import annotations
import copy, hashlib, json
from typing import Any

from core.director_tail_repair_provider_contract import build_provider_output_contract
from core.director_tail_repair_semantic_spec import SEMANTIC_SPEC_VERSION

REPAIR_REQUEST_SCHEMA_VERSION = "director_tail_repair_request_v1"

def _fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def build_repair_request(*, root_cause: str, target_dimensions: list[str], relevant_opportunities: list[dict[str, Any]] = (), relevant_beats: list[Any] = (), relevant_shots: list[Any] = (), allowed_plan_shot_ids: list[str] = (), allowed_character_ids: list[str] = (), strategy_subset: dict[str, Any] | None = None, immutable_contract: dict[str, Any] | None = None, validator_findings: list[Any] = (), previous_intervention: Any = None, target_metric: dict[str, Any] | None = None, attempt: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "schema_version": REPAIR_REQUEST_SCHEMA_VERSION,
        "root_cause": str(root_cause or "").strip(),
        "target_dimensions": [str(x).strip() for x in target_dimensions if str(x).strip()],
        "relevant_opportunities": copy.deepcopy(list(relevant_opportunities)),
        "relevant_beats": copy.deepcopy(list(relevant_beats)),
        "relevant_shots": copy.deepcopy(list(relevant_shots)),
        "allowed_plan_shot_ids": [str(value).strip() for value in allowed_plan_shot_ids if str(value).strip()],
        "allowed_character_ids": sorted({str(value).strip() for value in allowed_character_ids if str(value).strip()}),
        "semantic_spec_version": SEMANTIC_SPEC_VERSION,
        "strategy_subset": copy.deepcopy(strategy_subset or {}),
        "immutable_contract": copy.deepcopy(immutable_contract or {}),
        "validator_findings": copy.deepcopy(list(validator_findings)),
        "previous_intervention": copy.deepcopy(previous_intervention),
        "target_metric": copy.deepcopy(target_metric or {}),
        "output_contract": build_provider_output_contract(),
        "attempt": copy.deepcopy(attempt or {}),
    }
    payload["base_request_fingerprint"] = _fingerprint(payload)
    payload["request_fingerprint"] = payload["base_request_fingerprint"]
    return payload


def with_attempt(request: dict[str, Any], attempt: dict[str, Any]) -> dict[str, Any]:
    """Attach an attempt context and recompute the authoritative fingerprint."""

    payload = copy.deepcopy(request if isinstance(request, dict) else {})
    payload.pop("request_fingerprint", None)
    payload["attempt"] = copy.deepcopy(attempt or {})
    # Deprecated read-only projection retained for internal/provider-free
    # callers that still inspect the V2.4 request shape. The provider adapter
    # removes these fields through ``to_provider_request``.
    if isinstance(attempt, dict) and attempt.get("kind"):
        payload["attempt_kind"] = str(attempt["kind"])
    for key in ("previous_raw_output", "previous_validation_errors"):
        if isinstance(attempt, dict) and key in attempt:
            payload[key] = copy.deepcopy(attempt[key])
    payload["attempt_request_fingerprint"] = _fingerprint(payload)
    payload["request_fingerprint"] = payload["attempt_request_fingerprint"]
    return payload


_PROVIDER_FIELDS = frozenset({
    "schema_version", "root_cause", "target_dimensions", "relevant_opportunities",
    "relevant_beats", "relevant_shots", "allowed_plan_shot_ids", "strategy_subset",
    "allowed_character_ids", "semantic_spec_version",
    "immutable_contract", "validator_findings", "previous_intervention", "target_metric",
    "output_contract", "attempt", "base_request_fingerprint", "attempt_request_fingerprint",
    "request_fingerprint",
})


def to_provider_request(request: dict[str, Any]) -> dict[str, Any]:
    """Serialize only authoritative fields for the external provider boundary."""

    source = request if isinstance(request, dict) else {}
    payload = {key: copy.deepcopy(source[key]) for key in sorted(_PROVIDER_FIELDS) if key in source}
    payload.pop("request_fingerprint", None)
    payload["provider_request_fingerprint"] = _fingerprint(payload)
    return payload


__all__ = ["REPAIR_REQUEST_SCHEMA_VERSION", "build_repair_request", "with_attempt", "to_provider_request"]
