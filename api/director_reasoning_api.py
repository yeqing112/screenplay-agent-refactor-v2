"""AI Director Reasoning IR API with fail-closed ShotPlan compilation."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from core.director_reasoning import (
    DirectorReasoningCompileError,
    compile_reasoning,
    director_reason,
    get_reasoning,
    persist_reasoning,
    rollback_reasoning,
)
from models import DirectorReasoning, EpisodeOutline, ScriptIRVersion, Session


router = APIRouter(tags=["ai-director-reasoning-runtime"])


class DirectorReasoningRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    episode_context: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("episode_context", "episodeContext"))
    script_ir: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("script_ir", "scriptIr"))
    scene_context: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("scene_context", "sceneContext"))
    created_by: str = Field(default="director-reasoning-runtime", validation_alias=AliasChoices("created_by", "createdBy"))
    source_fact_snapshot_hash: str = Field(default="", validation_alias=AliasChoices("source_fact_snapshot_hash", "sourceFactSnapshotHash"))
    persist: bool = True


class DirectorReasoningCompileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    version: int | None = None
    episode_context: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("episode_context", "episodeContext"))
    script_ir: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("script_ir", "scriptIr"))
    scene_context: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("scene_context", "sceneContext"))
    book_id: int = Field(default=0, validation_alias=AliasChoices("book_id", "bookId"))
    episode_number: int = Field(default=0, validation_alias=AliasChoices("episode_number", "episodeNumber"))


def _decode(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback
    return parsed if parsed is not None else fallback


def _load_script_context(session: Any, episode_id: str) -> tuple[dict[str, Any], int | None, int, int]:
    ir = None
    try:
        numeric = int(episode_id)
        ir = session.query(ScriptIRVersion).filter_by(id=numeric).one_or_none()
        if ir is None:
            ir = session.query(ScriptIRVersion).filter_by(episode=numeric).order_by(ScriptIRVersion.revision.desc()).first()
    except (TypeError, ValueError):
        numeric = 0
    if ir is not None:
        payload = _decode(ir.payload_json, {})
        return (payload if isinstance(payload, dict) else {}), ir.id, int(getattr(ir, "book_id", 0) or 0), int(getattr(ir, "episode", 0) or 0)
    outline = None
    try:
        outline = session.query(EpisodeOutline).filter_by(id=int(episode_id)).one_or_none()
    except (TypeError, ValueError):
        pass
    if outline is not None:
        scenes = _decode(outline.scenes, [])
        return {"episode_id": str(episode_id), "episode": outline.episode, "scenes": scenes if isinstance(scenes, list) else []}, None, int(outline.book_id or 0), int(outline.episode or 0)
    return {"episode_id": str(episode_id), "scenes": []}, None, 0, numeric if isinstance(numeric, int) else 0


@router.post("/episodes/{episode_id}/director-reasoning", status_code=201)
def create_director_reasoning(episode_id: str, req: DirectorReasoningRequest):
    with Session() as session:
        persisted_script, ir_id, book_id, episode_number = _load_script_context(session, episode_id)
        script_ir = req.script_ir or persisted_script
        episode_context = {"episode_id": str(episode_id), "book_id": book_id, "episode": episode_number, **persisted_script, **req.episode_context}
        payload = director_reason(episode_context, script_ir, req.scene_context)
        payload["episode_id"] = str(episode_id)
        if not req.persist:
            return {"reasoning": payload, "persisted": False, "llm_called": False, "status": "DRAFT"}
        try:
            result = persist_reasoning(session, payload, source_fact_snapshot_hash=req.source_fact_snapshot_hash)
            session.commit()
            return {"reasoning": result, "persisted": True, "llm_called": False, "status": result["status"], "source_script_ir_version_id": ir_id}
        except Exception as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_REASONING_PERSIST_FAILED", "message": str(exc)}) from exc


@router.get("/episodes/{episode_id}/director-reasoning")
def read_director_reasoning(episode_id: str, version: int | None = None):
    with Session() as session:
        result = get_reasoning(session, episode_id, version)
        if result is None:
            raise HTTPException(status_code=404, detail={"code": "DIRECTOR_REASONING_NOT_FOUND", "episode_id": str(episode_id), "version": version})
        return {"reasoning": result, "llm_called": False}


@router.post("/episodes/{episode_id}/director-reasoning/compile", status_code=201)
def compile_director_reasoning(episode_id: str, req: DirectorReasoningCompileRequest):
    with Session() as session:
        row = session.query(DirectorReasoning).filter_by(episode_id=str(episode_id), version=req.version).one_or_none() if req.version is not None else session.query(DirectorReasoning).filter_by(episode_id=str(episode_id)).order_by(DirectorReasoning.version.desc()).first()
        if row is None:
            raise HTTPException(status_code=404, detail={"code": "DIRECTOR_REASONING_NOT_FOUND", "episode_id": str(episode_id), "version": req.version})
        persisted_script, _ir_id, default_book_id, default_episode_number = _load_script_context(session, episode_id)
        script_ir = req.script_ir or persisted_script
        episode_context = {"episode_id": str(episode_id), "book_id": default_book_id, "episode": default_episode_number, **persisted_script, **req.episode_context}
        try:
            result = compile_reasoning(session, row, episode_context=episode_context, script_ir=script_ir, scene_context=req.scene_context, book_id=req.book_id or default_book_id, episode_number=req.episode_number or default_episode_number)
            session.commit()
            return result
        except DirectorReasoningCompileError as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail=exc.to_dict()) from exc
        except Exception as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_REASONING_COMPILE_FAILED", "message": str(exc)}) from exc


@router.post("/episodes/{episode_id}/director-reasoning/{version}/rollback")
def rollback_director_reasoning(episode_id: str, version: int):
    with Session() as session:
        try:
            result = rollback_reasoning(session, episode_id, version)
            session.commit()
            return result
        except DirectorReasoningCompileError as exc:
            session.rollback()
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc


__all__ = ["router"]
