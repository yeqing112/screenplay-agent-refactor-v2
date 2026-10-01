"""AI Director Reasoning IR API with fail-closed ShotPlan compilation."""
from __future__ import annotations

import json
from datetime import datetime
import uuid
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
from core.director_llm_adapter import (
    DEFAULT_DIRECTOR_LLM_ADAPTERS,
    DirectorContextBuilder,
    DirectorLLMAdapterError,
    MockDirectorLLMAdapter,
    add_adapter_lineage,
    content_hash,
    validate_llm_reasoning_output,
)
from models import DirectorReasoning, DirectorReasoningGeneration, EpisodeOutline, ScriptIRVersion, Session


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


class DirectorReasoningGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    provider: str = "mock"
    episode_context: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("episode_context", "episodeContext"))
    script_ir: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("script_ir", "scriptIr"))
    characters: list[dict[str, Any]] = Field(default_factory=list)
    scenes: list[dict[str, Any]] = Field(default_factory=list)
    visual_styles: list[dict[str, Any]] = Field(default_factory=list, validation_alias=AliasChoices("visual_styles", "visualStyles"))
    existing_shots: list[dict[str, Any]] = Field(default_factory=list, validation_alias=AliasChoices("existing_shots", "existingShots"))
    source_fact_snapshot_hash: str = Field(default="", validation_alias=AliasChoices("source_fact_snapshot_hash", "sourceFactSnapshotHash"))
    mock_response: Any | None = Field(default=None, validation_alias=AliasChoices("mock_response", "mockResponse"))


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
        payload = payload if isinstance(payload, dict) else {}
        payload.update({"book_id": int(ir.book_id), "episode": int(ir.episode), "source_script_ir_version_id": int(ir.id), "source_script_ir_hash": str(ir.payload_hash or "")})
        return payload, ir.id, int(getattr(ir, "book_id", 0) or 0), int(getattr(ir, "episode", 0) or 0)
    outline = None
    try:
        outline = session.query(EpisodeOutline).filter_by(id=int(episode_id)).one_or_none()
    except (TypeError, ValueError):
        pass
    if outline is not None:
        scenes = _decode(outline.scenes, [])
        return {"episode_id": str(episode_id), "book_id": int(outline.book_id or 0), "episode": outline.episode, "scenes": scenes if isinstance(scenes, list) else []}, None, int(outline.book_id or 0), int(outline.episode or 0)
    return {"episode_id": str(episode_id), "scenes": []}, None, 0, numeric if isinstance(numeric, int) else 0


