"""Provider-only visual authoring routes.

The routes in this module stop at a reviewable proposal.  They intentionally
do not call the legacy semantic-governance write path and never activate an
asset or reference.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

import core.llm as llm_client
from api.model_registry import get_profile
from core.prompt_cache import canonical_json, llm_request_fingerprint, summarize_audit_records
from core.visual_authoring_provider import (
    ALLOWED_FIELDS,
    VISUAL_AUTHORING_PROPOSAL_SCHEMA_VERSION,
    build_visual_authoring_provider_context,
    build_visual_authoring_provider_prompt,
    proposal_payload_fingerprint,
    validate_visual_authoring_proposal,
)
from models import (
    CharacterProfile,
    Session,
    VisualAuthoringDecision,
    VisualAuthoringDecisionRequest,
    VisualAuthoringProposal,
    VisualLocation,
    VisualMakeup,
    VisualProp,
)


router = APIRouter(prefix="/api/books", tags=["visual-authoring-provider"])


class VisualAuthoringRequestCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    request_id: str = Field(default="", validation_alias=AliasChoices("request_id", "requestId"))
    asset_key: str = Field(default="", validation_alias=AliasChoices("asset_key", "assetKey"))
    canonical_id: str = Field(default="", validation_alias=AliasChoices("canonical_id", "canonicalId"))
    scope: dict = Field(default_factory=dict)
    source_constraints: dict = Field(default_factory=dict, validation_alias=AliasChoices("source_constraints", "sourceConstraints"))
    free_authoring_space: list[str] = Field(default_factory=list, validation_alias=AliasChoices("free_authoring_space", "freeAuthoringSpace"))
    forbidden_contradictions: list[str] = Field(default_factory=list, validation_alias=AliasChoices("forbidden_contradictions", "forbiddenContradictions"))
    context: dict = Field(default_factory=dict)
    advisory_legacy_context: dict = Field(default_factory=dict, validation_alias=AliasChoices("advisory_legacy_context", "advisoryLegacyContext"))


class VisualAuthoringCanaryRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    request_id: str = Field(validation_alias=AliasChoices("request_id", "requestId"))
    model_profile_id: str = Field(validation_alias=AliasChoices("model_profile_id", "modelProfileId"))
    confirmed_provider_call: bool = Field(default=False, validation_alias=AliasChoices("confirmed_provider_call", "confirmedProviderCall"))


class VisualAuthoringReviewRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    confirmed: bool = False
    reviewed_proposals: list[dict] = Field(default_factory=list, validation_alias=AliasChoices("reviewed_proposals", "reviewedProposals"))
    review_notes: str = Field(default="", validation_alias=AliasChoices("review_notes", "reviewNotes"))


def _json(value: Any, fallback: Any) -> Any:
    try:
        parsed = json.loads(value or "")
        return parsed
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _error(status: int, code: str, message: str, **extra: Any) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message, **extra})


def _asset_model(asset_type: str):
    return {"character": VisualMakeup, "scene": VisualLocation, "prop": VisualProp}.get(asset_type)


def _asset_row(session, book_id: int, asset_type: str, canonical_id: str):
    model = _asset_model(asset_type)
    if model is None:
        return None
    row = session.query(model).filter(model.book_id == book_id, model.id == int(canonical_id)).first()
    if row is not None:
        return row
    if asset_type == "character":
        return session.query(CharacterProfile).filter(CharacterProfile.book_id == book_id, CharacterProfile.id == int(canonical_id)).first()
    return None


def _structured_asset_snapshot(row: Any, asset_type: str) -> dict:
    if row is None:
        return {}
    fields = {
        "character": ("character_name", "gender", "identity", "hair_style", "makeup_spec", "refined_outfit", "refined_accessories", "temperament", "vibe", "color_palette", "face_shape", "facial_features", "body_type", "skin_tone"),
        "scene": ("name", "category", "style", "description", "color_palette", "lighting_mood", "key_props", "time_period", "board_spec", "canonical_facts", "state_variants", "look_profile"),
        "prop": ("name", "category", "description", "associated_characters", "time_period", "importance", "notes", "canonical_facts", "state_variants", "look_profile"),
    }[asset_type]
    return {field: getattr(row, field, "") for field in fields if hasattr(row, field)}


def _serialize_proposal(row: VisualAuthoringProposal) -> dict:
    return {
        "id": row.id,
        "proposal_id": row.proposal_id,
        "request_id": row.request_id,
        "book_id": row.book_id,
        "asset_key": row.asset_key,
        "asset_type": row.asset_type,
        "scope": _json(row.scope, {}),
        "proposed_fields": _json(row.proposed_fields_json, {}),
        "explanation_summary": row.explanation_summary,
        "source_constraint_refs": _json(row.source_constraint_refs, []),
        "provider": {
            "profile_id": row.provider_profile_id,
            "model": row.provider_model,
            "vendor_host": row.provider_vendor_host,
            "request_fingerprint": row.provider_request_fingerprint,
            "response_hash": row.provider_response_hash,
        },
        "validator_status": row.validator_status,
        "validator_diagnostics": _json(row.validator_diagnostics, {}),
        "audit": _json(row.audit_json, {}),
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.post("/{book_id}/visual-assets/authority/{asset_type}/{canonical_id}/authoring-requests")
def create_visual_authoring_request(book_id: int, asset_type: str, canonical_id: str, req: VisualAuthoringRequestCreate):
    if asset_type not in ALLOWED_FIELDS:
        raise _error(422, "PROPOSAL_SCOPE_MISMATCH", "unsupported visual asset type")
    with Session() as session:
        row = _asset_row(session, book_id, asset_type, canonical_id)
        if row is None:
            raise _error(404, "ASSET_NOT_FOUND", "visual asset not found")
        request_id = req.request_id.strip() or f"var_{uuid.uuid4().hex}"
        asset_key = req.asset_key.strip() or f"{asset_type}:{canonical_id}"
        existing = session.query(VisualAuthoringDecisionRequest).filter_by(request_id=request_id).first()
        if existing:
            return {"request": _serialize_request(existing), "deduplicated": True}
        source_constraints = dict(req.source_constraints)
        structured_snapshot = _structured_asset_snapshot(row, asset_type)
        if not source_constraints:
            # Only structured authority fields are eligible as constraints.
            source_constraints = {key: value for key, value in structured_snapshot.items() if value not in (None, "", [], {})}
        free_space = req.free_authoring_space or sorted(ALLOWED_FIELDS[asset_type])
        request = VisualAuthoringDecisionRequest(
            request_id=request_id,
            book_id=book_id,
            asset_key=asset_key,
            asset_type=asset_type,
            canonical_id=str(canonical_id),
            scope=json.dumps(req.scope, ensure_ascii=False),
            source_constraints=json.dumps(source_constraints, ensure_ascii=False),
            free_authoring_space=json.dumps(free_space, ensure_ascii=False),
            forbidden_contradictions=json.dumps(req.forbidden_contradictions, ensure_ascii=False),
            context_json=json.dumps({
                **req.context,
                "asset_snapshot": structured_snapshot,
                "asset_snapshot_fingerprint": proposal_payload_fingerprint(structured_snapshot),
                "advisory_legacy_context": req.advisory_legacy_context,
            }, ensure_ascii=False),
        )
        session.add(request)
        session.commit()
        return {"request": _serialize_request(request), "llm_called": False}


def _serialize_request(row: VisualAuthoringDecisionRequest) -> dict:
    return {
        "request_id": row.request_id, "book_id": row.book_id, "asset_key": row.asset_key,
        "asset_type": row.asset_type, "canonical_id": row.canonical_id,
        "scope": _json(row.scope, {}), "source_constraints": _json(row.source_constraints, {}),
        "free_authoring_space": _json(row.free_authoring_space, []),
        "forbidden_contradictions": _json(row.forbidden_contradictions, []),
        "context": _json(row.context_json, {}), "status": row.status,
    }


@router.post("/{book_id}/visual-assets/authority/{asset_type}/{canonical_id}/authoring-proposals/canary")
def create_visual_authoring_proposal_canary(book_id: int, asset_type: str, canonical_id: str, req: VisualAuthoringCanaryRequest):
    # Check confirmation before any provider/profile work. This is the hard
    # billable-call boundary.
    if not req.confirmed_provider_call:
        raise _error(409, "PROVIDER_CALL_CONFIRMATION_REQUIRED", "provider call requires confirmed_provider_call=true", provider_calls=0)
    profile = get_profile(req.model_profile_id)
    if not profile or profile.get("capability") != "llm":
        raise _error(422, "INVALID_PROVIDER_PROFILE", "explicit profile must be an enabled LLM profile")
    if not profile.get("enabled") or not profile.get("key_configured") or not str(profile.get("model_name") or "").strip():
        raise _error(422, "INVALID_PROVIDER_PROFILE", "LLM profile is disabled, missing credentials, or missing model name")
    with Session() as session:
        request = session.query(VisualAuthoringDecisionRequest).filter_by(request_id=req.request_id, book_id=book_id).first()
        if not request:
            raise _error(404, "AUTHORING_REQUEST_NOT_FOUND", "authoring request not found")
        if request.asset_type != asset_type or request.canonical_id != str(canonical_id):
            raise _error(409, "PROPOSAL_ASSET_MISMATCH", "request is bound to a different asset")
        row = _asset_row(session, book_id, asset_type, canonical_id)
        if row is None:
            raise _error(404, "ASSET_NOT_FOUND", "visual asset not found")
        request_payload = _serialize_request(request)
        request_context = _json(request.context_json, {})
        expected_snapshot_fingerprint = str(request_context.get("asset_snapshot_fingerprint") or "") if isinstance(request_context, dict) else ""
        current_snapshot = _structured_asset_snapshot(row, asset_type)
        if expected_snapshot_fingerprint and expected_snapshot_fingerprint != proposal_payload_fingerprint(current_snapshot):
            raise _error(409, "AUTHORING_REQUEST_STALE", "asset changed after the authoring request was frozen; create a new request", provider_calls=0)
        context = build_visual_authoring_provider_context(
            request=request_payload,
            asset=current_snapshot,
            authoritative_context=request_context,
        )
        system, user = build_visual_authoring_provider_prompt(context)
        fingerprint = llm_request_fingerprint(system=system, user=user, profile=profile, extra={"contract": context["contract_version"]})
        existing = session.query(VisualAuthoringProposal).filter_by(request_id=request.request_id, provider_request_fingerprint=fingerprint).first()
        if existing:
            return {"proposal": _serialize_proposal(existing), "llm_called": False, "provider_calls": 0, "deduplicated": True}
        audit_records: list[dict] = []
        try:
            raw = llm_client.call_llm_json(
                user,
                system=system,
                model_profile=profile,
                required_keys={"schema_version", "request_id", "asset_key", "proposals", "unknowns", "review_notes"},
                json_parse_retries=0,
                retries=1,
                estimated_tokens=1800,
                max_tokens=1800,
                temperature=0,
                audit_callback=audit_records.append,
                audit_extra={"mode": "visual_authoring_provider_canary", "request_id": request.request_id, "asset_key": request.asset_key},
            )
        except Exception as exc:
            audit = summarize_audit_records(audit_records)
            raise _error(502, "PROVIDER_CALL_FAILED", str(exc)[:300], provider_calls=1, audit=audit)
        validation = validate_visual_authoring_proposal(raw, request=request_payload, context=context)
        normalized = validation.get("normalized") or {}
        response_hash = hashlib.sha256(canonical_json(raw).encode("utf-8")).hexdigest()
        payload_hash = proposal_payload_fingerprint(normalized)
        audit = summarize_audit_records(audit_records)
        audit.update({
            "logical_provider_calls": 1,
            "transport_attempt_count": audit.get("attempt_count", 0),
            "request_id": request.request_id,
            "asset_key": request.asset_key,
            "profile_id": profile.get("id"),
            "provider_model": profile.get("model_name"),
            "vendor_host": (audit.get("vendor_hosts") or [""])[-1] if audit.get("vendor_hosts") else "",
            "request_fingerprint": fingerprint,
            "response_hash": response_hash,
        })
        if audit_records:
            last_audit = audit_records[-1] if isinstance(audit_records[-1], dict) else {}
            for safe_key in ("system_prompt_sha256", "user_prompt_sha256", "request_messages_sha256", "response_sha256", "latency_ms", "http_status", "parse_ok", "provider_request_id"):
                if safe_key in last_audit:
                    audit[safe_key] = last_audit[safe_key]
        proposal = VisualAuthoringProposal(
            proposal_id=f"vap_{uuid.uuid4().hex}", request_id=request.request_id, book_id=book_id,
            asset_key=request.asset_key, asset_type=asset_type, scope=request.scope,
            proposed_fields_json=json.dumps(normalized, ensure_ascii=False),
            explanation_summary="；".join(normalized.get("review_notes") or [])[:2000],
            source_constraint_refs=json.dumps([ref for item in normalized.get("proposals", []) for ref in item.get("constraint_refs", [])], ensure_ascii=False),
            provider_profile_id=str(profile.get("id") or req.model_profile_id), provider_model=str(profile.get("model_name") or ""),
            provider_vendor_host=str(audit.get("vendor_host") or ""), provider_request_fingerprint=fingerprint,
            provider_response_hash=response_hash, proposal_payload_hash=payload_hash,
            validator_status="PASS" if validation["ok"] else "FAIL",
            validator_diagnostics=json.dumps({"reason_codes": validation.get("reason_codes", []), "diagnostics": validation.get("diagnostics", [])}, ensure_ascii=False),
            audit_json=json.dumps(audit, ensure_ascii=False), status="REVIEW_REQUIRED" if validation["ok"] else "REJECTED",
        )
        session.add(proposal)
        session.commit()
        result = {"proposal": _serialize_proposal(proposal), "llm_called": True, "provider_calls": 1, "deduplicated": False}
        if not validation["ok"]:
            raise _error(422, validation["reason_codes"][0] if validation.get("reason_codes") else "PROPOSAL_SCHEMA_INVALID", "provider proposal rejected", **result)
        return result


@router.get("/{book_id}/visual-assets/authority/authoring-proposals/{proposal_id}")
def get_visual_authoring_proposal(book_id: int, proposal_id: str):
    with Session() as session:
        row = session.query(VisualAuthoringProposal).filter_by(book_id=book_id, proposal_id=proposal_id).first()
        if not row:
            raise _error(404, "PROPOSAL_NOT_FOUND", "proposal not found")
        return {"proposal": _serialize_proposal(row)}


@router.get("/{book_id}/visual-assets/authority/{asset_type}/{canonical_id}/authoring-proposals/{proposal_id}")
def get_visual_authoring_proposal_scoped(book_id: int, asset_type: str, canonical_id: str, proposal_id: str):
    """Scoped alias for clients that keep the asset route in their URL."""
    with Session() as session:
        row = session.query(VisualAuthoringProposal).filter_by(book_id=book_id, proposal_id=proposal_id, asset_type=asset_type, asset_key=f"{asset_type}:{canonical_id}").first()
        if not row:
            raise _error(404, "PROPOSAL_NOT_FOUND", "proposal not found")
        return {"proposal": _serialize_proposal(row)}


@router.post("/{book_id}/visual-assets/authority/authoring-proposals/{proposal_id}/reject")
def reject_visual_authoring_proposal(book_id: int, proposal_id: str, req: VisualAuthoringReviewRequest):
    if not req.confirmed:
        raise _error(409, "REVIEW_CONFIRMATION_REQUIRED", "reject requires confirmed=true")
    with Session() as session:
        row = session.query(VisualAuthoringProposal).filter_by(book_id=book_id, proposal_id=proposal_id).first()
        if not row:
            raise _error(404, "PROPOSAL_NOT_FOUND", "proposal not found")
        row.status = "REJECTED"
        row.updated_at = datetime.utcnow()
        session.commit()
        return {"proposal": _serialize_proposal(row), "authority_mutated": False}


@router.post("/{book_id}/visual-assets/authority/authoring-proposals/{proposal_id}/approve")
def approve_visual_authoring_proposal(book_id: int, proposal_id: str, req: VisualAuthoringReviewRequest):
    if not req.confirmed:
        raise _error(409, "REVIEW_CONFIRMATION_REQUIRED", "approval requires confirmed=true")
    with Session() as session:
        proposal = session.query(VisualAuthoringProposal).filter_by(book_id=book_id, proposal_id=proposal_id).first()
        if not proposal:
            raise _error(404, "PROPOSAL_NOT_FOUND", "proposal not found")
        if proposal.status != "REVIEW_REQUIRED":
            raise _error(409, "PROPOSAL_NOT_REVIEWABLE", "only REVIEW_REQUIRED proposals can be approved")
        request = session.query(VisualAuthoringDecisionRequest).filter_by(request_id=proposal.request_id, book_id=book_id).first()
        if not request:
            raise _error(409, "AUTHORING_REQUEST_NOT_FOUND", "authoring request not found")
        reviewed = _json(proposal.proposed_fields_json, {})
        # Re-run deterministic validation against the current request snapshot.
        validation = validate_visual_authoring_proposal(reviewed, request=_serialize_request(request))
        if not validation["ok"]:
            raise _error(409, "PROPOSAL_REVALIDATION_FAILED", "proposal no longer satisfies source constraints", reason_codes=validation["reason_codes"])
        decision = VisualAuthoringDecision(
            decision_id=f"vad_{uuid.uuid4().hex}", request_id=request.request_id, book_id=book_id,
            asset_key=proposal.asset_key, asset_type=proposal.asset_type,
            decision_json=json.dumps({"proposal_id": proposal.proposal_id, "reviewed": req.reviewed_proposals or validation["normalized"], "review_notes": req.review_notes}, ensure_ascii=False),
            confirmed=1, status="APPROVED",
        )
        session.add(decision)
        proposal.status = "SUPERSEDED"
        proposal.updated_at = datetime.utcnow()
        session.commit()
        return {"decision_id": decision.decision_id, "proposal": _serialize_proposal(proposal), "authority_mutated": True, "version_created": False, "pointer_moved": False}
