"""Provider-free visual asset authority and authoring boundary."""
from __future__ import annotations

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.visual_asset_authority import (
    AUTHORING_PENDING,
    PRODUCTION_READY,
    REFERENCE_LOCKED,
    SPEC_APPROVED,
    VisualAssetAuthorityError,
    asset_readiness,
    build_asset_key,
    build_reference_generation_request_draft,
    build_reference_media_authority,
    build_visual_asset_authority_envelope,
    classify_reference_asset,
    compile_visual_asset_spec,
    fingerprint,
    reference_requirement_policy,
    scope_key,
    propagate_visual_asset_staleness,
)
from models import (
    Session,
    VisualAssetPointer,
    VisualAssetVersion,
    VisualAuthoringDecision,
    VisualAuthoringDecisionRequest,
    VisualReferenceAsset,
    VisualReferenceAuthority,
    VisualReferenceGenerationRequest,
)

router = APIRouter(prefix="/api/books", tags=["visual-asset-authority"])


class AuthoringRequestBody(BaseModel):
    missing_field: str
    source_constraints: list[dict] = Field(default_factory=list)
    free_authoring_space: dict = Field(default_factory=dict)
    forbidden_contradictions: list[dict] = Field(default_factory=list)
    scope: dict = Field(default_factory=dict)
    required_by_stage: str = "PromptIR"


class AuthoringDecisionBody(BaseModel):
    request_id: str | None = None
    field: str
    value: object
    scope: dict = Field(default_factory=dict)
    source_constraint_refs: list[str] = Field(default_factory=list)
    author: str = "human"
    confirmed: bool = False


class VisualVersionBody(BaseModel):
    canonical_id: str
    canonical_identity: dict = Field(default_factory=dict)
    source_constraints: list[dict] = Field(default_factory=list)
    authoring_decisions: list[dict] = Field(default_factory=list)
    variant_decisions: list[dict] = Field(default_factory=list)
    scope: dict = Field(default_factory=dict)
    geometry_authority: dict = Field(default_factory=dict)
    continuity_authority: dict = Field(default_factory=dict)
    base_version_id: int | None = None
    confirmed: bool = False


class ReferenceAuthorityBody(BaseModel):
    visual_reference_asset_id: int
    reference_scope: dict = Field(default_factory=dict)
    image_identity: str
    checksum: str
    storage_reference: dict = Field(default_factory=dict)
    generation_provenance: dict = Field(default_factory=dict)
    reference_token_mapping: dict = Field(default_factory=dict)
    lock_revision: int = 1
    status: str = "LOCKED"
    confirmed: bool = False


class ReferenceDraftBody(BaseModel):
    reference_purpose: str = "production_reference"
    aspect_layout_requirement: dict = Field(default_factory=dict)
    board_type: str = "single_hero_reference"
    required_source_constraints: list[dict] = Field(default_factory=list)


def _conflict(code: str, message: str, **extra):
    raise HTTPException(status_code=409, detail={"code": code, "message": message, **extra})


def _json(value, fallback):
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _key(book_id: int, asset_type: str, canonical_id: str) -> str:
    try:
        return build_asset_key(book_id=book_id, asset_type=asset_type, canonical_id=canonical_id)
    except VisualAssetAuthorityError as exc:
        _conflict(exc.code, exc.message)


def _version_dict(row: VisualAssetVersion) -> dict:
    payload = _json(row.payload_json, {})
    return {"id": row.id, "asset_key": row.asset_key, "asset_type": row.asset_type, "canonical_id": row.canonical_id, "scope": _json(row.scope_json, {}), "revision": row.revision, "payload": payload, "payload_hash": row.payload_hash, "source_constraint_fingerprint": row.source_constraint_fingerprint, "authoring_decision_fingerprint": row.authoring_decision_fingerprint, "variant_fingerprint": row.variant_fingerprint, "authority_status": row.authority_status, "stale_status": row.stale_status, "stale_reasons": _json(row.stale_reasons, [])}


@router.post("/{book_id}/visual-assets/authority/{asset_type}/{canonical_id}/authoring-requests")
def create_authoring_request(book_id: int, asset_type: str, canonical_id: str, body: AuthoringRequestBody):
    asset_key = _key(book_id, asset_type, canonical_id)
    request_id = f"VAR-{uuid.uuid4().hex}"
    with Session() as session:
        row = VisualAuthoringDecisionRequest(request_id=request_id, book_id=book_id, asset_key=asset_key, asset_type=asset_type, missing_field=body.missing_field, source_constraints_json=json.dumps(body.source_constraints, ensure_ascii=False), free_authoring_space_json=json.dumps(body.free_authoring_space, ensure_ascii=False), forbidden_contradictions_json=json.dumps(body.forbidden_contradictions, ensure_ascii=False), scope_json=json.dumps(body.scope, ensure_ascii=False), required_by_stage=body.required_by_stage, status="PENDING", created_at=datetime.now(), updated_at=datetime.now())
        session.add(row); session.commit()
        return {"request_id": request_id, "asset_key": asset_key, "status": "PENDING", "provider_calls": 0}


