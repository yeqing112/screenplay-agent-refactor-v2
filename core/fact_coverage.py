"""Provider-free Fact Coverage foundation.

Coverage is intentionally separate from FactSnapshot identity and semantic
grounding.  This module supplies deterministic component IDs, coarse source
narrative units, requirement/matrix contracts, and a conservative authority
compiler.  It never creates or edits facts and never calls a provider.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Iterable

REQUIREMENT_TYPES = (
    "CHARACTER_IDENTITY", "CHARACTER_RELATION", "LOCATION_IDENTITY", "LOCATION_CHANGE",
    "EVENT_OCCURRENCE", "EVENT_ORDER", "TEMPORAL_ANCHOR", "CAUSAL_RELATION",
    "OBJECT_STATE", "OBJECT_OWNERSHIP", "REVEAL", "CONFLICT_STATE", "CLAIM_OR_BELIEF", "OUTCOME",
)
COVERAGE_STATUSES = ("COVERED", "PARTIALLY_COVERED", "MISSING", "CLAIM_ONLY", "UNSAFE_INFERENCE", "AMBIGUOUS")
DISPOSITION_TO_COVERAGE = {
    "WORLD_FACT_CONFIRMED": "COVERED",
    "CLAIM_SUPPORTED": "CLAIM_ONLY",
    "INFERENCE_PROPOSED": "UNSAFE_INFERENCE",
    "PARTIAL_SUPPORT_REVIEW": "PARTIALLY_COVERED",
    "CONTRADICTED_REJECTED": "AMBIGUOUS",
    "AMBIGUOUS_REVIEW": "AMBIGUOUS",
}
CLAIM_COMPATIBLE_REQUIREMENTS = {"CLAIM_OR_BELIEF"}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def canonical_fact_components(facts: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Create deterministic structural component identities, not semantics."""
    rows: list[dict[str, Any]] = []
    for fact in facts:
        fact_id = str(fact.get("fact_id") or "")
        predicate = str(fact.get("predicate") or "")
        value = copy.deepcopy(fact.get("value"))
        composite_unknown = isinstance(value, (dict, list, tuple)) or any(token in f"{predicate} {value}".lower() for token in (" and ", " or ", "以及", "并且", "同时"))
        rows.append({
            "fact_id": fact_id,
            "components": [
                {"component_id": f"{fact_id}::SUBJECT", "component_type": "SUBJECT", "value": copy.deepcopy(fact.get("subject_id")), "semantic_atomicity": "UNKNOWN" if composite_unknown else "NOT_ASSESSED"},
                {"component_id": f"{fact_id}::PREDICATE", "component_type": "PREDICATE", "value": predicate, "semantic_atomicity": "UNKNOWN" if composite_unknown else "NOT_ASSESSED"},
                {"component_id": f"{fact_id}::VALUE", "component_type": "VALUE", "value": value, "semantic_atomicity": "UNKNOWN" if composite_unknown else "NOT_ASSESSED"},
            ],
            "component_semantic_atomicity": "UNKNOWN_REVIEW_REQUIRED" if composite_unknown else "NOT_CLAIMED",
            "runtime_authority": False,
        })
    return {"schema_version": "canonical_fact_assertion_components_v1", "provider_calls": 0, "facts": rows, "fingerprint": fingerprint(rows)}


