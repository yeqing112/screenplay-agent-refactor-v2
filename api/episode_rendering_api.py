"""Episode rendering plan and execution API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from core.episode_rendering import (
    EpisodeRenderingError,
    complete_episode_render_plan,
    create_episode_render_plan,
    get_episode_render_plan,
    render_episode,
    serialize_episode_render_plan,
)
from models import Session


router = APIRouter(prefix="/episodes", tags=["episode-rendering-runtime"])


class RenderItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    shot_id: int = Field(gt=0, validation_alias=AliasChoices("shot_id", "shotId"))
    order: int = Field(ge=0)
    dependency: list[int] = Field(default_factory=list)


class CreateEpisodeRenderPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    render_strategy: str = Field(default="SEQUENTIAL", validation_alias=AliasChoices("render_strategy", "renderStrategy"))
    items: list[RenderItemRequest] | None = None


class RenderEpisodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    model_profile_id: str = Field(default="shapi-image", validation_alias=AliasChoices("model_profile_id", "modelProfileId"))
    plan_id: int | None = Field(default=None, gt=0, validation_alias=AliasChoices("plan_id", "planId"))
    retry_failed: bool = Field(default=False, validation_alias=AliasChoices("retry_failed", "retryFailed"))
    max_retries: int = Field(default=1, ge=0, le=3, validation_alias=AliasChoices("max_retries", "maxRetries"))


class CompleteEpisodeRenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    plan_id: int | None = Field(default=None, gt=0, validation_alias=AliasChoices("plan_id", "planId"))
    reviewed: bool = False


def _raise(exc: EpisodeRenderingError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.to_dict()) from exc


@router.get("/{episode_id}/render-plan")
def get_render_plan(episode_id: int, plan_id: int | None = None):
    with Session() as session:
        try:
            return serialize_episode_render_plan(session, get_episode_render_plan(session, episode_id=episode_id, plan_id=plan_id))
        except EpisodeRenderingError as exc:
            _raise(exc)


@router.post("/{episode_id}/render-plan", status_code=201)
def create_render_plan(episode_id: int, req: CreateEpisodeRenderPlanRequest | None = None):
    request = req or CreateEpisodeRenderPlanRequest()
    with Session() as session:
        try:
            plan = create_episode_render_plan(
                session,
                episode_id=episode_id,
                render_strategy=request.render_strategy,
                items=[item.model_dump() for item in request.items] if request.items is not None else None,
            )
            session.commit()
            return serialize_episode_render_plan(session, plan)
        except EpisodeRenderingError as exc:
            session.rollback()
            _raise(exc)


@router.post("/{episode_id}/render")
def render(episode_id: int, req: RenderEpisodeRequest | None = None):
    request = req or RenderEpisodeRequest()
    with Session() as session:
        try:
            plan = render_episode(
                session,
                episode_id=episode_id,
                model_profile_id=request.model_profile_id,
                plan_id=request.plan_id,
                retry_failed=request.retry_failed,
                max_retries=request.max_retries,
            )
            session.commit()
            return serialize_episode_render_plan(session, plan)
        except EpisodeRenderingError as exc:
            session.commit()
            _raise(exc)
        except Exception:
            session.commit()
            raise


@router.get("/{episode_id}/render-status")
def render_status(episode_id: int, plan_id: int | None = None):
    with Session() as session:
        try:
            return serialize_episode_render_plan(session, get_episode_render_plan(session, episode_id=episode_id, plan_id=plan_id))
        except EpisodeRenderingError as exc:
            _raise(exc)


@router.post("/{episode_id}/render/complete")
def complete_render(episode_id: int, req: CompleteEpisodeRenderRequest | None = None):
    request = req or CompleteEpisodeRenderRequest()
    with Session() as session:
        try:
            plan = complete_episode_render_plan(session, episode_id=episode_id, plan_id=request.plan_id, reviewed=request.reviewed)
            session.commit()
            return serialize_episode_render_plan(session, plan)
        except EpisodeRenderingError as exc:
            session.rollback()
            _raise(exc)


__all__ = ["router"]