def _generation_payload(row: DirectorReasoningGeneration) -> dict[str, Any]:
    return {
        "id": row.id,
        "generation_id": row.generation_id,
        "episode_id": row.episode_id,
        "status": row.status,
        "provider": row.provider,
        "adapter_name": row.adapter_name,
        "context_hash": row.context_hash,
        "request_hash": row.request_hash,
        "response_hash": row.response_hash,
        "director_reasoning_id": row.director_reasoning_id,
        "director_reasoning_version": row.director_reasoning_version,
        "provider_calls": row.provider_calls,
        "source_fact_mutated": bool(row.source_fact_mutated),
        "script_ir_mutated": bool(row.script_ir_mutated),
        "human_review_required": bool(row.human_review_required),
        "error": _decode(row.error_json, {}),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


def _adapter_for_request(req: DirectorReasoningGenerateRequest):
    if req.mock_response is not None:
        return MockDirectorLLMAdapter(req.mock_response)
    if str(req.provider).strip().lower() == "mock":
        return MockDirectorLLMAdapter()
    return DEFAULT_DIRECTOR_LLM_ADAPTERS.resolve(req.provider)


def _mark_generation_failed(
    session: Any,
    *,
    generation_id: str,
    episode_id: str,
    provider: str,
    adapter_name: str,
    context_hash: str,
    request_hash: str,
    provider_calls: int,
    error: dict[str, Any],
) -> DirectorReasoningGeneration:
    generation = session.query(DirectorReasoningGeneration).filter_by(generation_id=generation_id).one_or_none()
    if generation is None:
        generation = DirectorReasoningGeneration(
            generation_id=generation_id,
            episode_id=episode_id,
            provider=provider,
            adapter_name=adapter_name,
            context_hash=context_hash,
            request_hash=request_hash,
            source_fact_mutated=False,
            script_ir_mutated=False,
            human_review_required=True,
        )
        session.add(generation)
    generation.status = "FAILED"
    generation.provider_calls = int(provider_calls or 0)
    generation.error_json = json.dumps(error, ensure_ascii=False)
    generation.updated_at = datetime.utcnow()
    generation.completed_at = generation.updated_at
    return generation


@router.post("/episodes/{episode_id}/director-reasoning", status_code=201)
def create_director_reasoning(episode_id: str, req: DirectorReasoningRequest):
    with Session() as session:
        persisted_script, ir_id, book_id, episode_number = _load_script_context(session, episode_id)
        script_ir = req.script_ir or persisted_script
        episode_context = {"episode_id": str(episode_id), **persisted_script, **req.episode_context}
        if book_id:
            episode_context["book_id"] = book_id
        else:
            episode_context.pop("book_id", None)
        if episode_number:
            episode_context["episode"] = episode_number
        if ir_id:
            episode_context["source_script_ir_version_id"] = ir_id
            episode_context["source_script_ir_hash"] = str(persisted_script.get("source_script_ir_hash") or "")
        else:
            episode_context.pop("source_script_ir_version_id", None)
            episode_context.pop("source_script_ir_hash", None)
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


@router.post("/episodes/{episode_id}/director-reasoning/generate", status_code=201)
def generate_director_reasoning(episode_id: str, req: DirectorReasoningGenerateRequest):
    """Generate a reviewable IR draft; the adapter has no database access."""
    with Session() as session:
        persisted_script, ir_id, book_id, episode_number = _load_script_context(session, episode_id)
        script_ir = req.script_ir or persisted_script
        episode_context = {"episode_id": str(episode_id), **persisted_script, **req.episode_context}
        if book_id:
            episode_context["book_id"] = book_id
        else:
            episode_context.pop("book_id", None)
        if episode_number:
            episode_context["episode"] = episode_number
        if ir_id:
            episode_context["source_script_ir_version_id"] = ir_id
            episode_context["source_script_ir_hash"] = str(persisted_script.get("source_script_ir_hash") or "")
        else:
            episode_context.pop("source_script_ir_version_id", None)
            episode_context.pop("source_script_ir_hash", None)
        context = DirectorContextBuilder().build(
            episode=episode_context,
            script_ir=script_ir,
            characters=req.characters or None,
            scenes=req.scenes or None,
            visual_styles=req.visual_styles or None,
            existing_shots=req.existing_shots or None,
        )
        adapter = None
        generation_id = f"drg_{uuid.uuid4().hex}"
        provider = str(req.provider or "mock").strip().lower()
        request_hash = content_hash({"episode_id": str(episode_id), "provider": provider, "context_hash": context.context_hash})
        try:
            adapter = _adapter_for_request(req)
            generation = DirectorReasoningGeneration(
                generation_id=generation_id,
                episode_id=str(episode_id),
                status="RUNNING",
                provider=getattr(adapter, "provider", provider),
                adapter_name=getattr(adapter, "adapter_name", adapter.__class__.__name__),
                context_hash=context.context_hash,
                request_hash=request_hash,
                source_fact_mutated=False,
                script_ir_mutated=False,
                human_review_required=True,
            )
            session.add(generation)
            session.commit()

            raw = adapter.generate_reasoning(context)
            validated = validate_llm_reasoning_output(raw, context)
            payload = add_adapter_lineage(validated, context=context, adapter=adapter)
            payload["episode_id"] = str(episode_id)
            payload["lineage"]["source_fact_snapshot_hash"] = req.source_fact_snapshot_hash or context.source_hashes.get("source_fact", "")
            result = persist_reasoning(session, payload, source_fact_snapshot_hash=req.source_fact_snapshot_hash or context.source_hashes.get("source_fact", ""))
            generation = session.query(DirectorReasoningGeneration).filter_by(generation_id=generation_id).one()
            generation.status = "REVIEW_REQUIRED"
            generation.response_hash = content_hash(raw)
            generation.director_reasoning_id = result["id"]
            generation.director_reasoning_version = result["version"]
            generation.provider_calls = int(getattr(adapter, "provider_calls", 0) or 0)
            generation.updated_at = datetime.utcnow()
            generation.completed_at = generation.updated_at
            session.commit()
            return {
                "generation": _generation_payload(generation),
                "reasoning": result,
                "status": "REVIEW_REQUIRED",
                "provider": generation.provider,
                "provider_calls": generation.provider_calls,
                "direct_database_write": False,
                "source_fact_mutated": False,
                "script_ir_mutated": False,
                "human_review_required": True,
            }
        except DirectorLLMAdapterError as exc:
            session.rollback()
            generation = _mark_generation_failed(
                session,
                generation_id=generation_id,
                episode_id=str(episode_id),
                provider=getattr(adapter, "provider", provider) if adapter else provider,
                adapter_name=getattr(adapter, "adapter_name", "") if adapter else "",
                context_hash=context.context_hash,
                request_hash=request_hash,
                provider_calls=int(getattr(adapter, "provider_calls", exc.provider_calls) or 0) if adapter else exc.provider_calls,
                error=exc.to_dict(),
            )
            session.commit()
            raise HTTPException(status_code=409, detail=exc.to_dict()) from exc
        except Exception as exc:
            session.rollback()
            error = {"code": "DIRECTOR_LLM_GENERATION_FAILED", "message": str(exc)}
            generation = _mark_generation_failed(
                session,
                generation_id=generation_id,
                episode_id=str(episode_id),
                provider=getattr(adapter, "provider", provider) if adapter else provider,
                adapter_name=getattr(adapter, "adapter_name", "") if adapter else "",
                context_hash=context.context_hash,
                request_hash=request_hash,
                provider_calls=int(getattr(adapter, "provider_calls", 0) or 0) if adapter else 0,
                error=error,
            )
            session.commit()
            raise HTTPException(status_code=409, detail=error) from exc


@router.get("/episodes/{episode_id}/director-reasoning/generation-status")
def read_director_reasoning_generation_status(episode_id: str):
    with Session() as session:
        row = session.query(DirectorReasoningGeneration).filter_by(episode_id=str(episode_id)).order_by(DirectorReasoningGeneration.id.desc()).first()
        if row is None:
            raise HTTPException(status_code=404, detail={"code": "DIRECTOR_LLM_GENERATION_NOT_FOUND", "episode_id": str(episode_id)})
        return {"generation": _generation_payload(row), "status": row.status, "human_review_required": True}


@router.post("/episodes/{episode_id}/director-reasoning/compile", status_code=201)
def compile_director_reasoning(episode_id: str, req: DirectorReasoningCompileRequest):
    with Session() as session:
        row = session.query(DirectorReasoning).filter_by(episode_id=str(episode_id), version=req.version).one_or_none() if req.version is not None else session.query(DirectorReasoning).filter_by(episode_id=str(episode_id)).order_by(DirectorReasoning.version.desc()).first()
        if row is None:
            raise HTTPException(status_code=404, detail={"code": "DIRECTOR_REASONING_NOT_FOUND", "episode_id": str(episode_id), "version": req.version})
        persisted_script, ir_id, default_book_id, default_episode_number = _load_script_context(session, episode_id)
        script_ir = req.script_ir or persisted_script
        episode_context = {"episode_id": str(episode_id), **persisted_script, **req.episode_context}
        if default_book_id:
            episode_context["book_id"] = default_book_id
        if default_episode_number:
            episode_context["episode"] = default_episode_number
        if ir_id:
            episode_context["source_script_ir_version_id"] = ir_id
            episode_context["source_script_ir_hash"] = str(persisted_script.get("source_script_ir_hash") or "")
        try:
            result = compile_reasoning(session, row, episode_context=episode_context, script_ir=script_ir, scene_context=req.scene_context, book_id=default_book_id or req.book_id, episode_number=default_episode_number or req.episode_number)
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
