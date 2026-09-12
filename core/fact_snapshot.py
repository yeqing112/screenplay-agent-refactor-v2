"""Deterministic fact authority and unknown routing."""
from __future__ import annotations

import hashlib
import json
from typing import Any

AUTHORITIES = {"source_text", "locked_fact", "approved_fact", "derived_fact", "model_observation"}
FACT_STATUSES = {"confirmed", "proposed", "conflict", "unknown"}
UNKNOWN_CLASSES = {"blocking_unknown", "assumable_unknown", "creative_unknown"}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def snapshot_hash(records: list[dict[str, Any]]) -> str:
    return hashlib.sha256(_canonical(records).encode("utf-8")).hexdigest()


def _normalize_record(raw: Any, index: int) -> dict[str, Any]:
    item = raw if isinstance(raw, dict) else {}
    subject_type = str(item.get("subject_type") or "").strip()
    subject_id = str(item.get("subject_id") or "").strip()
    predicate = str(item.get("predicate") or "").strip()
    authority = str(item.get("authority") or "derived_fact").strip().lower()
    status = str(item.get("status") or "proposed").strip().lower()
    value = item.get("value")
    if "value_json" in item and "value" not in item:
        try:
            value = json.loads(str(item.get("value_json") or "null"))
        except (TypeError, ValueError, json.JSONDecodeError):
            value = item.get("value_json")
    return {
        "fact_id": str(item.get("fact_id") or f"FACT_{index:04d}"),
        "subject_type": subject_type,
        "subject_id": subject_id,
        "predicate": predicate,
        "value": value,
        "scope": str(item.get("scope") or "global"),
        "authority": authority,
        "status": status,
        "confidence": max(0.0, min(float(item.get("confidence", 0.0) or 0.0), 1.0)),
        "evidence": item.get("evidence") if isinstance(item.get("evidence"), list) else [],
        "conflict_group": item.get("conflict_group"),
    }


def classify_unknown(*, subject_type: str, predicate: str, production_critical: bool = False, creative: bool = False) -> str:
    if creative:
        return "creative_unknown"
    if production_critical:
        return "blocking_unknown"
    return "assumable_unknown"


def validate_fact_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    seen: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for idx, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            errors.append({"code": "FACT_RECORD_INVALID", "message": f"Record {idx} must be an object."})
            continue
        key = (str(record.get("subject_type") or ""), str(record.get("subject_id") or ""), str(record.get("predicate") or ""), str(record.get("scope") or "global"))
        if not all(key[:3]):
            errors.append({"code": "FACT_IDENTITY_REQUIRED", "message": f"Record {idx} requires subject_type, subject_id and predicate."})
        authority = str(record.get("authority") or "").lower()
        if authority not in AUTHORITIES:
            errors.append({"code": "FACT_AUTHORITY_INVALID", "message": f"Record {idx} authority is not allowed."})
        status = str(record.get("status") or "").lower()
        if status not in FACT_STATUSES:
            errors.append({"code": "FACT_STATUS_INVALID", "message": f"Record {idx} status is not allowed."})
        if key in seen and seen[key].get("value") != record.get("value"):
            errors.append({"code": "FACT_CONFLICT", "message": f"Conflicting values for {key[0]}/{key[1]}/{key[2]}."})
        else:
            seen[key] = record
        if authority in {"locked_fact", "approved_fact"} and status != "confirmed":
            errors.append({"code": "LOCKED_FACT_MUST_BE_CONFIRMED", "message": f"{authority} facts must be confirmed."})
        if not record.get("evidence") and authority in {"source_text", "locked_fact", "approved_fact"}:
            warnings.append({"code": "FACT_EVIDENCE_MISSING", "message": f"{record.get('fact_id', idx)} has no evidence."})
    return {"status": "qualified" if not errors else "needs_review", "errors": errors, "warnings": warnings}


def build_fact_snapshot(records: list[dict[str, Any]], *, book_id: int, episode: int | None = None, source_fingerprint: str = "") -> dict[str, Any]:
    normalized = [_normalize_record(item, idx) for idx, item in enumerate(records, start=1)]
    report = validate_fact_records(normalized)
    return {
        "schema_version": "fact_snapshot_v1",
        "book_id": int(book_id),
        "episode": int(episode) if episode is not None else None,
        "records": normalized,
        "source_fingerprint": str(source_fingerprint or ""),
        "payload_hash": snapshot_hash(normalized),
        "validation": report,
    }

