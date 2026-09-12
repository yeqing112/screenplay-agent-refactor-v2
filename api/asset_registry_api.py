"""ScriptIR → canonical asset registry synchronization."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, Field

from core.asset_registry_sync import sync_assets_from_script_ir
from models import Script, ScriptIRVersion, Session

router = APIRouter(prefix="/api/books", tags=["asset-registry"])


class AssetRegistrySyncRequest(BaseModel):
    source_fingerprint: str = Field(default="", validation_alias=AliasChoices("source_fingerprint", "sourceFingerprint"))
    confirmed: bool = False


@router.post("/{book_id}/episodes/{episode}/asset-registry/sync")
def sync_asset_registry(book_id: int, episode: int, req: AssetRegistrySyncRequest) -> dict:
    if not req.confirmed:
        raise HTTPException(status_code=409, detail="Asset registry sync requires confirmed=true.")
    with Session() as session:
        script = session.query(Script).filter_by(book_id=book_id, episode=episode).order_by(Script.id.desc()).first()
        if not script:
            raise HTTPException(status_code=404, detail="No script found for this episode.")
        version = None
        if script.current_script_ir_version_id:
            version = session.query(ScriptIRVersion).filter_by(id=script.current_script_ir_version_id, book_id=book_id, episode=episode, status="qualified").first()
        if version is None:
            version = session.query(ScriptIRVersion).filter_by(book_id=book_id, episode=episode, status="qualified").order_by(ScriptIRVersion.revision.desc(), ScriptIRVersion.id.desc()).first()
        if version is None:
            raise HTTPException(status_code=409, detail="Asset registry sync requires a qualified ScriptIR.")
        try:
            payload = json.loads(version.payload_json or "{}")
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=409, detail="Qualified ScriptIR payload is invalid.") from exc
        source = req.source_fingerprint.strip() or version.payload_hash
        result = sync_assets_from_script_ir(session, payload, book_id=book_id, episode=episode, source_fingerprint=source)
        session.commit()
        return {"mode": "deterministic_asset_registry_sync", "llm_called": False, "confirmed": True, **result}

