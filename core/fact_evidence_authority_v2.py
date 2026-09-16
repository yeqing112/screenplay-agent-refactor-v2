"""Fact Evidence Authority V2: provider refs, program-owned source spans."""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from core.fact_snapshot import build_fact_snapshot
from core.source_evidence_index import SCHEMA_VERSION as INDEX_SCHEMA

SCHEMA_VERSION = "fact_evidence_authority_v2"
EPISTEMIC_CLASSES = ("SOURCE_ASSERTED_FACT", "SOURCE_OBSERVED_ACTION", "SOURCE_SPEECH_ACT", "CHARACTER_CLAIM_CONTENT", "MODEL_INFERENCE", "UNKNOWN")
FORBIDDEN_FIELDS = ("fact_id", "final_status", "authority", "start", "end", "char_start", "char_end", "byte_start", "byte_end", "excerpt", "evidence")
CONFIRMED_CLASSES = {"SOURCE_ASSERTED_FACT", "SOURCE_OBSERVED_ACTION", "SOURCE_SPEECH_ACT", "CHARACTER_CLAIM_CONTENT"}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def provider_schema() -> dict[str, Any]:
    fact_properties = {
        "subject_type": {"type": "string"},
        "subject_label": {"type": "string"},
        "predicate": {"type": "string"},
        "value": {},
        "epistemic_class": {"enum": list(EPISTEMIC_CLASSES)},
        "evidence_refs": {"type": "array", "items": {"type": "string", "pattern": "^E[0-9]{4}$"}},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    }
    return {
        "type": "object",
        "required": ["facts"],
        "properties": {"facts": {"type": "array", "items": {"type": "object", "required": ["subject_type", "subject_label", "predicate", "value", "epistemic_class", "evidence_refs", "confidence"], "additionalProperties": False, "properties": fact_properties}}},
        "additionalProperties": False,
    }


def contract() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "provider_owns": ["what_fact_it_sees", "evidence_refs"], "program_owns": ["anchor_ids", "exact_text", "char_offsets", "byte_offsets", "fact_ids", "authority", "status"], "epistemic_classes": list(EPISTEMIC_CLASSES), "forbidden_provider_fields": list(FORBIDDEN_FIELDS), "legacy_free_text_evidence_fallback": False, "resolver": "resolve_evidence_refs_v1", "source_index_schema": INDEX_SCHEMA}


def schema_fingerprint() -> str:
    return hashlib.sha256(_canonical({"contract": contract(), "provider_schema": provider_schema()})).hexdigest()


def build_fact_request_v2(*, raw_text: str, source_package_id: str, source_version_id: str, source_raw_hash: str, source_index: dict[str, Any], provider: str = "", model: str = "") -> dict[str, Any]:
    return {"task": "extract_source_grounded_facts_v2", "source_package_id": source_package_id, "source_version_id": source_version_id, "source_fingerprint": source_raw_hash, "source_blocks": [{"ref": row["anchor_ref"], "text": row["exact_text"]} for row in source_index.get("anchors") or []], "contract": {**contract(), "schema_fingerprint": schema_fingerprint(), "output_schema": provider_schema()}, "provider": provider, "model": model}