@router.post("/{book_id}/visual-assets/authority/{asset_type}/{canonical_id}/authoring-decisions")
def record_authoring_decision(book_id: int, asset_type: str, canonical_id: str, body: AuthoringDecisionBody):
    if not body.confirmed:
        _conflict("AUTHORING_CONFIRMATION_REQUIRED", "Authoring decisions require confirmed=true before becoming eligible for authority.")
    asset_key = _key(book_id, asset_type, canonical_id)
    decision_id = f"VAD-{uuid.uuid4().hex}"
    with Session() as session:
        if body.request_id:
            request = session.query(VisualAuthoringDecisionRequest).filter_by(request_id=body.request_id, asset_key=asset_key).first()
            if not request:
                _conflict("AUTHORING_REQUEST_NOT_FOUND", "Authoring decision request does not match the asset authority.")
        decision = VisualAuthoringDecision(decision_id=decision_id, request_id=body.request_id, book_id=book_id, asset_key=asset_key, asset_type=asset_type, field=body.field, value_json=json.dumps(body.value, ensure_ascii=False), scope_json=json.dumps(body.scope, ensure_ascii=False), source_constraint_refs_json=json.dumps(body.source_constraint_refs, ensure_ascii=False), author=body.author, status="APPROVED", provenance_json=json.dumps({"provider_calls": 0}, ensure_ascii=False), created_at=datetime.now(), updated_at=datetime.now())
        session.add(decision)
        if body.request_id:
            request.status = "APPROVED"; request.resolution_json = json.dumps({"decision_id": decision_id, "field": body.field}, ensure_ascii=False); request.updated_at = datetime.now()
        session.commit()
        return {"decision_id": decision_id, "asset_key": asset_key, "status": "APPROVED", "provider_calls": 0}


@router.post("/{book_id}/visual-assets/authority/{asset_type}/versions")
def create_visual_asset_version(book_id: int, asset_type: str, body: VisualVersionBody):
    if not body.confirmed:
        _conflict("AUTHORING_CONFIRMATION_REQUIRED", "VisualAssetVersion activation requires confirmed=true.")
    asset_key = _key(book_id, asset_type, body.canonical_id)
    try:
        spec = compile_visual_asset_spec(asset_type=asset_type, asset_key=asset_key, canonical_identity=body.canonical_identity, source_constraints=body.source_constraints, authoring_decisions=body.authoring_decisions, variant_decisions=body.variant_decisions, scope=body.scope, geometry_authority=body.geometry_authority, continuity_authority=body.continuity_authority)
    except VisualAssetAuthorityError as exc:
        _conflict(exc.code, exc.message, diagnostics=exc.diagnostics)
    with Session() as session:
        existing = session.query(VisualAssetVersion).filter_by(asset_key=asset_key).order_by(VisualAssetVersion.revision.desc(), VisualAssetVersion.id.desc()).first()
        revision = (existing.revision + 1) if existing else 1
        if existing:
            propagate_visual_asset_staleness(session, asset_key=asset_key, reason="VISUAL_ASSET_VERSION_REPLACED")
        spec["id"] = None
        spec["revision"] = revision
        row = VisualAssetVersion(book_id=book_id, asset_key=asset_key, asset_type=asset_type, canonical_id=body.canonical_id, canonical_identity_json=json.dumps(body.canonical_identity, ensure_ascii=False), scope_json=json.dumps(body.scope, ensure_ascii=False), revision=revision, base_version_id=body.base_version_id or (existing.id if existing else None), payload_json=json.dumps(spec, ensure_ascii=False, sort_keys=True), payload_hash=spec["payload_hash"], source_constraints_json=json.dumps(body.source_constraints, ensure_ascii=False), authoring_decisions_json=json.dumps(body.authoring_decisions, ensure_ascii=False), variant_binding_json=json.dumps(body.variant_decisions, ensure_ascii=False), source_constraint_fingerprint=spec["source_constraint_fingerprint"], authoring_decision_fingerprint=spec["authoring_decision_fingerprint"], variant_fingerprint=spec["variant_fingerprint"], authority_status=SPEC_APPROVED, stale_status="FRESH", stale_reasons="[]", created_at=datetime.now(), updated_at=datetime.now())
        session.add(row); session.flush()
        current_scope_key = scope_key(asset_key=asset_key, scope=body.scope)
        pointer = session.query(VisualAssetPointer).filter_by(asset_key=asset_key, scope_key=current_scope_key).first()
        if pointer:
            pointer.current_version_id = row.id; pointer.payload_hash = row.payload_hash; pointer.authority_status = SPEC_APPROVED; pointer.stale_status = "FRESH"; pointer.stale_reasons = "[]"; pointer.updated_at = datetime.now()
        else:
            pointer = VisualAssetPointer(book_id=book_id, asset_key=asset_key, asset_type=asset_type, scope_key=current_scope_key, current_version_id=row.id, payload_hash=row.payload_hash, authority_status=SPEC_APPROVED, stale_status="FRESH", stale_reasons="[]", created_at=datetime.now(), updated_at=datetime.now()); session.add(pointer)
        session.commit()
        envelope = build_visual_asset_authority_envelope(version={**_version_dict(row), "source_constraints": body.source_constraints, "authoring_decision_ids": [item.get("decision_id") for item in body.authoring_decisions if isinstance(item, dict)], "variant_fingerprint": spec["variant_fingerprint"]}, pointer={"scope_key": current_scope_key, "current_version_id": row.id, "payload_hash": row.payload_hash})
        return {"asset_key": asset_key, "version_id": row.id, "revision": revision, "authority_status": SPEC_APPROVED, "pointer": {"scope_key": current_scope_key, "current_version_id": row.id}, "authority_envelope": envelope, "provider_calls": 0}


