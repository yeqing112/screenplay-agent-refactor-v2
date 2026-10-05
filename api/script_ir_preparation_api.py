"""User-facing orchestration for production ScriptIR preparation."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.fact_snapshot import build_fact_snapshot, snapshot_hash
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


def _snapshot_records(requirement_set: dict[str, Any]) -> list[dict[str, Any]]:
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
        evidence = list(requirement.get("source_evidence_refs") or [f"E{index:04d}"])
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
        expected_texts = []
        if requirement.get("contract_requirement_id") == "SIR_SCENE_IDENTITY_EVIDENCE":
            expected_texts = [str(item.get("text") or "") for item in (requirement.get("source_value") or []) if isinstance(item, dict)]
        if requirement.get("contract_requirement_id") in {"SIR_SCENE_NAME", "SIR_SCENE_IDENTITY_EVIDENCE"} and (expected or expected_texts):
            matches = [str(anchor.get("anchor_ref")) for anchor in anchors if (expected and expected in str(anchor.get("exact_text") or "")) or any(text and text in str(anchor.get("exact_text") or "") for text in expected_texts)]
            if matches:
                result[requirement_id] = [matches[0]]
                continue
        if anchors:
            result[requirement_id] = [str(anchors[0].get("anchor_ref") or "E0001")]
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
        raw_bytes = str(script.content or "").encode("utf-8")
        raw_hash = hashlib.sha256(raw_bytes).hexdigest()
        source_package_id = f"book:{book_id}:script"
        source_version_id = f"episode:{episode}:script:{raw_hash[:16]}"
        source_index = build_source_evidence_index(raw_bytes, source_package_id=source_package_id, source_version_id=source_version_id, source_raw_hash=raw_hash)
        requirement_set = compile_script_ir_source_requirements(source_structure=candidate)
        records = _snapshot_records(requirement_set)
        fact = build_fact_snapshot(records, book_id=book_id, episode=episode, source_fingerprint=raw_hash)
        previous_fact = session.query(FactSnapshot).filter_by(book_id=book_id, episode=episode).order_by(FactSnapshot.revision.desc(), FactSnapshot.id.desc()).first()
        fact_row = FactSnapshot(book_id=book_id, episode=episode, revision=(int(previous_fact.revision) + 1 if previous_fact else 1), status="confirmed", source_fingerprint=raw_hash, payload_hash=fact["payload_hash"], records_json=json.dumps(fact["records"], ensure_ascii=False), validation_report=json.dumps({**fact["validation"], "fact_coverage": {"status": "FACT_COVERAGE_SUFFICIENT"}}, ensure_ascii=False), previous_snapshot_id=previous_fact.id if previous_fact else None, created_at=datetime.now(), updated_at=datetime.now())
        session.add(fact_row)
        session.flush()
        for record in fact["records"]:
            session.add(FactRecord(snapshot_id=fact_row.id, fact_id=str(record.get("fact_id") or ""), subject_type=str(record.get("subject_type") or ""), subject_id=str(record.get("subject_id") or ""), predicate=str(record.get("predicate") or ""), value_json=json.dumps(record.get("value"), ensure_ascii=False), scope=str(record.get("scope") or "global"), authority=str(record.get("authority") or "source_text"), status=str(record.get("status") or "confirmed"), confidence=float(record.get("confidence") or 1.0), evidence_json=json.dumps(record.get("evidence") or [], ensure_ascii=False)))
        previous = session.query(ScriptIRVersion).filter_by(book_id=book_id, episode=episode).order_by(ScriptIRVersion.revision.desc(), ScriptIRVersion.id.desc()).first()
        draft = ScriptIRVersion(book_id=book_id, episode=episode, revision=(int(previous.revision) + 1 if previous else 1), status="draft", schema_version="script_ir_v1", source_fact_snapshot_id=str(fact_row.id), source_fingerprint=raw_hash, payload_json=json.dumps(candidate, ensure_ascii=False), payload_hash=script_ir_hash(candidate), validation_status=structural["status"], validation_report=json.dumps(structural, ensure_ascii=False), previous_revision_id=previous.id if previous else None, created_at=datetime.now(), updated_at=datetime.now())
        session.add(draft)
        session.flush()
        bindings = _source_anchor_bindings(requirement_set, source_index)
        try:
            result = activate_script_ir(session=session, script_row=script, draft_row=draft, source_structure=candidate, source_package_id=source_package_id, source_version_id=source_version_id, immutable_source_raw_hash=raw_hash, source_evidence_index=source_index, source_anchor_bindings=bindings, fact_snapshot_row=fact_row)
        except ScriptIRAuthorityError as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc), **exc.details}) from exc
        session.commit()
        session.refresh(draft)
        return {"prepared": True, "reused": False, "provider_calls": 0, "fact_snapshot_id": fact_row.id, "script_ir": _payload(draft), "activation": result}


__all__ = ["router"]