def build_narrative_unit_index(*, anchors: list[dict[str, Any]], window_size: int = 1200) -> dict[str, Any]:
    """Group ordered evidence anchors into coarse, deterministic source windows."""
    clean = [row for row in anchors if isinstance(row, dict) and isinstance(row.get("char_start"), int) and isinstance(row.get("char_end"), int)]
    clean.sort(key=lambda row: (int(row["char_start"]), int(row["char_end"]), str(row.get("anchor_ref") or "")))
    groups: dict[int, list[dict[str, Any]]] = {}
    for row in clean:
        bucket = int(row["char_start"]) // max(1, int(window_size))
        groups.setdefault(bucket, []).append(row)
    units: list[dict[str, Any]] = []
    for order, bucket in enumerate(sorted(groups), 1):
        rows = groups[bucket]
        exact = "".join(str(row.get("exact_text") or "") for row in rows)
        units.append({
            "unit_id": f"NU_{order:04d}",
            "anchor_refs": [str(row.get("anchor_ref") or "") for row in rows],
            "char_start": min(int(row["char_start"]) for row in rows),
            "char_end": max(int(row["char_end"]) for row in rows),
            "exact_text_hash": fingerprint(exact),
            "source_order": order,
        })
    return {"schema_version": "source_narrative_unit_index_v1", "provider_calls": 0, "window_size": int(window_size), "unit_count": len(units), "units": units, "fingerprint": fingerprint(units), "semantic_interpretation": False}


def requirement_contract() -> dict[str, Any]:
    return {"schema_version": "fact_coverage_requirement_v1", "provider_calls": 0, "requirement_types": list(REQUIREMENT_TYPES), "program_owned": ["requirement_id", "schema", "source_unit_refs", "category", "ordering", "validation"], "semantic_proposal_owned": ["meaning_of_structuring_necessity"], "canonical_id_pattern": "REQ_[0-9]{4}", "no_count_threshold": True}


def coverage_matrix_contract() -> dict[str, Any]:
    return {"schema_version": "fact_coverage_matrix_v1", "provider_calls": 0, "required_fields": ["requirement_id", "requirement_type", "source_unit_refs", "supporting_fact_ids", "semantic_fact_dispositions", "coverage_status", "review_required"], "coverage_statuses": list(COVERAGE_STATUSES), "fact_count_is_not_qualification": True, "anchor_percentage_is_not_qualification": True}


def coverage_provider_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["requirements", "coverage_claims"],
        "additionalProperties": False,
        "properties": {
            "requirements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["requirement_type", "description", "source_unit_refs"],
                    "additionalProperties": False,
                    "properties": {
                        "requirement_type": {"enum": list(REQUIREMENT_TYPES)},
                        "description": {"type": "string"},
                        "source_unit_refs": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "coverage_claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["requirement_ref", "fact_refs", "coverage_verdict"],
                    "additionalProperties": False,
                    "properties": {
                        "requirement_ref": {"type": "string", "pattern": "^REQ_[0-9]{4}$"},
                        "fact_refs": {"type": "array", "items": {"type": "string", "pattern": "^FACT_[0-9]{4}$"}},
                        "coverage_verdict": {"enum": list(COVERAGE_STATUSES)},
                    },
                },
            },
        },
    }


def coverage_schema_fingerprint() -> str:
    return fingerprint({"contract": requirement_contract(), "matrix": coverage_matrix_contract(), "provider_schema": coverage_provider_schema()})