@router.get("/{book_id}/visual-assets/authority/{asset_type}/{canonical_id}/current")
def get_current_visual_asset(book_id: int, asset_type: str, canonical_id: str, scope: str = ""):
    asset_key = _key(book_id, asset_type, canonical_id)
    with Session() as session:
        query = session.query(VisualAssetPointer).filter_by(book_id=book_id, asset_key=asset_key)
        pointer = query.filter_by(scope_key=scope).first() if scope else query.order_by(VisualAssetPointer.id.desc()).first()
        if not pointer:
            _conflict("VISUAL_ASSET_POINTER_MISSING", "No current authoritative visual asset pointer exists.")
        version = session.query(VisualAssetVersion).filter_by(id=pointer.current_version_id).first()
        if not version or pointer.payload_hash != version.payload_hash or pointer.stale_status != "FRESH" or version.stale_status != "FRESH":
            _conflict("VISUAL_ASSET_POINTER_STALE", "Current visual asset pointer or payload is stale.")
        return {"asset_key": asset_key, "pointer": {"scope_key": pointer.scope_key, "current_version_id": pointer.current_version_id, "payload_hash": pointer.payload_hash}, "version": _version_dict(version), "provider_calls": 0}


@router.post("/{book_id}/visual-assets/authority/{asset_type}/{canonical_id}/references")
def bind_reference_authority(book_id: int, asset_type: str, canonical_id: str, body: ReferenceAuthorityBody):
    if not body.confirmed:
        _conflict("REFERENCE_CONFIRMATION_REQUIRED", "Reference authority activation requires confirmed=true.")
    asset_key = _key(book_id, asset_type, canonical_id)
    with Session() as session:
        version = session.query(VisualAssetVersion).filter_by(book_id=book_id, asset_key=asset_key).order_by(VisualAssetVersion.revision.desc()).first()
        if not version or version.stale_status != "FRESH" or version.authority_status != SPEC_APPROVED:
            _conflict("VISUAL_ASSET_VERSION_NOT_APPROVED", "A fresh approved VisualAssetVersion is required before reference binding.")
        reference = session.query(VisualReferenceAsset).filter_by(id=body.visual_reference_asset_id, book_id=book_id).first()
        if not reference:
            _conflict("REFERENCE_ASSET_NOT_FOUND", "Referenced media row was not found.")
        try:
            authority = build_reference_media_authority(asset_key=asset_key, asset_version_id=version.id, asset_version_fingerprint=version.payload_hash, reference_scope=body.reference_scope, image_identity=body.image_identity, checksum=body.checksum, storage_reference=body.storage_reference, generation_provenance=body.generation_provenance, reference_token_mapping=body.reference_token_mapping, lock_revision=body.lock_revision, status=body.status)
        except VisualAssetAuthorityError as exc:
            _conflict(exc.code, exc.message, diagnostics=exc.diagnostics)
        row = VisualReferenceAuthority(visual_reference_asset_id=reference.id, asset_key=asset_key, asset_version_id=version.id, asset_version_fingerprint=version.payload_hash, reference_scope_json=json.dumps(body.reference_scope, ensure_ascii=False), image_identity=body.image_identity, checksum=body.checksum, storage_reference_json=json.dumps(body.storage_reference, ensure_ascii=False), generation_provenance_json=json.dumps(body.generation_provenance, ensure_ascii=False), reference_token_mapping_json=json.dumps(body.reference_token_mapping, ensure_ascii=False), lock_revision=body.lock_revision, status=body.status.upper(), authority_fingerprint=authority["authority_fingerprint"], stale_status="FRESH", stale_reasons="[]", created_at=datetime.now(), updated_at=datetime.now())
        session.add(row)
        version.authority_status = PRODUCTION_READY if body.status.upper() == REFERENCE_LOCKED else version.authority_status
        session.query(VisualAssetPointer).filter_by(asset_key=asset_key, current_version_id=version.id).update({"authority_status": version.authority_status, "updated_at": datetime.now()}, synchronize_session=False)
        version.updated_at = datetime.now()
        reference.asset_key = asset_key; reference.asset_version_id = version.id; reference.authority_status = body.status.upper(); reference.reference_scope = json.dumps(body.reference_scope, ensure_ascii=False); reference.image_identity = body.image_identity; reference.checksum = body.checksum; reference.generation_provenance = json.dumps(body.generation_provenance, ensure_ascii=False); reference.lock_revision = body.lock_revision; reference.stale_status = "FRESH"; reference.stale_reasons = "[]"
        session.commit()
        return {"reference_authority_id": row.id, "asset_key": asset_key, "status": body.status.upper(), "authority_fingerprint": authority["authority_fingerprint"], "provider_calls": 0}


