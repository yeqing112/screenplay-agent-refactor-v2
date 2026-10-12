"""Typed SourceClaim materialization boundary.

This module intentionally refuses to recover semantics from source prose.  It
can materialize deterministic claims only when upstream structured metadata is
present on each source unit.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from .director_claim_ir import make_claim


SOURCE_CLAIM_MATERIALIZATION_VERSION = "director_source_claim_materialization_contract_v1"
STRUCTURED_SOURCE_FIELDS = ("actor", "action", "object", "participants", "fact_bindings", "entity_refs")


def source_structured_capability(units: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    aggregate = {field: False for field in STRUCTURED_SOURCE_FIELDS}
    for unit in units:
        if not isinstance(unit, Mapping):
            continue
        present = {field: field in unit and unit.get(field) not in (None, "", [], {}) for field in STRUCTURED_SOURCE_FIELDS}
        for field, value in present.items():
            aggregate[field] = aggregate[field] or value
        rows.append({"unit_id": str(unit.get("unit_id") or ""), "present": present, "source_type": str(unit.get("source_type") or ""), "has_dialogue_speaker": bool(unit.get("speaker")), "has_text": bool(str(unit.get("text") or "").strip())})
    missing = [field for field, present in aggregate.items() if not present]
    status = "READY" if not missing and rows else "SOURCE_CLAIM_MATERIALIZATION_BOUNDARY_REQUIRED"
    return {"schema_version": SOURCE_CLAIM_MATERIALIZATION_VERSION, "status": status, "unit_count": len(rows), "structured_fields": aggregate, "missing_structured_fields": missing, "unit_capabilities": rows, "text_role": ["human_readable_evidence", "provenance"]}


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_") or "unit"


def materialize_source_claims(units: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    units_list = [unit for unit in units if isinstance(unit, Mapping)]
    capability = source_structured_capability(units_list)
    if capability["status"] != "READY":
        return {"schema_version": SOURCE_CLAIM_MATERIALIZATION_VERSION, "status": capability["status"], "claims": [], "capability": capability}
    claims: list[dict[str, Any]] = []
    for unit in units_list:
        unit_id = str(unit.get("unit_id") or "")
        structured = unit.get("fact_bindings") or unit.get("claims") or []
        if not isinstance(structured, list):
            continue
        for index, item in enumerate(structured):
            if not isinstance(item, Mapping):
                continue
            claim_type = str(item.get("claim_type") or "")
            predicate = str(item.get("predicate") or "")
            if not claim_type or not predicate:
                continue
            relation = _safe_id(predicate)
            claim = make_claim(
                claim_id=f"SC_{_safe_id(unit_id)}_{relation}_{index:02d}",
                source_path=f"source_units[{unit_id}].fact_bindings[{index}]",
                raw_text=str(unit.get("text") or ""),
                claim_type=claim_type,
                subject=item.get("subject") if isinstance(item.get("subject"), Mapping) else {},
                predicate=predicate,
                object_=item.get("object") if isinstance(item.get("object"), Mapping) else {},
                qualifiers=item.get("qualifiers") if isinstance(item.get("qualifiers"), Mapping) else {},
                polarity=str(item.get("polarity") or "POSITIVE"),
                modality=str(item.get("modality") or "ASSERTED"),
                canonicality="CANONICAL_ASSERTION",
                authority_required="SOURCE",
                source_refs=[unit_id],
                origin="SOURCE",
                support_status="SUPPORTED_EXPLICIT",
            )
            claims.append(claim)
    return {"schema_version": SOURCE_CLAIM_MATERIALIZATION_VERSION, "status": "PASS", "claims": claims, "capability": capability}


__all__ = ["SOURCE_CLAIM_MATERIALIZATION_VERSION", "STRUCTURED_SOURCE_FIELDS", "source_structured_capability", "materialize_source_claims"]