def compile_fact_coverage(*, requirements: list[dict[str, Any]], semantic_overlay: dict[str, Any], source_unit_index: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compile conservative coverage statuses from program-owned requirements."""
    fact_rows = {str(row.get("fact_id")): row for row in semantic_overlay.get("facts", []) if isinstance(row, dict)}
    matrix: list[dict[str, Any]] = []
    for index, requirement in enumerate(requirements, 1):
        req_id = str(requirement.get("requirement_id") or f"REQ_{index:04d}")
        req_type = str(requirement.get("requirement_type") or "")
        refs = [str(ref) for ref in requirement.get("source_unit_refs") or []]
        support_ids = [str(ref) for ref in requirement.get("supporting_fact_ids") or [] if str(ref) in fact_rows]
        dispositions = [str(fact_rows[fact_id].get("semantic_disposition") or "") for fact_id in support_ids]
        statuses = [DISPOSITION_TO_COVERAGE.get(item, "AMBIGUOUS") for item in dispositions]
        if not statuses:
            status = "MISSING"
        elif "COVERED" in statuses and (req_type not in CLAIM_COMPATIBLE_REQUIREMENTS or any(disposition == "WORLD_FACT_CONFIRMED" for disposition in dispositions)):
            status = "COVERED"
        elif req_type in CLAIM_COMPATIBLE_REQUIREMENTS and "CLAIM_ONLY" in statuses:
            status = "COVERED"
        elif "PARTIALLY_COVERED" in statuses:
            status = "PARTIALLY_COVERED"
        elif "CLAIM_ONLY" in statuses:
            status = "CLAIM_ONLY"
        elif "UNSAFE_INFERENCE" in statuses:
            status = "UNSAFE_INFERENCE"
        else:
            status = "AMBIGUOUS"
        matrix.append({"requirement_id": req_id, "requirement_type": req_type, "source_unit_refs": refs, "supporting_fact_ids": support_ids, "semantic_fact_dispositions": dispositions, "coverage_status": status, "review_required": status != "COVERED", "runtime_authority": False})
    counts = {status: sum(1 for row in matrix if row["coverage_status"] == status) for status in COVERAGE_STATUSES}
    return {"schema_version": "fact_coverage_matrix_v1", "provider_calls": 0, "source_unit_index_fingerprint": (source_unit_index or {}).get("fingerprint"), "rows": matrix, "counts": counts, "qualification_status": "NOT_ADJUDICATED", "runtime_authority": False, "fact_count_diagnostic": len(fact_rows), "anchor_percentage_shortcut": False}


def validate_coverage_payload(payload: Any) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    if not isinstance(payload, dict) or not isinstance(payload.get("requirements"), list) or not isinstance(payload.get("coverage_claims"), list):
        return {"status": "FAIL", "errors": [{"code": "COVERAGE_OUTPUT_SCHEMA_INVALID"}]}
    for key in ("requirements", "coverage_claims"):
        for index, row in enumerate(payload[key], 1):
            if not isinstance(row, dict):
                errors.append({"code": "COVERAGE_ROW_INVALID", "field": key, "index": index}); continue
            allowed = set(coverage_provider_schema()["properties"][key]["items"]["properties"])
            extra = sorted(set(row) - allowed)
            if extra:
                errors.append({"code": "COVERAGE_UNEXPECTED_FIELD", "field": key, "index": index, "fields": extra})
            if key == "requirements":
                if row.get("requirement_type") not in REQUIREMENT_TYPES:
                    errors.append({"code": "COVERAGE_REQUIREMENT_TYPE_INVALID", "index": index})
                if not isinstance(row.get("description"), str) or not isinstance(row.get("source_unit_refs"), list) or not all(isinstance(item, str) for item in row.get("source_unit_refs", [])):
                    errors.append({"code": "COVERAGE_REQUIREMENT_FIELDS_INVALID", "index": index})
            else:
                ref = str(row.get("requirement_ref") or "")
                if len(ref) != 8 or not ref.startswith("REQ_") or not ref[4:].isdigit():
                    errors.append({"code": "COVERAGE_REQUIREMENT_REF_INVALID", "index": index})
                if not isinstance(row.get("fact_refs"), list) or not all(isinstance(item, str) and len(item) == 9 and item.startswith("FACT_") and item[5:].isdigit() for item in row.get("fact_refs", [])):
                    errors.append({"code": "COVERAGE_FACT_REFS_INVALID", "index": index})
                if row.get("coverage_verdict") not in COVERAGE_STATUSES:
                    errors.append({"code": "COVERAGE_VERDICT_INVALID", "index": index})
    return {"status": "PASS" if not errors else "FAIL", "errors": errors}


__all__ = ["REQUIREMENT_TYPES", "COVERAGE_STATUSES", "canonical_fact_components", "build_narrative_unit_index", "requirement_contract", "coverage_matrix_contract", "coverage_provider_schema", "coverage_schema_fingerprint", "compile_fact_coverage", "validate_coverage_payload", "fingerprint"]
