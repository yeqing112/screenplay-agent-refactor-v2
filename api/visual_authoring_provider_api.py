"""Canonical provider-only visual authoring routes.

The canonical Authority router owns requests, decisions, versions and
references.  This router owns only provider proposals and their review
transition; approval creates one canonical decision row per proposed field
and never activates a version or moves a pointer.
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
from core.visual_asset_authority import VisualAssetAuthorityError, build_asset_key, fingerprint
from core.visual_authoring_provider import (
    VISUAL_AUTHORING_PROPOSAL_SCHEMA_VERSION,
    build_visual_authoring_provider_context,
    build_visual_authoring_provider_prompt,
    proposal_payload_fingerprint,
    validate_visual_authoring_proposal,
)
from models import (
    Session,
    VisualAssetVersion,
    VisualAuthoringDecision,
    VisualAuthoringDecisionRequest,
    VisualAuthoringProposal,
)


router = APIRouter(prefix="/api/books", tags=["visual-authoring-provider"])


class ProviderCanaryRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    request_id: str = Field(validation_alias=AliasChoices("request_id", "requestId"))
    model_profile_id: str = Field(validation_alias=AliasChoices("model_profile_id", "modelProfileId"))
    confirmed_provider_call: bool = Field(default=False, validation_alias=AliasChoices("confirmed_provider_call", "confirmedProviderCall"))


class ReviewRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    confirmed: bool = False
    reviewed_proposals: list[dict[str, Any]] = Field(default_factory=list, validation_alias=AliasChoices("reviewed_proposals", "reviewedProposals"))
    review_notes: str = Field(default="", validation_alias=AliasChoices("review_notes", "reviewNotes"))


def _error(status: int, code: str, message: str, **extra: Any) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message, **extra})


def _json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _canonical_key(book_id: int, asset_type: str, canonical_id: str) -> str:
    try:
        return build_asset_key(book_id=book_id, asset_type=asset_type, canonical_id=canonical_id)
    except VisualAssetAuthorityError as exc:
        raise _error(409, exc.code, exc.message)


def _request_payload(row: VisualAuthoringDecisionRequest) -> dict[str, Any]:
    free = _json(row.free_authoring_space_json, [])
    if isinstance(free, dict):
        free = list(free.keys())
    source = _json(row.source_constraints_json, [])
    if isinstance(source, dict):
        source = [{"field": key, "value": value} for key, value in source.items()]
    forbidden = _json(row.forbidden_contradictions_json, [])
    return {
        "request_id": row.request_id,
        "book_id": row.book_id,
        "asset_key": row.asset_key,
        "asset_type": row.asset_type,
        "scope": _json(row.scope_json, {}),
        "source_constraints": source if isinstance(source, list) else [],
        "free_authoring_space": [str(item) for item in free] if isinstance(free, list) else [],
        "forbidden_contradictions": forbidden if isinstance(forbidden, list) else [],
        "required_by_stage": row.required_by_stage,
    }


def _serialize_proposal(row: VisualAuthoringProposal) -> dict[str, Any]:
    return {
        "id": row.id,
        "proposal_id": row.proposal_id,
        "request_id": row.request_id,
        "book_id": row.book_id,
        "asset_key": row.asset_key,
        "asset_type": row.asset_type,
        "scope": _json(row.scope_json, {}),
        "proposed_fields": _json(row.proposed_fields_json, {}),
        "explanation_summary": row.explanation_summary,
        "source_constraint_refs": _json(row.source_constraint_refs_json, []),
        "provider": {
            "profile_id": row.provider_profile_id,
            "model": row.provider_model,
            "vendor_host": row.provider_vendor_host,
            "request_fingerprint": row.provider_request_fingerprint,
            "response_hash": row.provider_response_hash,
        },
        "validator_status": row.validator_status,
        "validator_diagnostics": _json(row.validator_diagnostics_json, {}),
        "audit": _json(row.audit_json, {}),
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.post("/{book_id}/visual-assets/authority/{asset_type}/{canonical_id}/authoring-proposals/canary")
def create_visual_authoring_proposal_canary(book_id: int, asset_type: str, canonical_id: str, req: ProviderCanaryRequest):
    if not req.confirmed_provider_call:
        raise _error(409, "PROVIDER_CALL_CONFIRMATION_REQUIRED", "provider call requires confirmed_provider_call=true", provider_calls=0)
    profile = get_profile(req.model_profile_id)
    if not profile or profile.get("capability") != "llm" or not profile.get("enabled") or not profile.get("key_configured") or not str(profile.get("model_name") or "").strip():
        raise _error(422, "INVALID_PROVIDER_PROFILE", "explicit profile must be an enabled LLM profile with credentials and a model name")
    asset_key = _canonical_key(book_id, asset_type, canonical_id)
    with Session() as session:
        request = session.query(VisualAuthoringDecisionRequest).filter_by(request_id=req.request_id, book_id=book_id).first()
        if not request:
            raise _error(404, "AUTHORING_REQUEST_NOT_FOUND", "authoring request not found")
        if request.asset_type != asset_type or request.asset_key != asset_key:
            raise _error(409, "PROPOSAL_ASSET_MISMATCH", "request is bound to a different canonical asset key")
        request_payload = _request_payload(request)
        current = session.query(VisualAssetVersion).filter_by(book_id=book_id, asset_key=asset_key).order_by(VisualAssetVersion.revision.desc()).first()
        current_authority = {"version_id": current.id, "payload_hash": current.payload_hash, "revision": current.revision, "authority_status": current.authority_status} if current else {}
        evidence = {
            "source_constraint_fingerprint": fingerprint(request_payload["source_constraints"]),
            "request_evidence_fingerprint": fingerprint({key: request_payload.get(key) for key in ("asset_key", "asset_type", "scope", "source_constraints", "free_authoring_space", "forbidden_contradictions")}),
            "current_authority": current_authority,
            "current_authority_fingerprint": fingerprint(current_authority),
        }
        context = build_visual_authoring_provider_context(request=request_payload, authoritative_context=evidence)
        system, user = build_visual_authoring_provider_prompt(context)
        request_fp = llm_request_fingerprint(system=system, user=user, profile=profile, extra={"contract": context["contract_version"], "schema": VISUAL_AUTHORING_PROPOSAL_SCHEMA_VERSION})
        existing = session.query(VisualAuthoringProposal).filter_by(request_id=request.request_id, provider_request_fingerprint=request_fp).first()
        if existing:
            return {"proposal": _serialize_proposal(existing), "llm_called": False, "provider_calls": 0, "deduplicated": True}
        audit_records: list[dict[str, Any]] = []
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
                audit_extra={"mode": "visual_authoring_provider_canary", "request_id": request.request_id, "asset_key": asset_key},
            )
        except Exception as exc:
            raise _error(502, "PROVIDER_CALL_FAILED", str(exc)[:300], provider_calls=1, audit=summarize_audit_records(audit_records))
        validation = validate_visual_authoring_proposal(raw, request=request_payload, context=context)
        normalized = validation["normalized"]
        response_hash = hashlib.sha256(canonical_json(raw).encode("utf-8")).hexdigest()
        audit = summarize_audit_records(audit_records)
        audit.update({"logical_provider_calls": 1, "request_id": request.request_id, "asset_key": asset_key, "profile_id": profile.get("id"), "provider_model": profile.get("model_name"), "request_fingerprint": request_fp, "response_hash": response_hash, "evidence": evidence})
        vendor_hosts = audit.get("vendor_hosts") or []
        audit["vendor_host"] = vendor_hosts[-1] if vendor_hosts else ""
        proposal = VisualAuthoringProposal(
            proposal_id=f"vap_{uuid.uuid4().hex}", request_id=request.request_id, book_id=book_id,
            asset_key=asset_key, asset_type=asset_type, scope_json=json.dumps(request_payload["scope"], ensure_ascii=False),
            proposed_fields_json=json.dumps(normalized, ensure_ascii=False),
            explanation_summary="；".join(normalized.get("review_notes") or [])[:2000],
            source_constraint_refs_json=json.dumps([ref for item in normalized.get("proposals", []) for ref in item.get("constraint_refs", [])], ensure_ascii=False),
            provider_profile_id=str(profile.get("id") or req.model_profile_id), provider_model=str(profile.get("model_name") or ""),
            provider_vendor_host=str(audit.get("vendor_host") or ""), provider_request_fingerprint=request_fp,
            provider_response_hash=response_hash, proposal_payload_hash=proposal_payload_fingerprint(normalized),
            validator_status="PASS" if validation["ok"] else "FAIL",
            validator_diagnostics_json=json.dumps({"reason_codes": validation.get("reason_codes", []), "diagnostics": validation.get("diagnostics", [])}, ensure_ascii=False),
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


@router.post("/{book_id}/visual-assets/authority/authoring-proposals/{proposal_id}/reject")
def reject_visual_authoring_proposal(book_id: int, proposal_id: str, req: ReviewRequest):
    if not req.confirmed:
        raise _error(409, "REVIEW_CONFIRMATION_REQUIRED", "reject requires confirmed=true")
    with Session() as session:
        row = session.query(VisualAuthoringProposal).filter_by(book_id=book_id, proposal_id=proposal_id).first()
        if not row:
            raise _error(404, "PROPOSAL_NOT_FOUND", "proposal not found")
        row.status = "REJECTED"
        row.updated_at = datetime.now()
        session.commit()
        return {"proposal": _serialize_proposal(row), "authority_mutated": False}


@router.post("/{book_id}/visual-assets/authority/authoring-proposals/{proposal_id}/approve")
def approve_visual_authoring_proposal(book_id: int, proposal_id: str, req: ReviewRequest):
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
        request_payload = _request_payload(request)
        audit = _json(proposal.audit_json, {})
        current_fp = fingerprint({key: request_payload.get(key) for key in ("asset_key", "asset_type", "scope", "source_constraints", "free_authoring_space", "forbidden_contradictions")})
        if str(_json(audit.get("evidence"), {}).get("request_evidence_fingerprint") or "") != current_fp:
            raise _error(409, "AUTHORING_REQUEST_STALE", "the evidence packet changed; create a new provider proposal")
        current = session.query(VisualAssetVersion).filter_by(book_id=book_id, asset_key=proposal.asset_key).order_by(VisualAssetVersion.revision.desc()).first()
        current_authority = {"version_id": current.id, "payload_hash": current.payload_hash, "revision": current.revision, "authority_status": current.authority_status} if current else {}
        if str(_json(audit.get("evidence"), {}).get("current_authority_fingerprint") or "") != fingerprint(current_authority):
            raise _error(409, "AUTHORING_REQUEST_STALE", "the canonical asset version changed; create a new provider proposal")
        reviewed_items = req.reviewed_proposals
        normalized = _json(proposal.proposed_fields_json, {})
        if reviewed_items:
            normalized = {**normalized, "proposals": reviewed_items}
        validation = validate_visual_authoring_proposal(normalized, request=request_payload)
        if not validation["ok"]:
            raise _error(409, "PROPOSAL_REVALIDATION_FAILED", "proposal no longer satisfies source constraints", reason_codes=validation["reason_codes"])
        decisions = []
        for item in validation["normalized"]["proposals"]:
            decision = VisualAuthoringDecision(
                decision_id=f"vad_{uuid.uuid4().hex}", request_id=request.request_id, book_id=book_id,
                asset_key=proposal.asset_key, asset_type=proposal.asset_type, field=item["field"],
                value_json=json.dumps(item["value"], ensure_ascii=False), scope_json=json.dumps(item["scope"], ensure_ascii=False),
                source_constraint_refs_json=json.dumps(item["constraint_refs"], ensure_ascii=False), author="human",
                status="APPROVED", provenance_json=json.dumps({"proposal_id": proposal.proposal_id, "review_notes": req.review_notes}, ensure_ascii=False),
                created_at=datetime.now(), updated_at=datetime.now(),
            )
            session.add(decision)
            decisions.append(decision.decision_id)
        proposal.status = "SUPERSEDED"
        proposal.updated_at = datetime.now()
        request.status = "APPROVED"
        request.resolution_json = json.dumps({"proposal_id": proposal.proposal_id, "decision_ids": decisions}, ensure_ascii=False)
        request.updated_at = datetime.now()
        session.commit()
        return {"decision_ids": decisions, "proposal": _serialize_proposal(proposal), "authority_mutated": True, "version_created": False, "pointer_moved": False, "reference_authority_mutated": False}


__all__ = ["router"]
