"""Deterministic ScriptIR build/confirm API."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, Field

from core.script_ir import build_script_ir, legacy_markdown_to_script_ir, script_ir_hash, validate_script_ir
from core.script_renderer import render_script_markdown
from models import Script, ScriptIRVersion, Session

router = APIRouter(prefix="/api/books", tags=["script-ir"])


class ScriptIRBuildRequest(BaseModel):
    source_outline_revision: str = Field(default="", validation_alias=AliasChoices("source_outline_revision", "sourceOutlineRevision"))
    source_fact_snapshot_id: str = Field(default="", validation_alias=AliasChoices("source_fact_snapshot_id", "sourceFactSnapshotId"))
    persist: bool = False


class ScriptIRConfirmRequest(BaseModel):
    version_id: int = Field(validation_alias=AliasChoices("version_id", "versionId"))
    confirmed: bool = False
    payload: dict[str, Any] | None = None


def _content_hash(content: str) -> str:
    return hashlib.sha256(str(content or "").encode("utf-8")).hexdigest()


def _payload(row: ScriptIRVersion) -> dict[str, Any]:
    try:
        parsed = json.loads(row.payload_json or "{}")
    except (TypeError, ValueError):
        parsed = {}
    try:
        report = json.loads(row.validation_report or "{}")
    except (TypeError, ValueError):
        report = {}
    return {
        "id": row.id,
        "book_id": row.book_id,
        "episode": row.episode,
        "revision": row.revision,
        "status": row.status,
        "schema_version": row.schema_version,
        "source_outline_revision": row.source_outline_revision,
        "source_fact_snapshot_id": row.source_fact_snapshot_id,
        "source_fingerprint": row.source_fingerprint,
        "payload": parsed,
        "payload_hash": row.payload_hash,
        "validation_status": row.validation_status,
        "validation_report": report,
        "previous_revision_id": row.previous_revision_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _source_payload(row: Script, *, book_id: int, episode: int) -> tuple[dict[str, Any], bool]:
    raw = str(row.content or "")
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        parsed = None
    if isinstance(parsed, dict) and isinstance(parsed.get("scenes"), list):
        return build_script_ir(parsed, book_id=book_id, episode=episode), False
    return legacy_markdown_to_script_ir(raw, book_id=book_id, episode=episode), True


@router.post("/{book_id}/episodes/{episode}/script-ir/build")
def build_script_ir_version(book_id: int, episode: int, req: ScriptIRBuildRequest) -> dict[str, Any]:
    with Session() as session:
        script = session.query(Script).filter_by(book_id=book_id, episode=episode).order_by(Script.id.desc()).first()
        if not script:
            raise HTTPException(status_code=404, detail="No script found for this episode.")
        ir, legacy = _source_payload(script, book_id=book_id, episode=episode)
        report = validate_script_ir(ir)
        if legacy:
            report = {**report, "status": "needs_review", "warnings": [*report.get("warnings", []), {"code": "LEGACY_RECONSTRUCTION", "message": "该 ScriptIR 由旧 Markdown 重建，需人工确认。"}]}
        source_fingerprint = _content_hash(script.content or "")
        persisted_id = None
        if req.persist:
            existing = session.query(ScriptIRVersion).filter_by(book_id=book_id, episode=episode, source_fingerprint=source_fingerprint, payload_hash=script_ir_hash(ir)).order_by(ScriptIRVersion.id.desc()).first()
            if existing:
                persisted_id = existing.id
                version = existing
            else:
                previous = session.query(ScriptIRVersion).filter_by(book_id=book_id, episode=episode).order_by(ScriptIRVersion.revision.desc(), ScriptIRVersion.id.desc()).first()
                version = ScriptIRVersion(
                    book_id=book_id, episode=episode, revision=(previous.revision + 1 if previous else 1), status="draft",
                    schema_version="script_ir_v1", source_outline_revision=req.source_outline_revision.strip(), source_fact_snapshot_id=req.source_fact_snapshot_id.strip(),
                    source_fingerprint=source_fingerprint, payload_json=json.dumps(ir, ensure_ascii=False), payload_hash=script_ir_hash(ir),
                    validation_status=report["status"], validation_report=json.dumps(report, ensure_ascii=False), previous_revision_id=previous.id if previous else None,
                    created_at=datetime.now(), updated_at=datetime.now(),
                )
                session.add(version); session.commit(); session.refresh(version); persisted_id = version.id
        else:
            version = ScriptIRVersion(book_id=book_id, episode=episode, payload_json=json.dumps(ir, ensure_ascii=False), payload_hash=script_ir_hash(ir), source_fingerprint=source_fingerprint, validation_status=report["status"], validation_report=json.dumps(report, ensure_ascii=False))
        return {
            "mode": "deterministic_script_ir",
            "llm_called": False,
            "mutated": bool(persisted_id),
            "persisted_draft_id": persisted_id,
            "legacy_reconstruction": legacy,
            "validation": report,
            "rendered_markdown": render_script_markdown(ir),
            "version": _payload(version) if persisted_id else {"payload": ir, "payload_hash": version.payload_hash, "source_fingerprint": source_fingerprint, "validation_status": report["status"]},
        }


@router.get("/{book_id}/episodes/{episode}/script-ir")
def get_script_ir(book_id: int, episode: int) -> dict[str, Any]:
    with Session() as session:
        row = session.query(ScriptIRVersion).filter_by(book_id=book_id, episode=episode).order_by(ScriptIRVersion.revision.desc(), ScriptIRVersion.id.desc()).first()
        if not row:
            raise HTTPException(status_code=404, detail="No ScriptIR version found for this episode.")
        return _payload(row)


@router.post("/{book_id}/episodes/{episode}/script-ir/confirm")
def confirm_script_ir(book_id: int, episode: int, req: ScriptIRConfirmRequest) -> dict[str, Any]:
    if not req.confirmed:
        raise HTTPException(status_code=409, detail="ScriptIR confirmation requires confirmed=true.")
    with Session() as session:
        draft = session.query(ScriptIRVersion).filter_by(id=req.version_id, book_id=book_id, episode=episode).first()
        script = session.query(Script).filter_by(book_id=book_id, episode=episode).order_by(Script.id.desc()).first()
        if not draft or draft.status != "draft":
            raise HTTPException(status_code=409, detail="ScriptIR draft not found or already finalized.")
        if not script or _content_hash(script.content or "") != draft.source_fingerprint:
            draft.status = "superseded"; draft.updated_at = datetime.now(); session.commit()
            raise HTTPException(status_code=409, detail="Script source changed; ScriptIR draft is stale and must be regenerated.")
        try:
            candidate = build_script_ir(req.payload if req.payload is not None else json.loads(draft.payload_json), book_id=book_id, episode=episode, fact_snapshot_id=draft.source_fact_snapshot_id, source_outline_revision=draft.source_outline_revision)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=409, detail=f"ScriptIR candidate is invalid: {exc}") from exc
        report = validate_script_ir(candidate)
        if report["status"] != "qualified":
            raise HTTPException(status_code=409, detail={"code": "SCRIPT_IR_NOT_QUALIFIED", "validation": report})
        previous = session.query(ScriptIRVersion).filter_by(book_id=book_id, episode=episode, status="qualified").order_by(ScriptIRVersion.revision.desc(), ScriptIRVersion.id.desc()).first()
        if previous:
            previous.status = "superseded"; previous.updated_at = datetime.now()
        draft.status = "qualified"; draft.payload_json = json.dumps(candidate, ensure_ascii=False); draft.payload_hash = script_ir_hash(candidate); draft.validation_status = "qualified"; draft.validation_report = json.dumps(report, ensure_ascii=False); draft.updated_at = datetime.now(); session.commit(); session.refresh(draft)
        script.current_script_ir_version_id = draft.id; script.quality_status = "qualified"; script.workflow_profile = "production"; script.production_status = "blocked"; session.commit()
        return {"confirmed": True, "mutated": True, "script_ir": _payload(draft), "rendered_markdown": render_script_markdown(candidate), "production_status": "blocked"}

