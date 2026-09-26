"""Candidate review and official-media promotion routes.

These routes are a thin API facade over ``core.media_authority``.  They do
not create a second asset store or call a provider; the existing candidate,
validation, OfficialMediaVersion, and OfficialMediaPointer records remain the
single authority chain.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from core.media_authority import MediaAuthorityError, promote_media_candidate, validate_media_candidate
from models import MediaCandidateRecord, MediaPromotionRecord, MediaValidationRecord, Session


router = APIRouter(prefix="/assets", tags=["asset-promotion-runtime"])


class PromoteCandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    validation_id: str = Field(min_length=1)
    promotion_id: str | None = Field(default=None, min_length=1)
    reviewer: str = Field(min_length=1)
    decision: str = Field(default="APPROVE", min_length=1)
    review_notes: str = ""
    confirmation: bool | str = True


def _raise(exc: MediaAuthorityError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.to_dict()) from exc


def _json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _serialize_validation(row: MediaValidationRecord | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "validation_id": row.validation_id,
        "candidate_id": row.candidate_id,
        "execution_id": row.execution_id,
        "candidate_fingerprint": row.candidate_fingerprint,
        "technical_validation_fingerprint": row.technical_validation_fingerprint,
        "authority_snapshot_fingerprint": row.authority_snapshot_fingerprint,
        "validator_version": row.validator_version,
        "status": row.status,
        "technical": _json(row.technical_validation_payload_json, {}),
    }


def _serialize_promotion(row: MediaPromotionRecord | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "promotion_id": row.promotion_id,
        "candidate_id": row.candidate_id,
        "validation_id": row.validation_id,
        "execution_id": row.execution_id,
        "review_status": row.review_status,
        "decision": row.decision,
        "reviewer": row.reviewer,
        "review_notes": row.review_notes,
        "official_media_version_id": row.official_media_version_id,
        "authority_id": row.authority_id,
        "promotion_fingerprint": row.promotion_fingerprint,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _serialize_candidate(session: Any, row: MediaCandidateRecord) -> dict[str, Any]:
    validation = session.query(MediaValidationRecord).filter_by(candidate_id=row.candidate_id).order_by(MediaValidationRecord.id.desc()).first()
    promotion = session.query(MediaPromotionRecord).filter_by(candidate_id=row.candidate_id).first()
    return {
        "id": row.id,
        "candidate_id": row.candidate_id,
        "generation_execution_id": row.generation_execution_id,
        "execution_id": row.execution_id,
        "asset_reference": row.asset_reference,
        "storage_identity": row.storage_identity,
        "media_type": row.media_type,
        "status": row.status,
        "validation_status": row.validation_status,
        "metadata": row.candidate_metadata,
        "prompt_ir_version_id": row.prompt_ir_version_id,
        "prompt_ir_payload_hash": row.prompt_ir_payload_hash,
        "provider_request_fingerprint": row.provider_request_fingerprint,
        "provider_response_hash": row.provider_response_hash,
        "checksum_sha256": row.checksum_sha256,
        "mime_type": row.mime_type,
        "byte_size": row.byte_size,
        "width": row.width,
        "height": row.height,
        "duration_ms": row.duration_ms,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "validation": _serialize_validation(validation),
        "promotion": _serialize_promotion(promotion),
    }


@router.get("/candidates")
def list_asset_candidates(
    status: str | None = Query(default=None),
    validation_status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    """List immutable media candidates and their review projections."""
    with Session() as session:
        query = session.query(MediaCandidateRecord).order_by(MediaCandidateRecord.id.desc())
        if status:
            query = query.filter(MediaCandidateRecord.status == status)
        if validation_status:
            query = query.filter(MediaCandidateRecord.validation_status == validation_status)
        rows = query.limit(limit).all()
        return {"candidates": [_serialize_candidate(session, row) for row in rows], "count": len(rows)}


@router.post("/candidates/{candidate_id}/validate")
def validate_asset_candidate(candidate_id: str):
    """Run deterministic storage, metadata, and lineage validation."""
    with Session() as session:
        try:
            result = validate_media_candidate(session, candidate_id)
        except MediaAuthorityError as exc:
            _raise(exc)
        candidate = session.query(MediaCandidateRecord).filter_by(candidate_id=candidate_id).one()
        return {
            "candidate": _serialize_candidate(session, candidate),
            "validation": _serialize_validation(result["validation"]),
            "promotion": _serialize_promotion(result.get("promotion")),
            "reused": result.get("reused", False),
            "provider_calls": 0,
            "llm_calls": 0,
            "image_calls": 0,
            "video_calls": 0,
        }


@router.post("/candidates/{candidate_id}/promote")
def promote_asset_candidate(candidate_id: str, req: PromoteCandidateRequest):
    """Approve one review record and publish a new OfficialMedia version."""
    with Session() as session:
        try:
            result = promote_media_candidate(
                session,
                candidate_id,
                req.validation_id,
                confirmation=req.confirmation,
                promotion_id=req.promotion_id,
                reviewer=req.reviewer,
                decision=req.decision,
                review_notes=req.review_notes,
            )
        except MediaAuthorityError as exc:
            _raise(exc)
        candidate = session.query(MediaCandidateRecord).filter_by(candidate_id=candidate_id).one()
        return {
            "candidate": _serialize_candidate(session, candidate),
            "promotion": _serialize_promotion(result.get("promotion")),
            "official_media_version_id": result["version"].official_media_version_id,
            "authority_id": result["authority"].authority_id,
            "pointer_id": result["pointer"].id,
            "reused": result.get("reused", False),
            "provider_calls": 0,
            "llm_calls": 0,
            "image_calls": 0,
            "video_calls": 0,
        }


__all__ = ["router", "PromoteCandidateRequest"]
