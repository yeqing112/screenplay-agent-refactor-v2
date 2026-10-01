"""AI Director runtime foundation API.

All POSTs create versioned drafts or human revisions.  The adapter is local
and deterministic; no provider, LLM, image generation, or video generation is
invoked by these routes.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from core.director_runtime import director_plan, get_director_plan, persist_director_plan, revise_shot
from models import EpisodeOutline, ScriptIRVersion, Session


router = APIRouter(tags=["ai-director-runtime"])


class DirectorPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    script_ir: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("script_ir", "scriptIr"))
    episode_context: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("episode_context", "episodeContext"))
    character_profiles: list[dict[str, Any]] = Field(default_factory=list, validation_alias=AliasChoices("character_profiles", "characterProfiles"))
    scene_profiles: list[dict[str, Any]] = Field(default_factory=list, validation_alias=AliasChoices("scene_profiles", "sceneProfiles"))
    created_by: str = Field(default="director-runtime", validation_alias=AliasChoices("created_by", "createdBy"))
    persist: bool = True


class DirectorReviseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    patch: dict[str, Any] = Field(default_factory=dict)
    created_by: str = Field(default="human-review", validation_alias=AliasChoices("created_by", "createdBy"))


def _decode(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback
    return parsed if parsed is not None else fallback


def _load_context(session: Any, episode_id: str) -> tuple[dict[str, Any], int | None]:
    ir = None
    try:
        numeric = int(episode_id)
        ir = session.query(ScriptIRVersion).filter_by(id=numeric).one_or_none()
        if ir is None:
            ir = session.query(ScriptIRVersion).filter_by(episode=numeric).order_by(ScriptIRVersion.revision.desc()).first()
    except (TypeError, ValueError):
        pass
    if ir is not None:
        payload = _decode(ir.payload_json, {})
        if not isinstance(payload, dict):
            payload = {}
        payload = {
            **payload,
            "book_id": int(ir.book_id),
            "episode": int(ir.episode),
            "source_script_ir_version_id": int(ir.id),
            "source_script_ir_hash": str(ir.payload_hash or ""),
        }
        return payload, ir.id
    outline = None
    try:
        outline = session.query(EpisodeOutline).filter_by(id=int(episode_id)).one_or_none()
    except (TypeError, ValueError):
        pass
    if outline is not None:
        return {"episode_id": str(episode_id), "book_id": int(outline.book_id), "episode": outline.episode, "title": outline.title, "scenes": _decode(outline.scenes, [])}, None
    return {"episode_id": str(episode_id), "scenes": []}, None


@router.post("/episodes/{episode_id}/director-plan", status_code=201)
def create_director_plan(episode_id: str, req: DirectorPlanRequest):
    with Session() as session:
        persisted_ir, ir_id = _load_context(session, episode_id)
        script_ir = req.script_ir or persisted_ir
        context = {"episode_id": str(episode_id), **persisted_ir, **req.episode_context}
        # Persisted ScriptIR identity is authoritative; caller context cannot
        # move a DirectorPlan to another Book.
        for key in ("book_id", "episode", "source_script_ir_version_id", "source_script_ir_hash"):
            if key in persisted_ir:
                context[key] = persisted_ir[key]
            else:
                context.pop(key, None)
        context["source_script_ir_hash"] = context.get("source_script_ir_hash") or (str(getattr(session.get(ScriptIRVersion, ir_id), "payload_hash", "")) if ir_id else "")
        payload = director_plan(script_ir, context, req.character_profiles, req.scene_profiles)
        payload["episode_id"] = str(episode_id)
        if not req.persist:
            return {"plan": payload, "persisted": False, "llm_called": False, "status": "DRAFT"}
        try:
            result = persist_director_plan(session, payload, created_by=req.created_by, source_script_ir_version_id=ir_id)
            session.commit()
            return {"plan": result, "persisted": True, "llm_called": False, "status": result["status"]}
        except Exception as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_PLAN_PERSIST_FAILED", "message": str(exc)}) from exc


@router.get("/episodes/{episode_id}/director-plan")
def read_director_plan(episode_id: str, version: int | None = None):
    with Session() as session:
        result = get_director_plan(session, episode_id, version)
        if result is None:
            raise HTTPException(status_code=404, detail={"code": "DIRECTOR_PLAN_NOT_FOUND", "episode_id": str(episode_id), "version": version})
        return {"plan": result, "llm_called": False}


@router.post("/shots/{shot_id}/director-revise", status_code=201)
def revise_director_shot(shot_id: str, req: DirectorReviseRequest):
    with Session() as session:
        try:
            result = revise_shot(session, shot_id, req.patch, created_by=req.created_by)
            session.commit()
            return {"plan": result, "revised_shot_id": str(shot_id), "llm_called": False, "human_review_required": True}
        except ValueError as exc:
            session.rollback()
            raise HTTPException(status_code=404 if "does not exist" in str(exc) else 422, detail={"code": "DIRECTOR_REVISE_INVALID", "message": str(exc)}) from exc


__all__ = ["router"]
