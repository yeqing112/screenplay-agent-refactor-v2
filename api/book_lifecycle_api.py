"""Formal provider-free Book and source Script lifecycle endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from core.book_lifecycle import (
    BookLifecycleError,
    create_book,
    create_script,
    serialize_book,
)
from models import Session


router = APIRouter(prefix="/api/books", tags=["book-lifecycle"])


class BookCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    title: str = Field(min_length=1, max_length=255)


class ScriptCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    episode: int = Field(ge=1)
    content: str | dict[str, Any]
    genre: str = Field(default="short_drama", min_length=1, max_length=50)
    workflow_profile: str = Field(
        default="creative_draft",
        validation_alias=AliasChoices("workflowProfile", "workflow_profile"),
    )


def _raise_lifecycle(exc: BookLifecycleError) -> None:
    detail = {"code": exc.code, "message": exc.message, **exc.details}
    raise HTTPException(status_code=exc.status_code, detail=detail) from exc


@router.post("", status_code=status.HTTP_201_CREATED)
def create_book_endpoint(req: BookCreateRequest) -> dict[str, Any]:
    """Create an empty project without ingest, indexing, LLM, or Provider work."""

    with Session() as session:
        try:
            book = create_book(session, title=req.title)
            return serialize_book(session, book)
        except BookLifecycleError as exc:
            session.rollback()
            _raise_lifecycle(exc)


@router.post("/{book_id}/scripts", status_code=status.HTTP_201_CREATED)
def create_script_endpoint(book_id: int, req: ScriptCreateRequest) -> dict[str, Any]:
    """Persist one structured source Script; ScriptIR remains an explicit step."""

    with Session() as session:
        try:
            script = create_script(
                session,
                book_id=int(book_id),
                episode=req.episode,
                content=req.content,
                genre=req.genre,
                workflow_profile=req.workflow_profile,
            )
            return {
                "id": int(script.id),
                "book_id": int(script.book_id),
                "episode": int(script.episode),
                "genre": str(script.genre or ""),
                "status": str(script.status or "draft"),
                "workflow_profile": str(script.workflow_profile or "creative_draft"),
                "word_count": int(script.word_count or 0),
                "production_status": str(script.production_status or "blocked"),
                "created_at": script.created_at.isoformat() if script.created_at else None,
                "provider_calls": 0,
                "llm_calls": 0,
            }
        except BookLifecycleError as exc:
            session.rollback()
            _raise_lifecycle(exc)


__all__ = ["router", "BookCreateRequest", "ScriptCreateRequest"]