@router.post("/{book_id}/visual-assets/authority/{asset_type}/{canonical_id}/reference-generation-drafts")
def create_reference_generation_draft(book_id: int, asset_type: str, canonical_id: str, body: ReferenceDraftBody):
    asset_key = _key(book_id, asset_type, canonical_id)
    with Session() as session:
        pointer = session.query(VisualAssetPointer).filter_by(book_id=book_id, asset_key=asset_key).order_by(VisualAssetPointer.id.desc()).first()
        if not pointer:
            _conflict("VISUAL_ASSET_POINTER_MISSING", "Reference generation requires a current VisualAssetVersion.")
        version = session.query(VisualAssetVersion).filter_by(id=pointer.current_version_id).first()
        if not version or version.stale_status != "FRESH":
            _conflict("VISUAL_ASSET_VERSION_STALE", "Reference generation requires a fresh VisualAssetVersion.")
        draft = build_reference_generation_request_draft(version={"id": version.id, "asset_key": asset_key, "payload": _json(version.payload_json, {}), "variant_id": "", "allowed_authoring_fields": []}, reference_purpose=body.reference_purpose, aspect_layout_requirement=body.aspect_layout_requirement, board_type=body.board_type, required_source_constraints=body.required_source_constraints)
        row = session.query(VisualReferenceGenerationRequest).filter_by(request_fingerprint=draft["request_fingerprint"]).first()
        if not row:
            row = VisualReferenceGenerationRequest(request_fingerprint=draft["request_fingerprint"], asset_key=asset_key, asset_version_id=version.id, variant_id="", request_json=json.dumps(draft, ensure_ascii=False, sort_keys=True), status="READY_FOR_PROVIDER_CANARY", provider_not_called="true", created_at=datetime.now(), updated_at=datetime.now()); session.add(row); session.commit()
        return {"request_id": row.id, "request": draft, "status": "READY_FOR_PROVIDER_CANARY", "provider_not_called": True, "provider_calls": 0}


@router.get("/{book_id}/visual-assets/authority/audit")
def visual_asset_authority_audit(book_id: int):
    with Session() as session:
        versions = session.query(VisualAssetVersion).filter_by(book_id=book_id).all()
        refs = session.query(VisualReferenceAsset).filter_by(book_id=book_id).all()
        summary = {"IDENTITY_REGISTERED": 0, "ASSET_AUTHORING_PENDING": 0, "ASSET_REFERENCE_PENDING": 0, "ASSET_REFERENCE_READY": 0}
        for version in versions:
            spec = _json(version.payload_json, {})
            approved = version.authority_status in {SPEC_APPROVED, PRODUCTION_READY}
            readiness = asset_readiness(identity_ready=bool(version.asset_key), authoring_status=SPEC_APPROVED if approved else AUTHORING_PENDING, spec_approved=approved, reference_required=bool(spec.get("reference_required", False)), reference_locked=any(r.asset_version_id == version.id and r.authority_status == REFERENCE_LOCKED and r.stale_status == "FRESH" for r in refs))
            summary[readiness["status"]] = summary.get(readiness["status"], 0) + 1
        return {"book_id": book_id, "counts": summary, "version_count": len(versions), "reference_count": len(refs), "provider_calls": 0}


__all__ = ["router"]
