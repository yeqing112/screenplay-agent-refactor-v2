"""Provider-free, scope-bound extraction for a MissingFactManifest.

Only explicit structured declarations are promoted.  Natural-language text
without a verifiable declaration remains unresolved; this is intentional and
keeps the FactSnapshot fail-closed.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any

from core.fact_coverage import fact_key
from core.fact_snapshot import build_fact_snapshot
from core.source_evidence_index import build_source_evidence_index

SCHEMA_VERSION = "targeted_missing_fact_extraction_v1"
_DECLARATION_RE = re.compile(r"(?:FACT|事实)\s*:\s*(?P<body>.+)", re.IGNORECASE)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def build_source_index(source_material: Any, *, source_package_id: str = "targeted-source", source_version_id: str = "v1") -> dict[str, Any]:
    if isinstance(source_material, dict) and isinstance(source_material.get("source_index"), dict):
        return copy.deepcopy(source_material["source_index"])
    if isinstance(source_material, (dict, list)):
        text = json.dumps(source_material, ensure_ascii=False, indent=2)
    else:
        text = str(source_material or "")
    raw = text.encode("utf-8")
    return build_source_evidence_index(raw, source_package_id=source_package_id, source_version_id=source_version_id)


def _structured_declarations(source_material: Any, source_index: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(source_material, dict):
        raw = source_material.get("facts")
        if isinstance(raw, list):
            rows.extend(item for item in raw if isinstance(item, dict))
    elif isinstance(source_material, list):
        rows.extend(item for item in source_material if isinstance(item, dict))
    # A line-oriented declaration is intentionally strict: every field needed
    # to identify and support a fact must be explicit.
    for anchor in source_index.get("anchors") or []:
        # One source block may contain several declarations.  Parse each line
        # independently so contradictory declarations cannot be hidden by a
        # greedy match over the whole block.
        for line in _text(anchor.get("exact_text")).splitlines():
            match = _DECLARATION_RE.search(line)
            if not match:
                continue
            fields: dict[str, Any] = {"_anchor_ref": anchor.get("anchor_ref")}
            for part in re.split(r"[;；]\s*", match.group("body")):
                if "=" not in part:
                    continue
                key, value = part.split("=", 1)
                fields[key.strip().lower()] = value.strip()
            if fields.get("subject_type") and (fields.get("subject_id") or fields.get("entity")) and fields.get("predicate") and "value" in fields:
                rows.append(fields)
    return rows


def _find_anchor_for_declaration(row: dict[str, Any], source_index: dict[str, Any]) -> dict[str, Any] | None:
    ref = _text(row.get("_anchor_ref") or row.get("anchor_ref"))
    anchors = [a for a in source_index.get("anchors") or [] if isinstance(a, dict)]
    if ref:
        return next((a for a in anchors if a.get("anchor_ref") == ref), None)
    # JSON facts are represented in the serialized source index.  Require all
    # identifying fields to appear in one anchor; otherwise leave unresolved.
    subject = _text(row.get("subject_id") or row.get("subject_label") or row.get("entity"))
    predicate = _text(row.get("predicate"))
    value = _text(row.get("value"))
    for anchor in anchors:
        text = _text(anchor.get("exact_text"))
        if subject and predicate and value and subject in text and predicate in text and value in text:
            return anchor
    return None


def _value_from_text(value: Any) -> Any:
    if not isinstance(value, str):
        return copy.deepcopy(value)
    raw = value.strip()
    try:
        return json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return raw


def _requirement_match(requirement: dict[str, Any], row: dict[str, Any]) -> bool:
    req_key = _text(requirement.get("fact_key"))
    candidate = {"subject_type": row.get("subject_type"), "subject_id": row.get("subject_id") or row.get("subject_label") or row.get("entity"), "predicate": row.get("predicate"), "scope": row.get("scope") or "global"}
    return req_key == fact_key(candidate) or all(not _text(requirement.get(name)) or _text(requirement.get(name)) == _text(candidate.get(name)) for name in ("subject_type", "subject_id", "predicate", "scope"))


def validate_candidate_fact(candidate: dict[str, Any], requirement: dict[str, Any], source_index: dict[str, Any], existing_records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    if not _requirement_match(requirement, candidate):
        errors.append({"code": "CANDIDATE_OUT_OF_SCOPE", "message": "Candidate is not requested by MissingFactManifest."})
    for field in ("subject_type", "subject_id", "predicate"):
        if not _text(candidate.get(field)):
            errors.append({"code": "CANDIDATE_SCHEMA_INVALID", "message": f"{field} is required."})
    evidence = candidate.get("evidence") if isinstance(candidate.get("evidence"), list) else []
    if not evidence:
        errors.append({"code": "CANDIDATE_EVIDENCE_REQUIRED", "message": "Every candidate requires evidence."})
    by_ref = {a.get("anchor_ref"): a for a in source_index.get("anchors") or [] if isinstance(a, dict)}
    for row in evidence:
        if not isinstance(row, dict) or _text(row.get("anchor_ref")) not in by_ref:
            errors.append({"code": "SOURCE_LOCATOR_INVALID", "message": "Evidence anchor_ref is not present in the source index."})
            continue
        anchor = by_ref[_text(row.get("anchor_ref"))]
        if row.get("excerpt") and row.get("excerpt") != anchor.get("exact_text"):
            errors.append({"code": "EVIDENCE_EXCERPT_MISMATCH", "message": f"Evidence excerpt does not match {anchor.get('anchor_ref')}."})
        if row.get("source_raw_hash") and row.get("source_raw_hash") != source_index.get("source_raw_hash"):
            errors.append({"code": "EVIDENCE_SOURCE_HASH_MISMATCH", "message": "Evidence source hash does not match the immutable source."})
        support_text = _text(anchor.get("exact_text"))
        value_text = _text(candidate.get("value"))
        # Avoid substring false positives (for example ``male`` in
        # ``female``); a value must be the explicit value field or a bounded
        # token in the immutable excerpt.
        value_pattern = re.compile(r"(?:^|[=:,;；\s])" + re.escape(value_text) + r"(?:$|[,;；\s])") if value_text else None
        if value_text and not (re.search(r"value\s*[=:]\s*[\"']?" + re.escape(value_text) + r"[\"']?(?:$|[,;；\s])", support_text, re.IGNORECASE) or value_pattern and value_pattern.search(support_text)):
            errors.append({"code": "EVIDENCE_VALUE_UNSUPPORTED", "message": "Evidence anchor does not support candidate value."})
    existing = [r for r in (existing_records or []) if isinstance(r, dict) and fact_key(r) == fact_key(candidate)]
    if any(str(r.get("authority") or "").lower() in {"source_text", "locked_fact", "approved_fact"} and str(r.get("status") or "").lower() == "confirmed" and _canonical(r.get("value")) != _canonical(candidate.get("value")) for r in existing):
        errors.append({"code": "AUTHORITATIVE_FACT_CONFLICT", "message": "Candidate conflicts with an existing authoritative fact."})
    return {"valid": not errors, "errors": errors}


def extract_targeted_missing_facts(source_material: Any, current_snapshot: dict[str, Any] | None, missing_manifest: dict[str, Any], *, source_package_id: str = "targeted-source", source_version_id: str = "v1") -> dict[str, Any]:
    manifest_items = (missing_manifest or {}).get("items") if isinstance(missing_manifest, dict) else []
    manifest_items = [item for item in manifest_items if isinstance(item, dict)]
    source_index = build_source_index(source_material, source_package_id=source_package_id, source_version_id=source_version_id)
    existing = (current_snapshot or {}).get("records") if isinstance(current_snapshot, dict) else []
    existing = [row for row in (existing or []) if isinstance(row, dict)]
    declarations = _structured_declarations(source_material, source_index)
    candidates: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for requirement in manifest_items:
        matches = [row for row in declarations if _requirement_match(requirement, row)]
        if not matches:
            unresolved.append({"fact_key": requirement.get("fact_key"), "reason": "NO_RELIABLE_EVIDENCE", "missing_reason": requirement.get("missing_reason")})
            continue
        # More than one explicit value is a conflict, never a choice.
        values = {_canonical(_value_from_text(row.get("value"))) for row in matches}
        if len(values) > 1:
            unresolved.append({"fact_key": requirement.get("fact_key"), "reason": "CONFLICTING_SOURCE_DECLARATIONS", "values": [row.get("value") for row in matches]})
            continue
        row = matches[0]
        anchor = _find_anchor_for_declaration(row, source_index)
        if not anchor:
            unresolved.append({"fact_key": requirement.get("fact_key"), "reason": "SOURCE_LOCATOR_UNRESOLVED"})
            continue
        candidate = {"fact_id": f"TARGETED_{_hash({'requirement': requirement.get('fact_key'), 'value': row.get('value'), 'anchor': anchor.get('anchor_ref')})[:16]}", "subject_type": _text(row.get("subject_type")), "subject_id": _text(row.get("subject_id") or row.get("subject_label") or row.get("entity")), "predicate": _text(row.get("predicate")), "value": _value_from_text(row.get("value")), "scope": _text(row.get("scope") or "global"), "authority": "source_text", "status": "confirmed", "confidence": 1.0, "evidence": [{"anchor_ref": anchor.get("anchor_ref"), "excerpt": anchor.get("exact_text"), "char_start": anchor.get("char_start"), "char_end": anchor.get("char_end"), "byte_start": anchor.get("byte_start"), "byte_end": anchor.get("byte_end"), "source_raw_hash": anchor.get("source_raw_hash"), "verified": True}]}
        validation = validate_candidate_fact(candidate, requirement, source_index, existing)
        diagnostics.append({"fact_key": requirement.get("fact_key"), "validation": validation})
        if validation["valid"]:
            candidates.append(candidate)
        else:
            unresolved.append({"fact_key": requirement.get("fact_key"), "reason": "CANDIDATE_REJECTED", "errors": validation["errors"]})
    return {"schema_version": SCHEMA_VERSION, "source_index": source_index, "manifest_fingerprint": (missing_manifest or {}).get("fingerprint"), "candidates": candidates, "unresolved": unresolved, "diagnostics": diagnostics, "provider_calls": 0, "result_fingerprint": _hash({"candidates": candidates, "unresolved": unresolved})}


def merge_fact_snapshot_records(current_snapshot: dict[str, Any], candidates: list[dict[str, Any]], missing_manifest: dict[str, Any], source_index: dict[str, Any]) -> dict[str, Any]:
    existing = [copy.deepcopy(row) for row in (current_snapshot or {}).get("records", []) if isinstance(row, dict)]
    allowed = {item.get("fact_key") for item in (missing_manifest or {}).get("items", []) if isinstance(item, dict)}
    merged = list(existing)
    conflicts: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    added: list[str] = []
    for candidate in candidates or []:
        if not isinstance(candidate, dict) or fact_key(candidate) not in allowed:
            unresolved.append({"fact_key": fact_key(candidate) if isinstance(candidate, dict) else "", "reason": "OUT_OF_SCOPE"})
            continue
        validation = validate_candidate_fact(candidate, {"fact_key": fact_key(candidate)}, source_index, existing)
        if not validation["valid"]:
            unresolved.append({"fact_key": fact_key(candidate), "reason": "CANDIDATE_REJECTED", "errors": validation["errors"]})
            continue
        same = [row for row in merged if fact_key(row) == fact_key(candidate)]
        if any(str(row.get("authority") or "").lower() in {"source_text", "locked_fact", "approved_fact"} and str(row.get("status") or "").lower() == "confirmed" for row in same):
            if any(not _canonical(row.get("value")) == _canonical(candidate.get("value")) for row in same):
                conflicts.append({"fact_key": fact_key(candidate), "existing": same, "candidate": candidate})
            continue
        if same and any(_canonical(row.get("value")) != _canonical(candidate.get("value")) for row in same):
            conflicts.append({"fact_key": fact_key(candidate), "existing": same, "candidate": candidate})
            continue
        if not same:
            merged.append(copy.deepcopy(candidate)); added.append(fact_key(candidate))
    merged.sort(key=lambda row: (fact_key(row), _canonical(row.get("value"))))
    snapshot = build_fact_snapshot(merged, book_id=int((current_snapshot or {}).get("book_id") or 0), episode=(current_snapshot or {}).get("episode"), source_fingerprint=str((current_snapshot or {}).get("source_fingerprint") or source_index.get("source_raw_hash") or ""))
    revision = int((current_snapshot or {}).get("revision") or 0) + (1 if added else 0)
    snapshot["revision"] = revision
    return {"schema_version": "fact_snapshot_merge_v1", "snapshot": snapshot, "added": added, "conflicts": conflicts, "unresolved": unresolved, "changed": bool(added), "revision": revision, "provider_calls": 0}


__all__ = ["SCHEMA_VERSION", "build_source_index", "validate_candidate_fact", "extract_targeted_missing_facts", "merge_fact_snapshot_records"]