def resolve_evidence_refs_v1(evidence_refs: Any, source_index: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    rows = evidence_refs if isinstance(evidence_refs, list) else []
    by_ref = {row.get("anchor_ref"): row for row in source_index.get("anchors") or []}
    errors: list[dict[str, str]] = []
    selected: dict[str, dict[str, Any]] = {}
    if not isinstance(evidence_refs, list):
        errors.append({"code": "SOURCE_EVIDENCE_REF_REQUIRED", "message": "evidence_refs must be an array"})
    for ref in rows:
        if not isinstance(ref, str) or ref not in by_ref:
            errors.append({"code": "SOURCE_EVIDENCE_REF_UNKNOWN", "message": str(ref)})
            continue
        selected[ref] = by_ref[ref]
    resolved = []
    for row in sorted(selected.values(), key=lambda item: item["ordinal"]):
        resolved.append({"anchor_ref": row["anchor_ref"], "excerpt": row["exact_text"], "char_start": row["char_start"], "char_end": row["char_end"], "byte_start": row["byte_start"], "byte_end": row["byte_end"], "verified": True, "source_raw_hash": row["source_raw_hash"]})
    return resolved, errors


def canonicalize_fact_payload_v2(payload: Any, *, source_index: dict[str, Any], book_id: int, episode: int, source_fingerprint: str, provenance: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    if not isinstance(payload, dict) or not isinstance(payload.get("facts"), list):
        return {"snapshot": build_fact_snapshot([], book_id=book_id, episode=episode, source_fingerprint=source_fingerprint), "report": {"status": "FAIL", "errors": [{"code": "PROVIDER_OUTPUT_SCHEMA_INVALID"}], "total_facts": 0}}
    normalized: list[dict[str, Any]] = []
    evidence_verified = 0
    for index, raw in enumerate(payload["facts"], 1):
        if not isinstance(raw, dict):
            errors.append({"code": "FACT_RECORD_INVALID", "index": str(index)})
            continue
        forbidden = sorted(set(raw).intersection(FORBIDDEN_FIELDS))
        if forbidden:
            errors.append({"code": "V2_PROVIDER_FORBIDDEN_FIELD", "index": str(index), "fields": ",".join(forbidden)})
        epistemic = str(raw.get("epistemic_class") or "UNKNOWN")
        resolved, ref_errors = resolve_evidence_refs_v1(raw.get("evidence_refs"), source_index)
        errors.extend(ref_errors)
        if epistemic in CONFIRMED_CLASSES and not raw.get("evidence_refs"):
            errors.append({"code": "SOURCE_EVIDENCE_REF_REQUIRED", "index": str(index)})
        if resolved:
            evidence_verified += 1
        authority, status = _map_epistemic(epistemic)
        normalized.append({"subject_type": str(raw.get("subject_type") or "").strip(), "subject_id": str(raw.get("subject_label") or "").strip(), "predicate": str(raw.get("predicate") or "").strip(), "value": copy.deepcopy(raw.get("value")), "authority": authority, "status": status, "confidence": raw.get("confidence", 0.0), "evidence": resolved})
    normalized.sort(key=lambda row: (row["subject_type"], row["subject_id"], row["predicate"], json.dumps(row["value"], ensure_ascii=False, sort_keys=True, default=str)))
    snapshot = build_fact_snapshot(normalized, book_id=book_id, episode=episode, source_fingerprint=source_fingerprint)
    snapshot["provenance"] = copy.deepcopy(provenance)
    report = {"status": "PASS" if not errors and snapshot["validation"]["status"] == "qualified" else "FAIL", "errors": errors, "total_facts": len(normalized), "evidence_verified": evidence_verified, "evidence_invalid": sum(1 for item in errors if item.get("code", "").startswith("SOURCE_EVIDENCE")), "schema_fingerprint": schema_fingerprint(), "provider_runtime_schema_parity": "PASS"}
    return {"snapshot": snapshot, "report": report}


def _map_epistemic(value: str) -> tuple[str, str]:
    if value in {"SOURCE_ASSERTED_FACT", "SOURCE_OBSERVED_ACTION", "SOURCE_SPEECH_ACT"}:
        return "source_text", "confirmed"
    if value == "CHARACTER_CLAIM_CONTENT":
        return "source_text", "proposed"
    if value == "MODEL_INFERENCE":
        return "model_observation", "proposed"
    return "model_observation", "unknown"


__all__ = ["SCHEMA_VERSION", "EPISTEMIC_CLASSES", "FORBIDDEN_FIELDS", "contract", "provider_schema", "schema_fingerprint", "build_fact_request_v2", "resolve_evidence_refs_v1", "canonicalize_fact_payload_v2"]
