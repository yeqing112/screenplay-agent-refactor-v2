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
from dataclasses import dataclass
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
TARGETED_SCHEMA_VERSION = "fact_coverage_targeted_v1"
MISSING_REASONS = ("ABSENT", "INSUFFICIENT_EVIDENCE", "AMBIGUOUS", "CONFLICTED", "INVALID")
AUTHORITATIVE_AUTHORITIES = {"source_text", "locked_fact", "approved_fact"}


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


def validate_narrative_unit_completeness(
    *,
    narrative_unit_index: dict[str, Any],
    source_evidence_index: dict[str, Any],
    raw_bytes: bytes | None = None,
    expected_anchor_count: int | None = None,
) -> dict[str, Any]:
    """Fail-closed completeness gate for a full-source narrative index.

    This validates membership and ordering only.  Narrative units remain coarse
    deterministic windows; this function never infers scenes or semantics.
    """
    errors: list[dict[str, Any]] = []
    source_anchors = source_evidence_index.get("anchors") if isinstance(source_evidence_index, dict) else None
    units = narrative_unit_index.get("units") if isinstance(narrative_unit_index, dict) else None
    if not isinstance(source_anchors, list):
        return {"status": "FAIL", "errors": [{"code": "SOURCE_EVIDENCE_ANCHORS_INVALID"}]}
    if not isinstance(units, list):
        return {"status": "FAIL", "errors": [{"code": "NARRATIVE_UNITS_INVALID"}]}

    expected_count = int(expected_anchor_count or source_evidence_index.get("anchor_count") or len(source_anchors))
    source_refs = [str(row.get("anchor_ref") or "") for row in source_anchors if isinstance(row, dict)]
    expected_refs = [f"E{i:04d}" for i in range(1, expected_count + 1)]
    source_ref_set = set(source_refs)
    source_duplicates = sorted({ref for ref in source_refs if source_refs.count(ref) > 1})
    if source_duplicates:
        errors.append({"code": "SOURCE_ANCHOR_DUPLICATE", "refs": source_duplicates})
    if len(source_anchors) != expected_count:
        errors.append({"code": "INPUT_ANCHOR_COUNT_MISMATCH", "expected": expected_count, "actual": len(source_anchors)})
    if source_refs != expected_refs:
        errors.append({"code": "SOURCE_ANCHOR_SEQUENCE_INVALID", "expected_first": expected_refs[0] if expected_refs else None, "expected_last": expected_refs[-1] if expected_refs else None})

    indexed_refs: list[str] = []
    unit_ids: list[str] = []
    unit_source_orders: list[int] = []
    unit_char_ranges: list[tuple[int, int]] = []
    for unit in units:
        if not isinstance(unit, dict):
            errors.append({"code": "NARRATIVE_UNIT_INVALID"})
            continue
        unit_id = str(unit.get("unit_id") or "")
        unit_ids.append(unit_id)
        refs = unit.get("anchor_refs")
        if not isinstance(refs, list) or not all(isinstance(ref, str) for ref in refs):
            errors.append({"code": "UNIT_ANCHOR_REFS_INVALID", "unit_id": unit_id})
            refs = []
        indexed_refs.extend(refs)
        try:
            unit_source_orders.append(int(unit["source_order"]))
            start, end = int(unit["char_start"]), int(unit["char_end"])
            unit_char_ranges.append((start, end))
            if start > end:
                errors.append({"code": "UNIT_CHAR_RANGE_INVALID", "unit_id": unit_id})
        except (KeyError, TypeError, ValueError):
            errors.append({"code": "UNIT_METADATA_INVALID", "unit_id": unit_id})

    duplicates = sorted({ref for ref in indexed_refs if indexed_refs.count(ref) > 1})
    missing = sorted(source_ref_set - set(indexed_refs))
    unknown = sorted(set(indexed_refs) - source_ref_set)
    if duplicates:
        errors.append({"code": "INDEXED_ANCHOR_DUPLICATE", "refs": duplicates})
    if missing:
        errors.append({"code": "INDEXED_ANCHOR_MISSING", "refs": missing})
    if unknown:
        errors.append({"code": "INDEXED_ANCHOR_UNKNOWN", "refs": unknown})
    if len(indexed_refs) != expected_count:
        errors.append({"code": "INDEXED_ANCHOR_COUNT_MISMATCH", "expected": expected_count, "actual": len(indexed_refs)})

    expected_unit_ids = [f"NU_{i:04d}" for i in range(1, len(units) + 1)]
    if unit_ids != expected_unit_ids:
        errors.append({"code": "UNIT_ID_SEQUENCE_INVALID"})
    if unit_source_orders != list(range(1, len(units) + 1)):
        errors.append({"code": "UNIT_SOURCE_ORDER_INVALID"})
    if indexed_refs and indexed_refs != [str(row.get("anchor_ref")) for row in sorted(source_anchors, key=lambda row: (int(row.get("char_start", 0)), int(row.get("char_end", 0)), str(row.get("anchor_ref") or "")))]:
        errors.append({"code": "ANCHOR_SOURCE_ORDER_NOT_PRESERVED"})

    source_by_ref = {str(row.get("anchor_ref")): row for row in source_anchors if isinstance(row, dict)}
    indexed_rows = [source_by_ref.get(ref) for ref in indexed_refs]
    indexed_rows = [row for row in indexed_rows if row is not None]
    if indexed_rows:
        starts = [int(row.get("char_start")) for row in indexed_rows]
        ends = [int(row.get("char_end")) for row in indexed_rows]
        if starts != sorted(starts) or any(left > right for left, right in zip(starts, starts[1:])):
            errors.append({"code": "ANCHOR_CHAR_ORDER_INVALID"})
        if any(start < previous_end for start, previous_end in zip(starts[1:], ends)):
            errors.append({"code": "ANCHOR_CHAR_OVERLAP"})
        first_ref, last_ref = indexed_refs[0], indexed_refs[-1]
        if first_ref != expected_refs[0] or last_ref != expected_refs[-1]:
            errors.append({"code": "BOUNDARY_ANCHOR_NOT_COVERED", "first": first_ref, "last": last_ref})
        last_anchor_char_end = max(ends)
    else:
        first_ref = last_ref = None
        last_anchor_char_end = None

    raw_char_length = None
    raw_byte_length = None
    if raw_bytes is not None:
        try:
            raw_char_length = len(raw_bytes.decode("utf-8"))
            raw_byte_length = len(raw_bytes)
        except UnicodeDecodeError:
            errors.append({"code": "RAW_SOURCE_UTF8_INVALID"})
    trailing_chars = None if raw_char_length is None or last_anchor_char_end is None else max(0, raw_char_length - last_anchor_char_end)
    metadata_checks = {
        "schema_version": narrative_unit_index.get("schema_version") == "source_narrative_unit_index_v1",
        "provider_calls": narrative_unit_index.get("provider_calls") == 0,
        "semantic_interpretation": narrative_unit_index.get("semantic_interpretation") is False,
        "source_package_id": narrative_unit_index.get("source_package_id") == source_evidence_index.get("source_package_id"),
        "source_version_id": narrative_unit_index.get("source_version_id") == source_evidence_index.get("source_version_id"),
        "source_raw_hash": narrative_unit_index.get("source_raw_hash") == source_evidence_index.get("source_raw_hash"),
    }
    for name, passed in metadata_checks.items():
        if not passed:
            errors.append({"code": "SOURCE_METADATA_MISMATCH", "field": name})
    if narrative_unit_index.get("anchor_count") != expected_count:
        errors.append({"code": "INDEX_METADATA_ANCHOR_COUNT_MISMATCH", "expected": expected_count, "actual": narrative_unit_index.get("anchor_count")})
    if narrative_unit_index.get("full_anchor_count") != expected_count:
        errors.append({"code": "INDEX_METADATA_FULL_ANCHOR_COUNT_MISMATCH", "expected": expected_count, "actual": narrative_unit_index.get("full_anchor_count")})

    return {
        "schema_version": "source_narrative_unit_completeness_v1",
        "status": "PASS" if not errors else "FAIL",
        "provider_calls": 0,
        "input_anchor_count": len(source_anchors),
        "expected_anchor_count": expected_count,
        "indexed_anchor_count": len(indexed_refs),
        "unique_indexed_anchor_count": len(set(indexed_refs)),
        "missing_anchor_refs": missing,
        "duplicate_anchor_refs": duplicates,
        "unknown_anchor_refs": unknown,
        "first_anchor_ref": first_ref,
        "last_anchor_ref": last_ref,
        "first_anchor_indexed": bool(indexed_refs and indexed_refs[0] == "E0001"),
        "last_anchor_indexed": bool(indexed_refs and indexed_refs[-1] == f"E{expected_count:04d}"),
        "unit_count": len(units),
        "unit_ids_contiguous": unit_ids == expected_unit_ids,
        "source_order_contiguous": unit_source_orders == list(range(1, len(units) + 1)),
        "source_order_preserved": not any(error.get("code") == "ANCHOR_SOURCE_ORDER_NOT_PRESERVED" for error in errors),
        "char_order_stable": not any(error.get("code") in {"ANCHOR_CHAR_ORDER_INVALID", "ANCHOR_CHAR_OVERLAP"} for error in errors),
        "raw_char_length": raw_char_length,
        "raw_byte_length": raw_byte_length,
        "last_anchor_char_end": last_anchor_char_end,
        "trailing_unanchored_chars": trailing_chars,
        "metadata_checks": metadata_checks,
        "errors": errors,
    }


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


