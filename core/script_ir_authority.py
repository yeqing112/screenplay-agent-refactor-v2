"""Production authority activation and freshness checks for ScriptIR.

Activation is deliberately explicit and provider-free.  A structurally valid
ScriptIR is not production authority until its source anchors, FactSnapshot,
requirement contract, coverage result and payload hash are bound in one
transaction.
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from core.fact_coverage import fingerprint
from core.fact_snapshot import snapshot_hash
from core.source_evidence_index import build_source_evidence_index, validate_source_evidence_index
from core.script_ir import script_ir_hash, validate_script_ir
from core.script_creative_quality import run_script_creative_quality_gate
from core.script_ir_source_requirements import (
    CONTRACT_SCHEMA_VERSION,
    compile_script_ir_source_requirements,
    evaluate_script_ir_source_coverage,
    script_ir_source_requirement_contract,
)

AUTHORITY_ENVELOPE_SCHEMA_VERSION = "script_ir_authority_envelope_v1"
AUTHORITY_POLICY_VERSION = "script_ir_authority_policy_v1"
QUALIFICATION_STATES = ("STRUCTURALLY_VALID", "SOURCE_COVERAGE_QUALIFIED", "AUTHORITY_BOUND", "PRODUCTION_QUALIFIED")
STALE_STATUSES = ("UNKNOWN", "FRESH", "STALE")


class ScriptIRAuthorityError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _json(value: Any, fallback: Any) -> Any:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed
        except (TypeError, ValueError, json.JSONDecodeError):
            return fallback
    return value if value is not None else fallback


def _index_fingerprint(index: dict[str, Any]) -> str:
    return _text(index.get("evidence_index_fingerprint") or index.get("fingerprint"))


def _envelope_fingerprint(payload: dict[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key != "envelope_fingerprint"}
    return fingerprint(body)


def _anchor_contains_value(anchor_text: Any, expected: Any) -> bool:
    text = _text(anchor_text)
    value = _text(expected)
    if not value:
        return True
    if value in text:
        return True
    # Structured sources are often serialized with ensure_ascii=True.  The
    # immutable anchor remains byte-accurate; matching its JSON escaped form
    # still proves the value is present without rewriting the source text.
    escaped = json.dumps(value, ensure_ascii=True)[1:-1]
    return bool(escaped and escaped in text)


def build_authority_envelope(*, book_id: int, episode: int, script_ir_payload: dict[str, Any], source_package_id: str, source_version_id: str, immutable_source_raw_hash: str, source_evidence_index: dict[str, Any], fact_snapshot: dict[str, Any], contract: dict[str, Any], requirement_set: dict[str, Any], coverage_result: dict[str, Any], authority_revision: int = 1, activated_at: str | None = None) -> dict[str, Any]:
    payload_hash = script_ir_hash(script_ir_payload)
    coverage_fingerprint = _text(coverage_result.get("fingerprint")) or fingerprint(coverage_result)
    envelope = {
        "schema_version": AUTHORITY_ENVELOPE_SCHEMA_VERSION,
        "authority_policy_version": AUTHORITY_POLICY_VERSION,
        "book_id": int(book_id),
        "episode": int(episode),
        "script_ir_schema_version": _text(script_ir_payload.get("schema_version")) or "script_ir_v1",
        "script_ir_payload_hash": payload_hash,
        "source_package_id": _text(source_package_id),
        "source_version_id": _text(source_version_id),
        "immutable_source_raw_hash": _text(immutable_source_raw_hash),
        "source_evidence_index_fingerprint": _index_fingerprint(source_evidence_index),
        "fact_snapshot_id": int(fact_snapshot.get("id")) if str(fact_snapshot.get("id") or "").isdigit() else fact_snapshot.get("id"),
        "fact_snapshot_revision": int(fact_snapshot.get("revision") or 0),
        "fact_snapshot_payload_hash": _text(fact_snapshot.get("payload_hash")),
        "source_requirement_contract_version": _text(contract.get("schema_version")) or CONTRACT_SCHEMA_VERSION,
        "source_requirement_contract_fingerprint": _text(contract.get("fingerprint")) or fingerprint(contract),
        "compiled_requirement_set_fingerprint": _text(requirement_set.get("fingerprint")) or fingerprint(requirement_set),
        "source_coverage_result_fingerprint": coverage_fingerprint,
        "authority_revision": int(authority_revision),
        "authority_activated_at": activated_at or datetime.now(timezone.utc).isoformat(),
        "qualification_state": "PRODUCTION_QUALIFIED",
        "qualified": True,
        "stale": False,
        "stale_status": "FRESH",
        "stale_reasons": [],
    }
    envelope["envelope_fingerprint"] = _envelope_fingerprint(envelope)
    return envelope


def validate_source_anchor_bindings(*, requirement_set: dict[str, Any], source_evidence_index: dict[str, Any], bindings: dict[str, Any] | None) -> dict[str, Any]:
    anchors = {str(row.get("anchor_ref")): row for row in (source_evidence_index.get("anchors") or []) if isinstance(row, dict) and row.get("anchor_ref")}
    errors: list[dict[str, Any]] = []
    result: dict[str, list[str]] = {}
    for req in requirement_set.get("requirements", []) if isinstance(requirement_set, dict) else []:
        if not req.get("blocking"):
            continue
        req_id = str(req.get("requirement_id") or "")
        refs = bindings.get(req_id) if isinstance(bindings, dict) else None
        refs = [str(ref).strip() for ref in (refs if isinstance(refs, list) else []) if str(ref).strip()]
        if not refs:
            errors.append({"code": "SOURCE_ANCHOR_BINDING_MISSING", "requirement_id": req_id})
            continue
        if any(ref not in anchors for ref in refs):
            errors.append({"code": "SOURCE_ANCHOR_REF_INVALID", "requirement_id": req_id, "refs": refs})
            continue
        for ref in refs:
            anchor = anchors[ref]
            if _text(anchor.get("source_package_id")) != _text(source_evidence_index.get("source_package_id")) or _text(anchor.get("source_version_id")) != _text(source_evidence_index.get("source_version_id")) or _text(anchor.get("source_raw_hash")) != _text(source_evidence_index.get("source_raw_hash")):
                errors.append({"code": "SOURCE_ANCHOR_LINEAGE_MISMATCH", "requirement_id": req_id, "anchor_ref": ref})
        expected = req.get("expected_value")
        if req.get("contract_requirement_id") == "SIR_SCENE_NAME" and expected and not any(_anchor_contains_value(anchors[ref].get("exact_text"), expected) for ref in refs):
            errors.append({"code": "SOURCE_ANCHOR_SCENE_NAME_MISMATCH", "requirement_id": req_id, "expected": expected, "refs": refs})
        result[req_id] = refs
    return {"status": "PASS" if not errors else "FAIL", "errors": errors, "bindings": result}


def validate_authority_envelope(envelope: dict[str, Any], *, payload: dict[str, Any] | None = None, expected: dict[str, Any] | None = None) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    if not isinstance(envelope, dict) or envelope.get("schema_version") != AUTHORITY_ENVELOPE_SCHEMA_VERSION:
        return {"status": "FAIL", "errors": [{"code": "SCRIPT_IR_AUTHORITY_ENVELOPE_INVALID"}]}
    if envelope.get("envelope_fingerprint") != _envelope_fingerprint(envelope):
        errors.append({"code": "SCRIPT_IR_AUTHORITY_ENVELOPE_TAMPERED"})
    if payload is not None and envelope.get("script_ir_payload_hash") != script_ir_hash(payload):
        errors.append({"code": "SCRIPT_IR_AUTHORITY_TAMPERED", "reason": "SCRIPT_IR_PAYLOAD_HASH_MISMATCH"})
        stale_reasons = ["SCRIPT_IR_PAYLOAD_CHANGED"]
    else:
        stale_reasons = []
    expected = expected or {}
    comparisons = {
        "authority_policy_version": expected.get("authority_policy_version"), "book_id": expected.get("book_id"), "episode": expected.get("episode"), "source_package_id": expected.get("source_package_id"), "source_version_id": expected.get("source_version_id"), "immutable_source_raw_hash": expected.get("immutable_source_raw_hash"), "source_evidence_index_fingerprint": expected.get("source_evidence_index_fingerprint"), "fact_snapshot_id": expected.get("fact_snapshot_id"), "fact_snapshot_revision": expected.get("fact_snapshot_revision"), "fact_snapshot_payload_hash": expected.get("fact_snapshot_payload_hash"), "source_requirement_contract_version": expected.get("source_requirement_contract_version"), "source_requirement_contract_fingerprint": expected.get("source_requirement_contract_fingerprint"), "compiled_requirement_set_fingerprint": expected.get("compiled_requirement_set_fingerprint"), "source_coverage_result_fingerprint": expected.get("source_coverage_result_fingerprint"),
    }
    reason_by_field = {"immutable_source_raw_hash": "SOURCE_CHANGED", "source_version_id": "SOURCE_CHANGED", "source_evidence_index_fingerprint": "SOURCE_CHANGED", "fact_snapshot_revision": "FACT_SNAPSHOT_CHANGED", "fact_snapshot_payload_hash": "FACT_SNAPSHOT_CHANGED", "source_requirement_contract_fingerprint": "REQUIREMENT_CONTRACT_CHANGED", "compiled_requirement_set_fingerprint": "REQUIREMENT_SET_CHANGED", "source_coverage_result_fingerprint": "COVERAGE_RESULT_STALE"}
    for field, value in comparisons.items():
        if value is not None and str(envelope.get(field)) != str(value):
            errors.append({"code": "SCRIPT_IR_AUTHORITY_STALE", "field": field, "expected": value, "actual": envelope.get(field)})
            if reason_by_field.get(field):
                stale_reasons.append(reason_by_field[field])
    if envelope.get("stale") is True or envelope.get("stale_status") == "STALE":
        errors.append({"code": "SCRIPT_IR_AUTHORITY_STALE", "field": "stale_status", "actual": envelope.get("stale_status")})
        stale_reasons.extend(str(item) for item in envelope.get("stale_reasons", []) if str(item).strip())
    if envelope.get("qualification_state") != "PRODUCTION_QUALIFIED" or envelope.get("qualified") is not True:
        errors.append({"code": "SCRIPT_IR_NOT_PRODUCTION_QUALIFIED"})
    return {"status": "PASS" if not errors else "FAIL", "errors": errors, "stale_reasons": sorted(set(stale_reasons))}


def validate_source_evidence_binding(*, source_evidence_index: dict[str, Any], raw_bytes: bytes, source_package_id: str, source_version_id: str, source_raw_hash: str) -> dict[str, Any]:
    """Validate that an evidence index is derived from the immutable bytes.

    A caller-supplied path or anchor name is not sufficient authority.  The
    offsets, exact text, lineage and deterministic index fingerprint must all
    agree with the bytes being activated.
    """

    if not isinstance(source_evidence_index, dict):
        return {"status": "FAIL", "errors": [{"code": "SOURCE_EVIDENCE_INDEX_REQUIRED"}]}
    errors: list[dict[str, Any]] = []
    if source_evidence_index.get("schema_version") != "source_evidence_index_v1":
        errors.append({"code": "SOURCE_EVIDENCE_INDEX_SCHEMA_INVALID"})
    if _text(source_evidence_index.get("source_package_id")) != _text(source_package_id):
        errors.append({"code": "SOURCE_EVIDENCE_INDEX_PACKAGE_MISMATCH"})
    if _text(source_evidence_index.get("source_version_id")) != _text(source_version_id):
        errors.append({"code": "SOURCE_EVIDENCE_INDEX_VERSION_MISMATCH"})
    if _text(source_evidence_index.get("source_raw_hash")) != _text(source_raw_hash):
        errors.append({"code": "SOURCE_EVIDENCE_INDEX_SOURCE_HASH_MISMATCH"})
    if _text(source_raw_hash) != hashlib.sha256(raw_bytes).hexdigest():
        errors.append({"code": "SOURCE_HASH_MISMATCH"})
    structural = validate_source_evidence_index(source_evidence_index, raw_bytes)
    if structural.get("status") != "PASS":
        errors.append({"code": "SOURCE_EVIDENCE_INDEX_OFFSETS_INVALID", "details": structural})
    try:
        expected = build_source_evidence_index(raw_bytes, source_package_id=source_package_id, source_version_id=source_version_id, source_raw_hash=source_raw_hash)
        actual_fp = _index_fingerprint(source_evidence_index)
        if actual_fp != expected.get("evidence_index_fingerprint"):
            errors.append({"code": "SOURCE_EVIDENCE_INDEX_FINGERPRINT_MISMATCH", "expected": expected.get("evidence_index_fingerprint"), "actual": actual_fp})
    except (TypeError, UnicodeDecodeError, ValueError) as exc:
        errors.append({"code": "SOURCE_EVIDENCE_INDEX_REBUILD_FAILED", "message": str(exc)})
    return {"status": "PASS" if not errors else "FAIL", "errors": errors, "fingerprint": _index_fingerprint(source_evidence_index)}


def activate_script_ir(*, session: Any, script_row: Any, draft_row: Any, source_structure: dict[str, Any], source_package_id: str, source_version_id: str, immutable_source_raw_hash: str, source_evidence_index: dict[str, Any], source_anchor_bindings: dict[str, Any], fact_snapshot_row: Any, authority_revision: int | None = None) -> dict[str, Any]:
    """Atomically create production authority and update the current pointer."""

    if not isinstance(source_structure, dict):
        raise ScriptIRAuthorityError("SOURCE_STRUCTURE_REQUIRED", "Source structure is required for ScriptIR activation.")
    try:
        payload = _json(draft_row.payload_json, {})
    except Exception as exc:
        raise ScriptIRAuthorityError("SCRIPT_IR_PAYLOAD_INVALID", "ScriptIR payload is invalid.") from exc
    structural = validate_script_ir(payload)
    if structural.get("status") != "qualified":
        raise ScriptIRAuthorityError("SCRIPT_IR_NOT_STRUCTURALLY_VALID", "ScriptIR structural validation failed.", details={"validation": structural})
    creative = run_script_creative_quality_gate(payload, production=True)
    if not creative.get("qualified"):
        first_error = (creative.get("hard_errors") or [{}])[0]
        raise ScriptIRAuthorityError(
            str(first_error.get("code") or "SCRIPT_CREATIVE_QUALITY_BLOCKED"),
            "ScriptIR creative quality and explicit timeline gates failed.",
            details={"creative_quality": creative},
        )
    scenes = payload.get("scenes") if isinstance(payload.get("scenes"), list) else []
    if any(_text(scene.get("name")).startswith("未命名场景") for scene in scenes if isinstance(scene, dict)):
        raise ScriptIRAuthorityError("SCENE_NAME_SOURCE_AUTHORITY_REQUIRED", "Placeholder scene names cannot become production authority.")
    raw_source_bytes = str(getattr(script_row, "content", "") or "").encode("utf-8")
    current_source_hash = hashlib.sha256(raw_source_bytes).hexdigest()
    if _text(getattr(draft_row, "source_fingerprint", "")) and _text(getattr(draft_row, "source_fingerprint", "")) != current_source_hash:
        raise ScriptIRAuthorityError("SCRIPT_IR_DRAFT_STALE", "ScriptIR draft was built from a different immutable source revision.")
    try:
        parsed_source = json.loads(getattr(script_row, "content", "") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        parsed_source = None
    if isinstance(parsed_source, dict) and parsed_source != source_structure:
        raise ScriptIRAuthorityError("SOURCE_STRUCTURE_MISMATCH", "Activation source structure does not match the immutable source payload.")
    if not fact_snapshot_row or int(getattr(fact_snapshot_row, "book_id", -1)) != int(script_row.book_id) or int(getattr(fact_snapshot_row, "episode", -1) or -1) != int(script_row.episode) or str(getattr(fact_snapshot_row, "status", "")).lower() != "confirmed":
        raise ScriptIRAuthorityError("FACT_SNAPSHOT_BINDING_INVALID", "FactSnapshot must be confirmed and match book/episode.")
    contract = script_ir_source_requirement_contract()
    requirement_set = compile_script_ir_source_requirements(source_structure=source_structure)
    snapshot_records = _json(getattr(fact_snapshot_row, "records_json", "[]"), [])
    coverage = evaluate_script_ir_source_coverage(requirement_set, records=snapshot_records if isinstance(snapshot_records, list) else [], allow_source_structure_fallback=False)
    if coverage.get("status") != "SCRIPT_IR_SOURCE_CONTRACT_COVERAGE_SUFFICIENT":
        raise ScriptIRAuthorityError("SCRIPT_IR_SOURCE_COVERAGE_INSUFFICIENT", "ScriptIR source coverage is insufficient.", details={"coverage": coverage})
    evidence_index_check = validate_source_evidence_binding(source_evidence_index=source_evidence_index, raw_bytes=raw_source_bytes, source_package_id=source_package_id, source_version_id=source_version_id, source_raw_hash=immutable_source_raw_hash)
    if evidence_index_check["status"] != "PASS":
        raise ScriptIRAuthorityError("SOURCE_EVIDENCE_INDEX_INVALID", "Source evidence index is not derived from the immutable source.", details=evidence_index_check)
    anchor_check = validate_source_anchor_bindings(requirement_set=requirement_set, source_evidence_index=source_evidence_index, bindings=source_anchor_bindings)
    if anchor_check["status"] != "PASS":
        raise ScriptIRAuthorityError("SOURCE_EVIDENCE_BINDING_REQUIRED", "Blocking ScriptIR requirements are not bound to immutable source anchors.", details=anchor_check)
    if not _text(source_package_id) or not _text(source_version_id) or not _text(immutable_source_raw_hash) or not _index_fingerprint(source_evidence_index):
        raise ScriptIRAuthorityError("SOURCE_LINEAGE_REQUIRED", "Source package, version, raw hash and evidence index are required.")
    if current_source_hash != _text(immutable_source_raw_hash):
        raise ScriptIRAuthorityError("SOURCE_HASH_MISMATCH", "Immutable source raw hash does not match the current script source.")
    if not _text(getattr(fact_snapshot_row, "payload_hash", "")):
        raise ScriptIRAuthorityError("FACT_SNAPSHOT_PAYLOAD_HASH_REQUIRED", "Bound FactSnapshot payload hash is required.")
    if isinstance(snapshot_records, list) and snapshot_hash(snapshot_records) != _text(getattr(fact_snapshot_row, "payload_hash", "")):
        raise ScriptIRAuthorityError("FACT_SNAPSHOT_PAYLOAD_HASH_MISMATCH", "FactSnapshot payload hash does not match its records.")
    try:
        fact_report = _json(fact_snapshot_row.validation_report, {})
    except Exception:
        fact_report = {}
    fact_coverage = fact_report.get("fact_coverage") if isinstance(fact_report, dict) else None
    if isinstance(fact_coverage, dict) and str(fact_coverage.get("status") or "").startswith("FACT_COVERAGE_") and fact_coverage.get("status") != "FACT_COVERAGE_SUFFICIENT":
        raise ScriptIRAuthorityError("FACT_SNAPSHOT_COVERAGE_INSUFFICIENT", "Bound FactSnapshot is not coverage-qualified.")
    envelope = build_authority_envelope(book_id=script_row.book_id, episode=script_row.episode, script_ir_payload=payload, source_package_id=source_package_id, source_version_id=source_version_id, immutable_source_raw_hash=immutable_source_raw_hash, source_evidence_index=source_evidence_index, fact_snapshot={"id": fact_snapshot_row.id, "revision": fact_snapshot_row.revision, "payload_hash": fact_snapshot_row.payload_hash}, contract=contract, requirement_set=requirement_set, coverage_result=coverage, authority_revision=authority_revision or int(getattr(draft_row, "revision", 1) or 1))
    envelope["source_anchor_bindings"] = copy.deepcopy(anchor_check["bindings"])
    envelope["envelope_fingerprint"] = _envelope_fingerprint(envelope)
    draft_row.status = "production_qualified"
    draft_row.validation_status = "qualified"
    draft_row.payload_hash = script_ir_hash(payload)
    draft_row.schema_version = str(payload.get("schema_version") or "script_ir_v1")
    draft_row.qualification_state = "PRODUCTION_QUALIFIED"
    draft_row.stale_status = "FRESH"
    draft_row.stale_reasons = "[]"
    draft_row.authority_envelope_json = json.dumps(envelope, ensure_ascii=False, sort_keys=True)
    draft_row.updated_at = datetime.now()
    previous = session.query(type(draft_row)).filter_by(book_id=script_row.book_id, episode=script_row.episode, status="production_qualified").filter(type(draft_row).id != draft_row.id).order_by(type(draft_row).revision.desc(), type(draft_row).id.desc()).all()
    for row in previous:
        row.status = "superseded"
        row.stale_status = "STALE"
        row.stale_reasons = json.dumps(["SUPERSEDED_BY_NEW_AUTHORITY"], ensure_ascii=False)
    script_row.current_script_ir_version_id = draft_row.id
    script_row.quality_status = "production_qualified"
    script_row.workflow_profile = "production"
    script_row.production_status = "blocked"
    session.commit()
    session.refresh(draft_row)
    return {"status": "SCRIPT_IR_AUTHORITY_ACTIVATED", "script_ir_version_id": draft_row.id, "revision": draft_row.revision, "qualification_state": draft_row.qualification_state, "authority_envelope": envelope, "downstream_requirement_backlog": "preserved", "provider_calls": 0, "production_writes": 1}


__all__ = ["AUTHORITY_ENVELOPE_SCHEMA_VERSION", "AUTHORITY_POLICY_VERSION", "QUALIFICATION_STATES", "STALE_STATUSES", "ScriptIRAuthorityError", "build_authority_envelope", "validate_source_anchor_bindings", "validate_source_evidence_binding", "validate_authority_envelope", "activate_script_ir"]
