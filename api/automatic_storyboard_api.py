"""Automatic storyboard runtime API.

Generation is deliberately provider free: only the deterministic mock adapter
is available here.  It persists reviewable storyboard drafts; compilation is
the only operation that materializes blocked ShotPlan rows.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from core.automatic_storyboard import (
    StoryboardCompileError,
    compile_storyboard,
    get_storyboard,
    persist_storyboard,
    rollback_storyboard,
    storyboard_from_reasoning,
)
from core.director_llm_adapter import (
    DirectorContextBuilder,
    MockDirectorLLMAdapter,
    add_adapter_lineage,
    content_hash,
    validate_llm_reasoning_output,
)
from core.director_reasoning import get_reasoning, persist_reasoning
from models import EpisodeOutline, ScriptIRVersion, Session


router = APIRouter(tags=["automatic-storyboard-runtime"])


class StoryboardGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    provider: str = "mock"
    episode_context: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("episode_context", "episodeContext"))
    script_ir: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("script_ir", "scriptIr"))
    scene_context: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("scene_context", "sceneContext"))
    characters: list[dict[str, Any]] = Field(default_factory=list)
    scenes: list[dict[str, Any]] = Field(default_factory=list)
    visual_styles: list[dict[str, Any]] = Field(default_factory=list, validation_alias=AliasChoices("visual_styles", "visualStyles"))
    existing_shots: list[dict[str, Any]] = Field(default_factory=list, validation_alias=AliasChoices("existing_shots", "existingShots"))
    source_fact_snapshot_hash: str = Field(default="", validation_alias=AliasChoices("source_fact_snapshot_hash", "sourceFactSnapshotHash"))
    mock_response: Any | None = Field(default=None, validation_alias=AliasChoices("mock_response", "mockResponse"))


class StoryboardCompileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    version: int | None = None
    episode_context: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("episode_context", "episodeContext"))
    script_ir: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("script_ir", "scriptIr"))
    scene_context: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("scene_context", "sceneContext"))
    characters: list[dict[str, Any]] = Field(default_factory=list)
    scenes: list[dict[str, Any]] = Field(default_factory=list)
    visual_styles: list[dict[str, Any]] = Field(default_factory=list, validation_alias=AliasChoices("visual_styles", "visualStyles"))
    existing_shots: list[dict[str, Any]] = Field(default_factory=list, validation_alias=AliasChoices("existing_shots", "existingShots"))
    book_id: int = Field(default=0, validation_alias=AliasChoices("book_id", "bookId"))
    episode_number: int = Field(default=0, validation_alias=AliasChoices("episode_number", "episodeNumber"))


def _decode(value: Any, fallback: Any) -> Any:
    import json
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback
    return parsed if parsed is not None else fallback


def _load_script_context(session: Any, episode_id: str) -> tuple[dict[str, Any], int | None, int, int]:
    ir = None
    numeric = 0
    try:
        numeric = int(episode_id)
        ir = session.query(ScriptIRVersion).filter_by(id=numeric).one_or_none()
        if ir is None:
            ir = session.query(ScriptIRVersion).filter_by(episode=numeric).order_by(ScriptIRVersion.revision.desc()).first()
    except (TypeError, ValueError):
        pass
    if ir is not None:
        payload = _decode(ir.payload_json, {})
        return payload if isinstance(payload, dict) else {}, ir.id, int(getattr(ir, "book_id", 0) or 0), int(getattr(ir, "episode", 0) or 0)
    outline = None
    try:
        outline = session.query(EpisodeOutline).filter_by(id=int(episode_id)).one_or_none()
    except (TypeError, ValueError):
        pass
    if outline is not None:
        scenes = _decode(outline.scenes, [])
        return {"episode_id": str(episode_id), "episode": outline.episode, "scenes": scenes if isinstance(scenes, list) else []}, None, int(outline.book_id or 0), int(outline.episode or 0)
    return {"episode_id": str(episode_id), "scenes": []}, None, 0, numeric


def _contexts(session: Any, episode_id: str, req: StoryboardGenerateRequest | StoryboardCompileRequest) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], int, int]:
    persisted, _ir_id, book_id, episode_number = _load_script_context(session, episode_id)
    script_ir = req.script_ir or persisted
    episode_context = {"episode_id": str(episode_id), "book_id": book_id, "episode": episode_number, **persisted, **req.episode_context}
    scenes = req.scenes or (script_ir.get("scenes") if isinstance(script_ir.get("scenes"), list) else [])
    scene_context = {"scenes": scenes, **req.scene_context}
    if req.characters:
        episode_context["characters"] = req.characters
    elif isinstance(script_ir.get("characters"), list):
        episode_context["characters"] = script_ir["characters"]
    if req.visual_styles:
        episode_context["visual_styles"] = req.visual_styles
    elif isinstance(script_ir.get("visual_styles"), list):
        episode_context["visual_styles"] = script_ir["visual_styles"]
        scene_context.setdefault("visual_styles", script_ir["visual_styles"])
    req_book_id = getattr(req, "book_id", 0)
    req_episode_number = getattr(req, "episode_number", 0)
    return episode_context, script_ir, scene_context, int(req_book_id or book_id), int(req_episode_number or episode_number)


@router.post("/episodes/{episode_id}/storyboard/generate", status_code=201)
def generate_storyboard(episode_id: str, req: StoryboardGenerateRequest):
    if str(req.provider or "mock").strip().lower() != "mock":
        raise HTTPException(status_code=409, detail={"code": "AUTOMATIC_STORYBOARD_PROVIDER_DISABLED", "message": "Only the provider-free mock adapter is enabled."})
    with Session() as session:
        episode_context, script_ir, scene_context, _book_id, _episode_number = _contexts(session, episode_id, req)
        existing = get_reasoning(session, str(episode_id))
        reasoning_created = False
        adapter_calls = 0
        if existing is None:
            context = DirectorContextBuilder().build(
                episode=episode_context,
                script_ir=script_ir,
                characters=req.characters or None,
                scenes=scene_context.get("scenes") or None,
                visual_styles=req.visual_styles or None,
                existing_shots=req.existing_shots or None,
            )
            adapter = MockDirectorLLMAdapter(req.mock_response)
            raw = adapter.generate_reasoning(context)
            validated = validate_llm_reasoning_output(raw, context)
            validated = add_adapter_lineage(validated, context=context, adapter=adapter)
            validated["episode_id"] = str(episode_id)
            validated["lineage"]["source_fact_snapshot_hash"] = req.source_fact_snapshot_hash or context.source_hashes.get("source_fact", "")
            existing = persist_reasoning(session, validated, source_fact_snapshot_hash=req.source_fact_snapshot_hash or context.source_hashes.get("source_fact", ""))
            reasoning_created = True
            adapter_calls = int(adapter.provider_calls)
        payload = storyboard_from_reasoning(existing, context={"episode_id": str(episode_id), "scenes": scene_context.get("scenes", []), "existing_shots": req.existing_shots, "episode": episode_context.get("episode")}, director_reasoning_id=existing.get("id"), director_reasoning_version=existing.get("version"))
        result = persist_storyboard(session, payload)
        session.commit()
        return {"storyboard": result, "reasoning": existing, "status": "REVIEW_REQUIRED", "provider": "mock", "provider_calls": adapter_calls, "reasoning_created": reasoning_created, "direct_database_write": False, "source_fact_mutated": False, "script_ir_mutated": False, "human_review_required": True, "media_generation": False, "payload_hash": content_hash(result)}


@router.get("/episodes/{episode_id}/storyboard")
def read_storyboard(episode_id: str, version: int | None = None):
    with Session() as session:
        result = get_storyboard(session, str(episode_id), version)
        if result is None:
            raise HTTPException(status_code=404, detail={"code": "STORYBOARD_NOT_FOUND", "episode_id": str(episode_id), "version": version})
        return {"storyboard": result, "status": result["status"], "human_review_required": True}


@router.post("/episodes/{episode_id}/storyboard/compile", status_code=201)
def compile_storyboard_route(episode_id: str, req: StoryboardCompileRequest):
    with Session() as session:
        row_payload = get_storyboard(session, str(episode_id), req.version)
        if row_payload is None:
            raise HTTPException(status_code=404, detail={"code": "STORYBOARD_NOT_FOUND", "episode_id": str(episode_id), "version": req.version})
        from models import StoryboardPlan
        row = session.query(StoryboardPlan).filter_by(id=int(row_payload["id"])).one()
        episode_context, script_ir, scene_context, book_id, episode_number = _contexts(session, episode_id, req)
        try:
            result = compile_storyboard(session, row, episode_context=episode_context, script_ir=script_ir, scene_context=scene_context, book_id=book_id, episode_number=episode_number)
            session.commit()
            return result
        except StoryboardCompileError as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail=exc.to_dict()) from exc
        except Exception as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail={"code": "AUTOMATIC_STORYBOARD_COMPILE_FAILED", "message": str(exc)}) from exc


@router.post("/episodes/{episode_id}/storyboard/{version}/rollback")
def rollback_storyboard_route(episode_id: str, version: int):
    with Session() as session:
        try:
            result = rollback_storyboard(session, str(episode_id), version)
            session.commit()
            return result
        except StoryboardCompileError as exc:
            session.rollback()
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc


__all__ = ["router"]