# ---------------------------------------------------------------------------
# Targeted missing-fact coverage (provider-free extension)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MissingFactManifest:
    """Stable, serializable description of facts still required downstream."""

    status: str
    items: tuple[dict[str, Any], ...]
    fingerprint: str
    schema_version: str = "missing_fact_manifest_v1"

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "status": self.status, "items": [dict(item) for item in self.items], "count": len(self.items), "fingerprint": self.fingerprint}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "MissingFactManifest":
        items = tuple(item for item in (value or {}).get("items", []) if isinstance(item, dict))
        fp = str((value or {}).get("fingerprint") or fingerprint(list(items)))
        return cls(status=str((value or {}).get("status") or "FACT_COVERAGE_INSUFFICIENT"), items=items, fingerprint=fp, schema_version=str((value or {}).get("schema_version") or "missing_fact_manifest_v1"))


def fact_key(item: dict[str, Any]) -> str:
    return "|".join(str(item.get(name) or "").strip() for name in ("subject_type", "subject_id", "predicate", "scope"))


def _targeted_canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _targeted_evidence_usable(evidence: Any) -> bool:
    if not isinstance(evidence, list) or not evidence:
        return False
    for row in evidence:
        if not isinstance(row, dict):
            return False
        if row.get("verified") is True and (row.get("anchor_ref") or row.get("source_id")):
            continue
        if row.get("anchor_ref") and row.get("excerpt") and row.get("source_raw_hash"):
            continue
        return False
    return True


