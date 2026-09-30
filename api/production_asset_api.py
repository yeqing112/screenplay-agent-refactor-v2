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
    ProductionAssetScopeError,
    _asset_type,
    _typed_config,
    bind_shot_assets,
    ingest_production_asset,
    production_asset_media_readiness,
    resolve_production_asset_book_scope,
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
    ShotAssetBinding,
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


def _scope_or_404(session: Any, *, book_id: int, asset_type: str, asset_id: str | None = None, asset_version_id: str | None = None) -> dict[str, Any]:
    try:
        return resolve_production_asset_book_scope(
            session,
            book_id=int(book_id),
            asset_type=asset_type,
            asset_id=asset_id,
            asset_version_id=asset_version_id,
        )
    except ProductionAssetScopeError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": exc.code, "message": str(exc), "diagnostics": getattr(exc, "diagnostics", [])},
        ) from exc


def _bridge_version_payload(book_id: int, scope: dict[str, Any], version: Any | None) -> dict[str, Any] | None:
    if version is None:
        return None
    return {
        "asset_type": scope["asset_type"],
        "entity_id": scope["entity_id"],
        "authority_id": str(scope["authority"].authority_id),
        "version_id": str(version.version_id),
        "revision": int(version.revision or 0),
        "status": str(version.status or ""),
        "storage_identity": str(version.storage_identity or ""),
        "checksum": str(version.checksum or ""),
        "metadata_hash": str(version.metadata_hash or ""),
        "media": production_asset_media_readiness(
            storage_identity=version.storage_identity,
            checksum=version.checksum,
            metadata_hash=version.metadata_hash,
        ).to_dict(),
        "preview_url": f"/api/books/{int(book_id)}/production-assets/versions/{version.version_id}/media",
    }


def _bridge_state(session: Any, *, book_id: int, storyboard_shot_id: int) -> dict[str, Any]:
    shot = session.query(StoryboardShot).filter_by(book_id=int(book_id), id=int(storyboard_shot_id)).one_or_none()
    if shot is None:
        raise HTTPException(status_code=404, detail={"code": "STORYBOARD_SHOT_NOT_FOUND", "storyboard_shot_id": storyboard_shot_id})
    formal = _required_asset_contract(session, shot_id=int(shot.id))
    if not formal:
        raise HTTPException(status_code=409, detail={"code": "PRODUCTION_ASSET_REQUIREMENT_MISSING", "message": "shot has no formal Production Asset requirement contract"})
    requirements: list[dict[str, Any]] = []
    for asset_type, entity_id in formal:
        kind = _asset_type(asset_type)
        scope = None
        try:
            scope = resolve_production_asset_book_scope(session, book_id=int(book_id), asset_type=kind, asset_id=entity_id)
        except ProductionAssetScopeError:
            scope = None
        authority = scope.get("authority") if scope else None
        pointer = scope.get("pointer") if scope else None
        config = _typed_config(kind)
        versions = session.query(config["version"]).filter_by(authority_id=authority.authority_id if authority else "").order_by(config["version"].revision.desc(), config["version"].id.desc()).all() if authority else []
        current_version = None
        if authority and authority.current_version_id:
            current_version = session.query(config["version"]).filter_by(authority_id=authority.authority_id, version_id=authority.current_version_id).one_or_none()
        latest_version = versions[0] if versions else None
        version_ids = [str(item.version_id) for item in versions]
        reviews = session.query(ProductionAssetReview).filter(ProductionAssetReview.asset_type == kind, ProductionAssetReview.asset_id == entity_id, ProductionAssetReview.asset_version_id.in_(version_ids or ["__none__"])).order_by(ProductionAssetReview.id.desc()).all()
        latest_review = reviews[0] if reviews else None
        review_for_latest = next((row for row in reviews if latest_version and str(row.asset_version_id) == str(latest_version.version_id)), latest_review)
        binding_rows = session.query(ShotAssetBinding).filter_by(storyboard_shot_id=int(shot.id), asset_type=kind).order_by(ShotAssetBinding.id.desc()).all()
        binding = binding_rows[0] if binding_rows else None
        binding_current = bool(binding and current_version and str(binding.authority_id) == str(authority.authority_id) and str(binding.version_id) == str(current_version.version_id) and str(binding.status).upper() == "ACTIVE")
        if binding_current:
            requirement_status = "BOUND_CURRENT"
        elif binding and current_version:
            requirement_status = "BINDING_STALE"
        elif review_for_latest and review_for_latest.review_state == "HUMAN_REVIEW_PENDING":
            requirement_status = "REVIEW_PENDING"
        elif review_for_latest and review_for_latest.review_state == "HUMAN_APPROVED":
            requirement_status = "HUMAN_APPROVED_NOT_ACTIVATED"
        elif review_for_latest and review_for_latest.review_state == "REJECTED":
            requirement_status = "REJECTED"
        elif review_for_latest and review_for_latest.review_state == "REQUEST_CHANGE":
            requirement_status = "REQUEST_CHANGE"
        elif current_version:
            requirement_status = "CURRENT_NOT_BOUND"
        else:
            requirement_status = "MISSING"
        current_media = _bridge_version_payload(book_id, scope, current_version) if scope else None
        pending_review = _as_dict(review_for_latest) if review_for_latest and review_for_latest.review_state in {"HUMAN_REVIEW_PENDING", "HUMAN_APPROVED"} else None
        active_binding = None
        if binding:
            active_binding = {
                "id": int(binding.id),
                "asset_type": kind,
                "authority_id": str(binding.authority_id),
                "version_id": str(binding.version_id),
                "status": str(binding.status),
                "binding_fingerprint": str(binding.binding_fingerprint),
            }
        requirements.append({
            "entity_key": f"{kind}:{entity_id}",
            "asset_type": kind,
            "entity_id": entity_id,
            "requirement_status": requirement_status,
            "current_authority_id": str(authority.authority_id) if authority else None,
            "current_version_id": str(current_version.version_id) if current_version else None,
            "current_pointer": ({"id": int(pointer.id), "authority_id": str(pointer.authority_id), "version_id": str(pointer.version_id), "fingerprint": str(pointer.fingerprint)} if pointer else None),
            "current_media": current_media,
            "active_binding": active_binding,
            "binding_current": binding_current,
            "latest_version": _bridge_version_payload(book_id, scope, latest_version) if scope else None,
            "pending_review": pending_review,
            "pending_review_id": str(pending_review["review_id"]) if pending_review else None,
            "human_decision": str(review_for_latest.decision) if review_for_latest and review_for_latest.decision else None,
            "can_upload": requirement_status in {"MISSING", "REJECTED", "REQUEST_CHANGE", "REVIEW_PENDING"},
            "can_approve": bool(pending_review and pending_review["review_state"] == "HUMAN_REVIEW_PENDING"),
            "can_activate": bool(pending_review and pending_review["review_state"] == "HUMAN_APPROVED"),
            "can_bind": bool(current_version and scope and not binding_current),
        })
    all_current = all(item["requirement_status"] == "BOUND_CURRENT" for item in requirements)
    return {"schema_version": "production_asset_bridge_state_v1", "book_id": int(book_id), "storyboard_shot_id": int(shot.id), "requirements": requirements, "binding_current": all_current, "can_bind": bool(requirements) and all(item["can_bind"] or item["binding_current"] for item in requirements) and not all_current, "provider_calls": 0, "llm_calls": 0}


