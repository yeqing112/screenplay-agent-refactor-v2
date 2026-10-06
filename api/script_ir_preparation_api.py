"""User-facing orchestration for production ScriptIR preparation."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.fact_snapshot import build_fact_snapshot, snapshot_hash
from core.source_authority import SourceLineageContext, resolve_origin_source
from core.script_ir import validate_script_ir, script_ir_hash, legacy_markdown_to_script_ir
from core.script_ir_authority import ScriptIRAuthorityError, activate_script_ir
from core.script_ir_production_preparation import build_production_candidate
from core.script_ir_source_requirements import compile_script_ir_source_requirements
from core.source_evidence_index import build_source_evidence_index
from models import FactRecord, FactSnapshot, Script, ScriptIRVersion, Session

router = APIRouter(prefix="/api/books", tags=["script-ir-production-preparation"])


class PrepareProductionRequest(BaseModel):
    confirmed: bool = Field(default=False)


def _source_payload(script: Script) -> Any:
    try:
        parsed = json.loads(str(script.content or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        parsed = None
    if isinstance(parsed, dict):
        return parsed
    # Scriptwriter output is still stored as immutable Markdown screenplay
    # text.  Preparation must be able to derive a versioned ScriptIR candidate
    # from that legacy representation without rewriting the source row.
    return legacy_markdown_to_script_ir(str(script.content or ""), book_id=int(script.book_id), episode=int(script.episode))


def _snapshot_records(requirement_set: dict[str, Any], *, source_anchor_bindings: dict[str, list[str]] | None = None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, requirement in enumerate(requirement_set.get("requirements") or [], start=1):
        if not requirement.get("blocking"):
            continue
        value = requirement.get("expected_value")
        # Source-grounded V3 scene identity is a list of exact anchors.  The
        # semantic display name and unresolved location are never promoted to
        # source facts in FactSnapshot.
        if requirement.get("contract_requirement_id") == "SIR_SCENE_IDENTITY_EVIDENCE":
            value = requirement.get("source_value") or []
        bindings = source_anchor_bindings or {}
        evidence = [str(item) for item in (bindings.get(str(requirement.get("requirement_id") or "")) or []) if str(item).strip()]
        if requirement.get("blocking") and not evidence:
            raise ValueError("FACT_SOURCE_ANCHOR_REQUIRED")
        records.append({
            "fact_id": f"SOURCE_PREP_{index:04d}",
            "subject_type": requirement.get("subject_type") or "source",
            "subject_id": requirement.get("subject_id") or requirement.get("requirement_id"),
            "predicate": requirement.get("predicate") or "source_fact",
            "value": value,
            "scope": requirement.get("scope") or "episode",
            "authority": "source_text",
            "status": "confirmed",
            "confidence": 1.0,
            "evidence": evidence,
        })
    return records


def _source_anchor_bindings(requirement_set: dict[str, Any], source_index: dict[str, Any]) -> dict[str, list[str]]:
    """Bind each blocking requirement to a byte-accurate source block.

    A single first-anchor binding is unsafe for scene identity: a screenplay
    can contain a title block before its scene heading.  Resolve the anchor
    from the immutable evidence index while retaining the first anchor as the
    deterministic episode-level existence proof.
    """
    anchors = [row for row in (source_index.get("anchors") or []) if isinstance(row, dict)]
    result: dict[str, list[str]] = {}
    for requirement in requirement_set.get("requirements") or []:
        if not requirement.get("blocking"):
            continue
        requirement_id = str(requirement.get("requirement_id") or "")
        expected = str(requirement.get("expected_value") or "").strip()
        source_value = requirement.get("source_value")
        expected_texts = [str(item.get("text") or "") for item in source_value if isinstance(item, dict)] if isinstance(source_value, list) else ([str(source_value)] if isinstance(source_value, str) else [])
        if not expected_texts and isinstance(requirement.get("source_value"), str):
            expected_texts = [str(requirement.get("source_value"))]
        matches: list[str] = []
        for anchor in anchors:
            exact = str(anchor.get("exact_text") or "")
            if (expected and expected in exact) or any(text and text in exact for text in expected_texts):
                matches.append(str(anchor.get("anchor_ref")))
        if matches:
            result[requirement_id] = list(dict.fromkeys(matches))
        elif anchors and requirement.get("contract_requirement_id") == "SIR_SCENES_PRESENT":
            result[requirement_id] = [str(anchors[0].get("anchor_ref"))]
    return result


def _payload(row: ScriptIRVersion) -> dict[str, Any]:
    try:
        payload = json.loads(row.payload_json or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        payload = {}
    try:
        envelope = json.loads(row.authority_envelope_json or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        envelope = {}
    return {
        "id": row.id,
        "book_id": row.book_id,
        "episode": row.episode,
        "revision": row.revision,
        "status": row.status,
        "qualification_state": row.qualification_state,
        "payload_hash": row.payload_hash,
        "authority_envelope": envelope,
        "authority_profile": envelope.get("authority_profile", ""),
        "creative_readiness_state": envelope.get("creative_readiness_state", ""),
        "payload": payload,
    }


@router.post("/{book_id}/episodes/{episode}/script-ir/prepare-production")
def prepare_script_ir_production(book_id: int, episode: int, req: PrepareProductionRequest) -> dict[str, Any]:
    if not req.confirmed:
        raise HTTPException(status_code=409, detail={"code": "PRODUCTION_PREPARATION_CONFIRMATION_REQUIRED", "message": "请确认准备进入导演阶段。"})
    with Session() as session:
        script = session.query(Script).filter_by(book_id=book_id, episode=episode).order_by(Script.id.desc()).first()
        if not script:
            raise HTTPException(status_code=404, detail={"code": "SCRIPT_REQUIRED", "message": "请先生成本集剧本。"})
        existing = session.query(ScriptIRVersion).filter_by(book_id=book_id, episode=episode, status="production_qualified").order_by(ScriptIRVersion.revision.desc(), ScriptIRVersion.id.desc()).first()
        if existing:
            return {"prepared": True, "reused": True, "provider_calls": 0, "script_ir": _payload(existing)}

        source = _source_payload(script)
        candidate = build_production_candidate(source, book_id=book_id, episode=episode)
        structural = validate_script_ir(candidate)
        if structural.get("status") != "qualified":
            raise HTTPException(status_code=409, detail={"code": "SCRIPT_IR_NOT_QUALIFIED", "validation": structural})
        canonical_script_content_hash = hashlib.sha256(str(script.content or "").encode("utf-8")).hexdigest()
        lineage = None
        if str(source.get("source_grounded_schema_version") or source.get("schema_version") or "") == "source_grounded_script_payload_v3_1":
            lineage_data = source.get("source_lineage")
            if not isinstance(lineage_data, dict):
                raise HTTPException(status_code=409, detail={"code": "SOURCE_LINEAGE_REQUIRED", "message": "V3.1 source payload requires dual-source lineage."})
            try:
                lineage = SourceLineageContext.from_dict(lineage_data)
                origin = resolve_origin_source(session, lineage)
            except ValueError as exc:
                raise HTTPException(status_code=409, detail={"code": str(exc), "message": "Immutable origin source cannot be resolved."}) from exc
            raw_bytes = origin["raw_bytes"]
            raw_hash = origin["raw_sha256"]
            source_package_id = origin["source_package_id"]
            source_version_id = origin["source_version_id"]
        else:
            raw_bytes = str(script.content or "").encode("utf-8")
            raw_hash = hashlib.sha256(raw_bytes).hexdigest()
            source_package_id = f"book:{book_id}:script"
            source_version_id = f"episode:{episode}:script:{raw_hash[:16]}"
        source_index = build_source_evidence_index(raw_bytes, source_package_id=source_package_id, source_version_id=source_version_id, source_raw_hash=raw_hash)
        requirement_set = compile_script_ir_source_requirements(source_structure=candidate)
        bindings = _source_anchor_bindings(requirement_set, source_index)
        try:
            from core.script_ir_authority import validate_source_anchor_bindings
            binding_check = validate_source_anchor_bindings(requirement_set=requirement_set, source_evidence_index=source_index, bindings=bindings)
        except Exception as exc:
            raise HTTPException(status_code=409, detail={"code": "SOURCE_EVIDENCE_BINDING_REQUIRED", "message": str(exc)}) from exc
        if binding_check.get("status") != "PASS":
            raise HTTPException(status_code=409, detail={"code": "SOURCE_EVIDENCE_BINDING_REQUIRED", "details": binding_check})
        try:
            records = _snapshot_records(requirement_set, source_anchor_bindings=bindings)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail={"code": str(exc), "message": "FactSnapshot requires validated origin anchor bindings."}) from exc
        fact = build_fact_snapshot(records, book_id=book_id, episode=episode, source_fingerprint=raw_hash)
        previous_fact = session.query(FactSnapshot).filter_by(book_id=book_id, episode=episode).order_by(FactSnapshot.revision.desc(), FactSnapshot.id.desc()).first()
        fact_row = FactSnapshot(book_id=book_id, episode=episode, revision=(int(previous_fact.revision) + 1 if previous_fact else 1), status="confirmed", source_fingerprint=raw_hash, payload_hash=fact["payload_hash"], records_json=json.dumps(fact["records"], ensure_ascii=False), validation_report=json.dumps({**fact["validation"], "fact_coverage": {"status": "FACT_COVERAGE_SUFFICIENT"}}, ensure_ascii=False), previous_snapshot_id=previous_fact.id if previous_fact else None, created_at=datetime.now(), updated_at=datetime.now())
        session.add(fact_row)
        session.flush()
        for record in fact["records"]:
            session.add(FactRecord(snapshot_id=fact_row.id, fact_id=str(record.get("fact_id") or ""), subject_type=str(record.get("subject_type") or ""), subject_id=str(record.get("subject_id") or ""), predicate=str(record.get("predicate") or ""), value_json=json.dumps(record.get("value"), ensure_ascii=False), scope=str(record.get("scope") or "global"), authority=str(record.get("authority") or "source_text"), status=str(record.get("status") or "confirmed"), confidence=float(record.get("confidence") or 1.0), evidence_json=json.dumps(record.get("evidence") or [], ensure_ascii=False)))
        previous = session.query(ScriptIRVersion).filter_by(book_id=book_id, episode=episode).order_by(ScriptIRVersion.revision.desc(), ScriptIRVersion.id.desc()).first()
        draft = ScriptIRVersion(book_id=book_id, episode=episode, revision=(int(previous.revision) + 1 if previous else 1), status="draft", schema_version="script_ir_v1", source_fact_snapshot_id=str(fact_row.id), source_fingerprint=canonical_script_content_hash, payload_json=json.dumps(candidate, ensure_ascii=False, sort_keys=True), payload_hash=script_ir_hash(candidate), validation_status=structural["status"], validation_report=json.dumps(structural, ensure_ascii=False), previous_revision_id=previous.id if previous else None, created_at=datetime.now(), updated_at=datetime.now())
        session.add(draft)
        session.flush()
        try:
            result = activate_script_ir(session=session, script_row=script, draft_row=draft, source_structure=candidate, source_package_id=source_package_id, source_version_id=source_version_id, immutable_source_raw_hash=raw_hash, source_evidence_index=source_index, source_anchor_bindings=bindings, fact_snapshot_row=fact_row, origin_raw_bytes=raw_bytes, canonical_script_content_hash=canonical_script_content_hash, source_lineage=lineage)
        except ScriptIRAuthorityError as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc), **exc.details}) from exc
        session.commit()
        session.refresh(draft)
        return {"prepared": True, "reused": False, "provider_calls": 0, "fact_snapshot_id": fact_row.id, "script_ir": _payload(draft), "activation": result}


__all__ = ["router"]