def _targeted_requirement(raw: Any, index: int) -> dict[str, Any]:
    item = raw if isinstance(raw, dict) else {}
    subject_type = str(item.get("subject_type") or item.get("semantic_type") or "").strip()
    subject_id = str(item.get("subject_id") or item.get("entity") or item.get("subject") or "").strip()
    predicate = str(item.get("predicate") or "").strip()
    scope = str(item.get("scope") or "global").strip()
    return {
        "fact_key": str(item.get("fact_key") or "|".join((subject_type, subject_id, predicate, scope)) or f"requirement_{index:04d}"),
        "semantic_type": subject_type, "subject_type": subject_type, "entity": subject_id, "subject_id": subject_id,
        "predicate": predicate, "scope": scope, "consumer": str(item.get("consumer") or "script_ir").strip(),
        "required": bool(item.get("required", True)), "optional": bool(item.get("optional", False)),
        "severity": str(item.get("severity") or ("blocking" if item.get("required", True) else "warning")).strip(),
        "source_scope": item.get("source_scope") if isinstance(item.get("source_scope"), list) else ["source_material"],
        "dependency": item.get("dependency") if isinstance(item.get("dependency"), list) else [],
        "description": str(item.get("description") or "").strip(), "expected_value": item.get("expected_value", item.get("value")),
    }