@router.post("/ingest", status_code=201)
def ingest_canonical_production_asset(
    book_id: int,
    asset_type: str = Form(..., alias="assetType"),
    entity_id: str = Form(..., alias="entityId"),
    metadata: str = Form(default="{}"),
    file: UploadFile = File(...),
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
        data = file.file.read()
        filename = str(file.filename or "asset")
        upload = file
        if not data:
            raise HTTPException(status_code=422, detail={"code": "MEDIA_EMPTY", "message": "uploaded media is empty"})
        if len(data) > int(config.UPLOAD_MAX_BYTES):
            raise HTTPException(status_code=413, detail={"code": "MEDIA_TOO_LARGE", "message": "uploaded media exceeds configured size limit"})
        mime_type = _mime_type(upload, data, filename=filename)
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
        _scope_or_404(session, book_id=book_id, asset_type=review.asset_type, asset_id=review.asset_id, asset_version_id=review.asset_version_id)
        return _review_payload(session, review)


@router.get("/reviews/{review_id}/history")
def get_production_asset_review_history(book_id: int, review_id: str):
    with Session() as session:
        review = session.query(ProductionAssetReview).filter_by(review_id=str(review_id)).one_or_none()
        if review is None:
            raise HTTPException(status_code=404, detail={"code": "PRODUCTION_ASSET_REVIEW_NOT_FOUND", "review_id": review_id})
        _scope_or_404(session, book_id=book_id, asset_type=review.asset_type, asset_id=review.asset_id, asset_version_id=review.asset_version_id)
        return {"review_id": review_id, "history": review_history(session, review_id)}


@router.post("/reviews/{review_id}/validate")
@router.post("/reviews/{review_id}/system-validate")
def validate_production_asset_review(book_id: int, review_id: str):
    with Session() as session:
        try:
            review = session.query(ProductionAssetReview).filter_by(review_id=str(review_id)).one_or_none()
            if review is None:
                raise HTTPException(status_code=404, detail={"code": "PRODUCTION_ASSET_REVIEW_NOT_FOUND", "review_id": review_id})
            _scope_or_404(session, book_id=book_id, asset_type=review.asset_type, asset_id=review.asset_id, asset_version_id=review.asset_version_id)
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
            review = session.query(ProductionAssetReview).filter_by(review_id=str(review_id)).one_or_none()
            if review is None:
                raise HTTPException(status_code=404, detail={"code": "PRODUCTION_ASSET_REVIEW_NOT_FOUND", "review_id": review_id})
            _scope_or_404(session, book_id=book_id, asset_type=review.asset_type, asset_id=review.asset_id, asset_version_id=review.asset_version_id)
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
            review = session.query(ProductionAssetReview).filter_by(review_id=str(review_id)).one_or_none()
            if review is None:
                raise HTTPException(status_code=404, detail={"code": "PRODUCTION_ASSET_REVIEW_NOT_FOUND", "review_id": review_id})
            _scope_or_404(session, book_id=book_id, asset_type=review.asset_type, asset_id=review.asset_id, asset_version_id=review.asset_version_id)
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


@router.post("/shots/{storyboard_shot_id}/bind-current")
def bind_current_production_asset_versions(book_id: int, storyboard_shot_id: int):
    """Explicitly bind the exact current canonical Pointer versions for a shot."""
    with Session() as session:
        state = _bridge_state(session, book_id=book_id, storyboard_shot_id=storyboard_shot_id)
        if not state["can_bind"]:
            raise HTTPException(status_code=409, detail={"code": "PRODUCTION_ASSET_BINDING_NOT_READY", "message": "all formal requirements must resolve to current canonical pointers before binding", "bridge_state": state})
        characters = [{"authority_id": item["current_authority_id"], "version_id": item["current_version_id"]} for item in state["requirements"] if item["asset_type"] == "CHARACTER"]
        scene_items = [item for item in state["requirements"] if item["asset_type"] == "SCENE"]
        props = [{"authority_id": item["current_authority_id"], "version_id": item["current_version_id"]} for item in state["requirements"] if item["asset_type"] == "PROP"]
        if len(scene_items) != 1:
            raise HTTPException(status_code=409, detail={"code": "PRODUCTION_ASSET_SCENE_REQUIREMENT_INVALID", "message": "exactly one current scene requirement is required"})
        try:
            resolved = bind_shot_assets(session, storyboard_shot_id=int(storyboard_shot_id), characters=characters, scene={"authority_id": scene_items[0]["current_authority_id"], "version_id": scene_items[0]["current_version_id"]}, props=props, book_id=int(book_id))
            formal = set(_required_asset_contract(session, shot_id=int(storyboard_shot_id)))
            actual = {(str(item.get("asset_type") or "").upper(), str(item.get("entity_id") or "")) for item in resolved}
            if actual != formal:
                raise AssetBindingInvalid("binding set does not exactly match the formal shot asset requirement")
            session.commit()
            readiness = _asset_readiness(session, shot_id=int(storyboard_shot_id), book_id=int(book_id))
            return {"book_id": int(book_id), "storyboard_shot_id": int(storyboard_shot_id), "bindings": resolved, "asset_readiness": readiness, "current": bool(readiness.get("current")), "bridge_state": _bridge_state(session, book_id=book_id, storyboard_shot_id=storyboard_shot_id)}
        except (AssetBindingInvalid, ProductionAssetSchemaError) as exc:
            session.rollback()
            _raise_domain(exc)


@router.get("/shots/{storyboard_shot_id}/bridge-state")
def get_production_asset_bridge_state(book_id: int, storyboard_shot_id: int):
    with Session() as session:
        return _bridge_state(session, book_id=book_id, storyboard_shot_id=storyboard_shot_id)


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
        scope = _scope_or_404(session, book_id=book_id, asset_type=registry.asset_type, asset_version_id=version_id)
        payload = _version_payload(session, book_id=book_id, asset_type=registry.asset_type, version_id=version_id)
        path = Path(payload["storage_identity"]).resolve()
        root = (config.UPLOAD_DIR / "production-assets" / f"book-{int(book_id)}").resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail={"code": "MEDIA_STORAGE_IDENTITY_NOT_SERVABLE", "version_id": version_id}) from exc
        if not path.is_file():
            raise HTTPException(status_code=404, detail={"code": "MEDIA_STORAGE_IDENTITY_MISSING", "version_id": version_id})
        return FileResponse(path, media_type=mimetypes.guess_type(str(path))[0] or "application/octet-stream")


__all__ = ["router", "AssetDecisionRequest", "AssetBindingRequest"]
