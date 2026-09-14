"""Explicit model input contract for Director Tail Repair."""
from __future__ import annotations
import copy, hashlib, json
from typing import Any

REPAIR_REQUEST_SCHEMA_VERSION = "director_tail_repair_request_v1"

def build_repair_request(*, root_cause: str, target_dimensions: list[str], relevant_opportunities: list[dict[str, Any]] = (), relevant_beats: list[Any] = (), relevant_shots: list[Any] = (), strategy_subset: dict[str, Any] | None = None, immutable_contract: dict[str, Any] | None = None, validator_findings: list[Any] = (), previous_intervention: Any = None, target_metric: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "schema_version": REPAIR_REQUEST_SCHEMA_VERSION,
        "root_cause": str(root_cause or "").strip(),
        "target_dimensions": [str(x).strip() for x in target_dimensions if str(x).strip()],
        "relevant_opportunities": copy.deepcopy(list(relevant_opportunities)),
        "relevant_beats": copy.deepcopy(list(relevant_beats)),
        "relevant_shots": copy.deepcopy(list(relevant_shots)),
        "strategy_subset": copy.deepcopy(strategy_subset or {}),
        "immutable_contract": copy.deepcopy(immutable_contract or {}),
        "validator_findings": copy.deepcopy(list(validator_findings)),
        "previous_intervention": copy.deepcopy(previous_intervention),
        "target_metric": copy.deepcopy(target_metric or {}),
        "output_contract": {"schema_version": "director_tail_repair_ir_v1", "no_canonical_paths": True},
    }
    payload["request_fingerprint"] = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()
    return payload

__all__ = ["REPAIR_REQUEST_SCHEMA_VERSION", "build_repair_request"]