def _targeted_requirement_matches(req: dict[str, Any], record: dict[str, Any]) -> bool:
    return bool(req.get("fact_key") and req["fact_key"] == fact_key(record)) or all(not str(req.get(name) or "").strip() or str(req.get(name)).strip() == str(record.get(name) or "").strip() for name in ("subject_type", "subject_id", "predicate", "scope"))


def build_missing_fact_manifest(requirements: list[dict[str, Any]], records: list[dict[str, Any]], *, source_scope: list[str] | None = None) -> dict[str, Any]:
    normalized = [_targeted_requirement(item, i) for i, item in enumerate(requirements or [], 1)]
    rows = [item for item in records or [] if isinstance(item, dict)]
    missing, coverage = [], []
    for req in normalized:
        matches = [row for row in rows if _targeted_requirement_matches(req, row)]
        reason = None
        evidence_state: dict[str, Any] = {"record_count": len(matches)}
        if not matches:
            reason, evidence_state["state"] = "ABSENT", "absent"
        elif any(not row.get("subject_type") or not row.get("subject_id") or not row.get("predicate") for row in matches):
            reason, evidence_state["state"] = "INVALID", "invalid"
        elif len({_targeted_canonical(row.get("value")) for row in matches}) > 1:
            reason, evidence_state["state"] = "CONFLICTED", "conflicted"
        elif any(str(row.get("status") or "").lower() in {"conflict", "unknown"} for row in matches):
            reason, evidence_state["state"] = "AMBIGUOUS", "ambiguous"
        elif not any(str(row.get("authority") or "").lower() in AUTHORITATIVE_AUTHORITIES and str(row.get("status") or "").lower() == "confirmed" and _targeted_evidence_usable(row.get("evidence")) for row in matches):
            reason, evidence_state["state"] = "INSUFFICIENT_EVIDENCE", "evidence_insufficient"
        elif req.get("expected_value") is not None and not any(_targeted_canonical(row.get("value")) == _targeted_canonical(req.get("expected_value")) for row in matches):
            reason, evidence_state["state"] = "CONFLICTED", "expected_value_conflict"
        else:
            evidence_state["state"] = "satisfied"
        coverage.append({"fact_key": req["fact_key"], "required": req["required"], "satisfied": reason is None, "reason": reason, "evidence": evidence_state})
        if reason and req["required"] and not req["optional"]:
            missing.append({"fact_key": req["fact_key"], "semantic_type": req["semantic_type"], "scope": req["scope"], "entity": req["entity"], "consumer": req["consumer"], "required": req["required"], "optional": req["optional"], "missing_reason": reason, "existing_evidence": evidence_state, "source_scope": source_scope if source_scope is not None else req["source_scope"], "severity": req["severity"], "dependency": req["dependency"], "description": req["description"], "expected_value": req["expected_value"]})
    status = "FACT_COVERAGE_SUFFICIENT" if not missing else "FACT_COVERAGE_INSUFFICIENT"
    manifest = MissingFactManifest(status=status, items=tuple(missing), fingerprint=fingerprint(missing)).to_dict()
    return {"schema_version": TARGETED_SCHEMA_VERSION, "status": status, "coverage": coverage, "missing_fact_manifest": manifest, "required_count": sum(1 for row in normalized if row["required"] and not row["optional"]), "satisfied_count": sum(1 for row in coverage if row["satisfied"]), "blocking_count": len(missing)}


def script_ir_gate(coverage: dict[str, Any]) -> dict[str, Any]:
    allowed = str((coverage or {}).get("status") or "") == "FACT_COVERAGE_SUFFICIENT"
    return {"allowed": allowed, "status": "SCRIPT_IR_ALLOWED" if allowed else "BLOCKED_PENDING_TARGETED_MISSING_FACTS", "reason": "fact coverage requirements satisfied" if allowed else "required facts remain unresolved"}


__all__ = ["REQUIREMENT_TYPES", "COVERAGE_STATUSES", "canonical_fact_components", "build_narrative_unit_index", "validate_narrative_unit_completeness", "requirement_contract", "coverage_matrix_contract", "coverage_provider_schema", "coverage_schema_fingerprint", "compile_fact_coverage", "validate_coverage_payload", "fingerprint", "MISSING_REASONS", "MissingFactManifest", "fact_key", "build_missing_fact_manifest", "script_ir_gate"]
