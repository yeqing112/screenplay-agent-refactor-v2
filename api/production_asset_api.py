"""Canonical Production Asset ingestion and review HTTP facade.

This module exposes the existing Production Asset Authority/Review domain
without creating a second registry.  Ingestion always creates a non-current
immutable Version first; only the existing review gate can activate a Pointer.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import uuid
from pathlib import Path
from typing import Any

import config
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from core.production_asset_authority import (
    AssetBindingInvalid,
    ProductionAssetSchemaError,
    _asset_type,
    _typed_config,
    bind_shot_assets,
    ingest_production_asset,
)
from core.production_asset_review import (
    ProductionAssetReviewError,
    ProductionAssetReviewGateError,
    ProductionAssetValidationError,
    _as_dict,
    _version_model,
    activate_production_asset_version_after_review,
    create_production_asset_review,
    production_review_gate,
    review_history,
    transition_production_asset_review,
    validate_production_asset_version,
)
from core.production_workspace_projection_v2 import _asset_readiness, _required_asset_contract
from models import (
    ProductionAssetReview,
    ProductionAssetVersionRegistry,
    Session,
    StoryboardShot,
)


router = APIRouter(prefix="/api/books/{book_id}/production-assets", tags=["production-assets"])


class AssetDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    decision: str = Field(min_length=1)
    reviewer_type: str = Field(default="DIRECTOR", min_length=1)
    comment: str = ""


class AssetBindingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    storyboard_shot_id: int = Field(gt=0, validation_alias="storyboardShotId")
    characters: list[dict[str, str]] = Field(default_factory=list)
    scene: dict[str, str]
    props: list[dict[str, str]] = Field(default_factory=list)


def _json_object(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail={"code": "ASSET_METADATA_INVALID", "message": "metadata must be valid JSON object"}) from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=422, detail={"code": "ASSET_METADATA_INVALID", "message": "metadata must be a JSON object"})
    return parsed


def _metadata_hash(metadata: dict[str, Any]) -> str:
    canonical = json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _safe_segment(value: str, fallback: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip("-._")
    return normalized[:100] or fallback


def _image_dimensions(data: bytes, mime_type: str) -> tuple[int | None, int | None]:
    if not str(mime_type or "").startswith("image/"):
        return None, None
    try:
        from PIL import Image

        from io import BytesIO

        with Image.open(BytesIO(data)) as image:
            image.verify()
        with Image.open(BytesIO(data)) as image:
            return int(image.width), int(image.height)
    except Exception as exc:
        raise HTTPException(status_code=422, detail={"code": "MEDIA_UNREADABLE", "message": "uploaded image cannot be decoded"}) from exc


def _mime_type(upload: UploadFile | None, data: bytes, *, filename: str = "", declared_override: str = "") -> str:
    declared = str(declared_override or (upload.content_type if upload is not None else "") or "").split(";", 1)[0].strip().lower()
    guessed = mimetypes.guess_type(str(filename or (upload.filename if upload is not None else "")))[0] or ""
    if declared in {"application/octet-stream", ""}:
        declared = guessed
    if not declared:
        if data.startswith(b"\x89PNG"):
            declared = "image/png"
        elif data.startswith(b"\xff\xd8\xff"):
            declared = "image/jpeg"
        elif data.startswith((b"GIF87a", b"GIF89a")):
            declared = "image/gif"
        elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            declared = "image/webp"
    if not declared.startswith(("image/", "video/")):
        raise HTTPException(status_code=422, detail={"code": "MEDIA_MIME_UNSUPPORTED", "message": "only image/* and video/* production media are supported"})
    return declared


def _formal_requirements_for_book(session: Any, book_id: int) -> set[tuple[str, str]]:
    requirements: set[tuple[str, str]] = set()
    rows = session.query(StoryboardShot).filter_by(book_id=int(book_id)).all()
    for row in rows:
        requirements.update(_required_asset_contract(session, shot_id=int(row.id)))
    return requirements


def _require_canonical_identity(session: Any, *, book_id: int, asset_type: str, entity_id: str) -> None:
    requirements = _formal_requirements_for_book(session, book_id)
    if (asset_type, entity_id) not in requirements:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CANONICAL_ENTITY_REQUIREMENT_NOT_FOUND",
                "message": "entity_id must be present in the persisted Production Asset requirement contract",
                "asset_type": asset_type,
                "entity_id": entity_id,
                "required_entities": [f"{kind}:{identity}" for kind, identity in sorted(requirements)],
            },
        )


def _version_payload(session: Any, *, book_id: int, asset_type: str, version_id: str) -> dict[str, Any]:
    kind = _asset_type(asset_type)
    model = _version_model(kind)
    config_map = _typed_config(kind)
    version = session.query(model).filter_by(version_id=str(version_id)).one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail={"code": "PRODUCTION_ASSET_VERSION_NOT_FOUND", "version_id": version_id})
    authority = session.query(config_map["authority"]).filter_by(authority_id=version.authority_id).one_or_none()
    if authority is None:
        raise HTTPException(status_code=409, detail={"code": "PRODUCTION_ASSET_AUTHORITY_MISSING", "version_id": version_id})
    return {
        "asset_type": kind,
        "entity_id": str(getattr(authority, config_map["entity"], "") or ""),
        "authority_id": str(version.authority_id),
        "version_id": str(version.version_id),
        "revision": int(version.revision or 0),
        "status": str(version.status or ""),
        "storage_identity": str(version.storage_identity or ""),
        "checksum": str(version.checksum or ""),
        "metadata_hash": str(version.metadata_hash or ""),
        "pointer_activated": bool(str(authority.current_version_id or "") == str(version.version_id)),
        "preview_url": f"/api/books/{int(book_id)}/production-assets/versions/{version.version_id}/media",
    }


def _review_payload(session: Any, review: ProductionAssetReview) -> dict[str, Any]:
    payload = _as_dict(review)
    payload["history"] = review_history(session, review.review_id)
    payload["gate"] = production_review_gate(
        session,
        asset_type=review.asset_type,
        asset_id=review.asset_id,
        asset_version_id=review.asset_version_id,
    )
    return payload


def _raise_domain(exc: Exception) -> None:
    status = int(getattr(exc, "status_code", 409) or 409)
    detail = {"code": str(getattr(exc, "code", "PRODUCTION_ASSET_ERROR")), "message": str(exc)}
    diagnostics = getattr(exc, "diagnostics", None)
    if diagnostics:
        detail["diagnostics"] = diagnostics
    if isinstance(exc, ProductionAssetReviewGateError):
        detail["gate"] = exc.report
    raise HTTPException(status_code=status, detail=detail) from exc


@router.post("/ingest", status_code=201)
def ingest_canonical_production_asset(
    book_id: int,
    asset_type: str = Form(..., alias="assetType"),
    entity_id: str = Form(..., alias="entityId"),
    metadata: str = Form(default="{}"),
    file: UploadFile | None = File(default=None),
    storage_identity: str = Form(default="", alias="storageIdentity"),
):
    """Persist a real media Version and open a review, without activating it."""
    try:
        kind = _asset_type(asset_type)
    except ProductionAssetSchemaError as exc:
        _raise_domain(exc)
    identity = str(entity_id or "").strip()
    if not identity:
        raise HTTPException(status_code=422, detail={"code": "CANONICAL_ENTITY_ID_REQUIRED", "message": "entity_id is required"})
    metadata_payload = _json_object(metadata)
    with Session() as session:
        _require_canonical_identity(session, book_id=book_id, asset_type=kind, entity_id=identity)
        if file is None:
            source_path = Path(str(storage_identity or "").strip())
            if not source_path.is_absolute() or not source_path.is_file():
                raise HTTPException(status_code=422, detail={"code": "MEDIA_UPLOAD_REQUIRED", "message": "multipart file is required for canonical ingestion"})
            data = source_path.read_bytes()
            filename = source_path.name
            declared_mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        else:
            data = file.file.read()
            filename = str(file.filename or "asset")
            upload = file
        if not data:
            raise HTTPException(status_code=422, detail={"code": "MEDIA_EMPTY", "message": "uploaded media is empty"})
        if len(data) > int(config.UPLOAD_MAX_BYTES):
            raise HTTPException(status_code=413, detail={"code": "MEDIA_TOO_LARGE", "message": "uploaded media exceeds configured size limit"})
        mime_type = _mime_type(upload if file is not None else None, data, filename=filename, declared_override=declared_mime if file is None else "")
        width, height = _image_dimensions(data, mime_type)
        base_metadata = {key: value for key, value in metadata_payload.items() if key not in {"checksum", "metadata_hash", "storage_identity", "source_kind"}}
        base_metadata.update({
            "schema_version": "production_asset_media_metadata_v1",
            "source_kind": "uploaded_file",
            "mime_type": mime_type,
            "width": width,
            "height": height,
            "byte_size": len(data),
            "original_filename": filename,
        })
        digest = f"sha256:{hashlib.sha256(data).hexdigest()}"
        target_dir = (config.UPLOAD_DIR / "production-assets" / f"book-{int(book_id)}" / kind.lower() / _safe_segment(identity, "entity")).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(filename).suffix.lower() or mimetypes.guess_extension(mime_type) or ".bin"
        target_path = (target_dir / f"{uuid.uuid4().hex}{suffix}").resolve()
        target_path.relative_to((config.UPLOAD_DIR / "production-assets").resolve())
        target_path.write_bytes(data)
        source = {"storage_identity": str(target_path), "checksum": digest, "metadata": base_metadata}
        try:
            ingested = ingest_production_asset(session, entity_type=kind, entity_id=identity, source=source, book_id=book_id, activate_pointer=False)
            review = create_production_asset_review(session, asset_type=kind, asset_id=identity, asset_version_id=ingested["version_id"], comment="Canonical ingestion created a non-current version; deterministic validation started.")
            validation = validate_production_asset_version(session, review_id=review["review_id"], metadata=base_metadata)
            session.commit()
        except (ProductionAssetSchemaError, ProductionAssetReviewError) as exc:
            session.rollback()
            try:
                target_path.unlink(missing_ok=True)
            except OSError:
                pass
            _raise_domain(exc)
        return {
            "book_id": int(book_id),
            "asset_type": kind,
            "entity_id": identity,
            "version": _version_payload(session, book_id=book_id, asset_type=kind, version_id=ingested["version_id"]),
            "review": validation["review"],
            "history": validation["history"],
            "review_state": validation["review"]["review_state"],
            "media_readiness": {"present": True, "mime_type": mime_type, "width": width, "height": height, "byte_size": len(data)},
            "pointer_activated": False,
            "official": False,
            "ready": False,
            "provider_calls": 0,
            "llm_calls": 0,
            "image_calls": 0,
            "video_calls": 0,
        }


@router.get("/reviews/{review_id}")
def get_production_asset_review(book_id: int, review_id: str):
    with Session() as session:
        review = session.query(ProductionAssetReview).filter_by(review_id=str(review_id)).one_or_none()
        if review is None:
            raise HTTPException(status_code=404, detail={"code": "PRODUCTION_ASSET_REVIEW_NOT_FOUND", "review_id": review_id})
        return _review_payload(session, review)


@router.get("/reviews/{review_id}/history")
def get_production_asset_review_history(book_id: int, review_id: str):
    with Session() as session:
        if session.query(ProductionAssetReview).filter_by(review_id=str(review_id)).one_or_none() is None:
            raise HTTPException(status_code=404, detail={"code": "PRODUCTION_ASSET_REVIEW_NOT_FOUND", "review_id": review_id})
        return {"review_id": review_id, "history": review_history(session, review_id)}


@router.post("/reviews/{review_id}/validate")
@router.post("/reviews/{review_id}/system-validate")
def validate_production_asset_review(book_id: int, review_id: str):
    with Session() as session:
        try:
            result = validate_production_asset_version(session, review_id=review_id)
            session.commit()
            return result
        except ProductionAssetReviewError as exc:
            session.rollback()
            _raise_domain(exc)


@router.post("/reviews/{review_id}/decision")
@router.post("/reviews/{review_id}/human-decision")
def decide_production_asset_review(book_id: int, review_id: str, req: AssetDecisionRequest):
    decision = str(req.decision or "").strip().upper()
    target = {"APPROVE": "HUMAN_APPROVED", "REJECT": "REJECTED", "REQUEST_CHANGE": "REQUEST_CHANGE"}.get(decision)
    if target is None:
        raise HTTPException(status_code=422, detail={"code": "PRODUCTION_ASSET_DECISION_INVALID", "message": "decision must be APPROVE, REJECT, or REQUEST_CHANGE"})
    with Session() as session:
        try:
            result = transition_production_asset_review(session, review_id=review_id, to_state=target, reviewer_type=req.reviewer_type, decision=decision, comment=req.comment)
            session.commit()
            review = session.query(ProductionAssetReview).filter_by(review_id=review_id).one()
            return {"review": _review_payload(session, review), "decision": decision, "pointer_activated": False}
        except ProductionAssetReviewError as exc:
            session.rollback()
            _raise_domain(exc)


@router.post("/reviews/{review_id}/activate")
def activate_reviewed_production_asset(book_id: int, review_id: str):
    with Session() as session:
        try:
            result = activate_production_asset_version_after_review(session, review_id=review_id, book_id=book_id)
            session.commit()
            review = session.query(ProductionAssetReview).filter_by(review_id=review_id).one()
            return {"review": _review_payload(session, review), "switch": result["switch"], "pointer_activated": True, "official": False, "ready": False}
        except ProductionAssetReviewError as exc:
            session.rollback()
            _raise_domain(exc)


@router.post("/bindings")
def bind_production_asset_versions(book_id: int, req: AssetBindingRequest):
    with Session() as session:
        shot = session.query(StoryboardShot).filter_by(book_id=book_id, id=req.storyboard_shot_id).one_or_none()
        if shot is None:
            raise HTTPException(status_code=404, detail={"code": "STORYBOARD_SHOT_NOT_FOUND", "storyboard_shot_id": req.storyboard_shot_id})
        formal = set(_required_asset_contract(session, shot_id=int(shot.id)))
        if not formal:
            raise HTTPException(status_code=409, detail={"code": "PRODUCTION_ASSET_REQUIREMENT_MISSING", "message": "shot has no formal Production Asset requirement contract"})
        try:
            resolved = bind_shot_assets(session, storyboard_shot_id=int(shot.id), characters=req.characters, scene=req.scene, props=req.props, book_id=int(book_id))
            actual = {(str(item.get("asset_type") or "").upper(), str(item.get("entity_id") or "")) for item in resolved}
            if actual != formal:
                raise AssetBindingInvalid("binding set does not exactly match the formal shot asset requirement", diagnostics=[{"required": sorted(formal), "received": sorted(actual)}])
            session.commit()
            readiness = _asset_readiness(session, shot_id=int(shot.id), book_id=int(book_id))
            return {"book_id": int(book_id), "storyboard_shot_id": int(shot.id), "bindings": resolved, "asset_readiness": readiness, "current": bool(readiness.get("current"))}
        except (AssetBindingInvalid, ProductionAssetSchemaError) as exc:
            session.rollback()
            _raise_domain(exc)


@router.get("/shots/{storyboard_shot_id}/readiness")
def get_production_asset_readiness(book_id: int, storyboard_shot_id: int):
    with Session() as session:
        shot = session.query(StoryboardShot).filter_by(book_id=book_id, id=storyboard_shot_id).one_or_none()
        if shot is None:
            raise HTTPException(status_code=404, detail={"code": "STORYBOARD_SHOT_NOT_FOUND", "storyboard_shot_id": storyboard_shot_id})
        return {"book_id": int(book_id), "storyboard_shot_id": int(storyboard_shot_id), "asset_readiness": _asset_readiness(session, shot_id=int(storyboard_shot_id), book_id=int(book_id))}


@router.get("/versions/{version_id}/media")
def get_production_asset_media(book_id: int, version_id: str):
    with Session() as session:
        registry = session.query(ProductionAssetVersionRegistry).filter_by(version_id=str(version_id)).one_or_none()
        if registry is None:
            raise HTTPException(status_code=404, detail={"code": "PRODUCTION_ASSET_VERSION_NOT_FOUND", "version_id": version_id})
        payload = _version_payload(session, book_id=book_id, asset_type=registry.asset_type, version_id=version_id)
        path = Path(payload["storage_identity"]).resolve()
        root = (config.UPLOAD_DIR / "production-assets").resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail={"code": "MEDIA_STORAGE_IDENTITY_NOT_SERVABLE", "version_id": version_id}) from exc
        if not path.is_file():
            raise HTTPException(status_code=404, detail={"code": "MEDIA_STORAGE_IDENTITY_MISSING", "version_id": version_id})
        return FileResponse(path, media_type=mimetypes.guess_type(str(path))[0] or "application/octet-stream")


__all__ = ["router", "AssetDecisionRequest", "AssetBindingRequest"]
