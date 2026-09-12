"""Read-only build and explicit confirmation API for FactSnapshot."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, Field

from core.fact_snapshot import build_fact_snapshot
from models import FactRecord, FactSnapshot, Script, Session

router = APIRouter(prefix="/api/books", tags=["fact-snapshot"])


class FactSnapshotBuildRequest(BaseModel):
    records: list[dict[str, Any]] = Field(default_factory=list)
    source_fingerprint: str = Field(default="", validation_alias=AliasChoices("source_fingerprint", "sourceFingerprint"))
    persist: bool = False


class FactSnapshotConfirmRequest(BaseModel):
    snapshot_id: int = Field(validation_alias=AliasChoices("snapshot_id", "snapshotId"))
    confirmed: bool = False


def _source_fingerprint(script: Script | None) -> str:
    return hashlib.sha256(str((script.content if script else "") or "").encode("utf-8")).hexdigest()


def _payload(row: FactSnapshot) -> dict[str, Any]:
    try:
        records = json.loads(row.records_json or "[]")
    except (TypeError, ValueError):
        records = []
    try:
        report = json.loads(row.validation_report or "{}")
    except (TypeError, ValueError):
        report = {}
    return {"id": row.id, "book_id": row.book_id, "episode": row.episode, "revision": row.revision, "status": row.status, "source_fingerprint": row.source_fingerprint, "payload_hash": row.payload_hash, "records": records, "validation": report, "previous_snapshot_id": row.previous_snapshot_id, "created_at": row.created_at.isoformat() if row.created_at else None, "updated_at": row.updated_at.isoformat() if row.updated_at else None}


@router.post("/{book_id}/episodes/{episode}/fact-snapshots/build")
def build_fact_snapshot_endpoint(book_id: int, episode: int, req: FactSnapshotBuildRequest) -> dict[str, Any]:
    with Session() as session:
        script = session.query(Script).filter_by(book_id=book_id, episode=episode).order_by(Script.id.desc()).first()
        if not script:
            raise HTTPException(status_code=404, detail="No script found for this episode.")
        snapshot = build_fact_snapshot(req.records, book_id=book_id, episode=episode, source_fingerprint=req.source_fingerprint.strip() or _source_fingerprint(script))
        persisted_id = None
        row = None
        if req.persist:
            previous = session.query(FactSnapshot).filter_by(book_id=book_id, episode=episode).order_by(FactSnapshot.revision.desc(), FactSnapshot.id.desc()).first()
            row = FactSnapshot(book_id=book_id, episode=episode, revision=(previous.revision + 1 if previous else 1), status="draft", source_fingerprint=snapshot["source_fingerprint"], payload_hash=snapshot["payload_hash"], records_json=json.dumps(snapshot["records"], ensure_ascii=False), validation_report=json.dumps(snapshot["validation"], ensure_ascii=False), previous_snapshot_id=previous.id if previous else None, created_at=datetime.now(), updated_at=datetime.now())
            session.add(row); session.commit(); session.refresh(row); persisted_id = row.id
        return {"mode": "deterministic_fact_snapshot", "llm_called": False, "mutated": bool(persisted_id), "persisted_draft_id": persisted_id, "snapshot": _payload(row) if row else snapshot}


@router.get("/{book_id}/episodes/{episode}/fact-snapshots")
def list_fact_snapshots(book_id: int, episode: int) -> dict[str, Any]:
    with Session() as session:
        rows = session.query(FactSnapshot).filter_by(book_id=book_id, episode=episode).order_by(FactSnapshot.revision.desc(), FactSnapshot.id.desc()).all()
    return {"items": [_payload(row) for row in rows]}


@router.post("/{book_id}/episodes/{episode}/fact-snapshots/confirm")
def confirm_fact_snapshot(book_id: int, episode: int, req: FactSnapshotConfirmRequest) -> dict[str, Any]:
    if not req.confirmed:
        raise HTTPException(status_code=409, detail="FactSnapshot confirmation requires confirmed=true.")
    with Session() as session:
        row = session.query(FactSnapshot).filter_by(id=req.snapshot_id, book_id=book_id, episode=episode).first()
        script = session.query(Script).filter_by(book_id=book_id, episode=episode).order_by(Script.id.desc()).first()
        if not row or row.status != "draft":
            raise HTTPException(status_code=409, detail="FactSnapshot draft not found or already finalized.")
        if not script or _source_fingerprint(script) != row.source_fingerprint:
            row.status = "superseded"; row.updated_at = datetime.now(); session.commit()
            raise HTTPException(status_code=409, detail="Fact evidence changed; snapshot is stale and must be regenerated.")
        report = json.loads(row.validation_report or "{}")
        if report.get("status") != "qualified":
            raise HTTPException(status_code=409, detail={"code": "FACT_SNAPSHOT_NOT_QUALIFIED", "validation": report})
        previous = session.query(FactSnapshot).filter_by(book_id=book_id, episode=episode, status="confirmed").order_by(FactSnapshot.revision.desc(), FactSnapshot.id.desc()).first()
        if previous:
            previous.status = "superseded"; previous.updated_at = datetime.now()
        row.status = "confirmed"; row.updated_at = datetime.now()
        records = json.loads(row.records_json or "[]")
        session.query(FactRecord).filter_by(snapshot_id=row.id).delete()
        for record in records:
            session.add(FactRecord(snapshot_id=row.id, fact_id=str(record.get("fact_id") or ""), subject_type=str(record.get("subject_type") or ""), subject_id=str(record.get("subject_id") or ""), predicate=str(record.get("predicate") or ""), value_json=json.dumps(record.get("value"), ensure_ascii=False), scope=str(record.get("scope") or "global"), authority=str(record.get("authority") or "derived_fact"), status=str(record.get("status") or "proposed"), confidence=float(record.get("confidence") or 0.0), evidence_json=json.dumps(record.get("evidence") or [], ensure_ascii=False)))
        session.commit(); session.refresh(row)
        return {"confirmed": True, "mutated": True, "fact_snapshot": _payload(row)}

