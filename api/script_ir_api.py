"""Deterministic ScriptIR build/confirm API."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, Field

from core.script_ir import build_script_ir, legacy_markdown_to_script_ir, script_ir_hash, validate_script_ir
from core.script_ir_authority import ScriptIRAuthorityError, activate_script_ir
from core.script_renderer import render_reader_script, render_script_markdown, render_technical_script_view
from core.script_creative_quality import run_script_creative_quality_gate
from models import FactSnapshot, Script, ScriptIRVersion, Session

router = APIRouter(prefix="/api/books", tags=["script-ir"])


class ScriptIRBuildRequest(BaseModel):
    source_outline_revision: str = Field(default="", validation_alias=AliasChoices("source_outline_revision", "sourceOutlineRevision"))
    source_fact_snapshot_id: str = Field(default="", validation_alias=AliasChoices("source_fact_snapshot_id", "sourceFactSnapshotId"))
    persist: bool = False


class ScriptIRConfirmRequest(BaseModel):
    version_id: int = Field(validation_alias=AliasChoices("version_id", "versionId"))
    confirmed: bool = False
    payload: dict[str, Any] | None = None
    enforce_creative_quality: bool = Field(default=False, validation_alias=AliasChoices("enforce_creative_quality", "enforceCreativeQuality"))


class ScriptIRCreativeQualityRequest(BaseModel):
    version_id: int | None = Field(default=None, validation_alias=AliasChoices("version_id", "versionId"))
    payload: dict[str, Any] | None = Field(default=None)


class ScriptIRActivateRequest(BaseModel):
    version_id: int = Field(validation_alias=AliasChoices("version_id", "versionId"))
    confirmed: bool = False
    fact_snapshot_id: int | None = Field(default=None, validation_alias=AliasChoices("fact_snapshot_id", "factSnapshotId"))
    source_package_id: str = Field(default="", validation_alias=AliasChoices("source_package_id", "sourcePackageId"))
    source_version_id: str = Field(default="", validation_alias=AliasChoices("source_version_id", "sourceVersionId"))
    immutable_source_raw_hash: str = Field(default="", validation_alias=AliasChoices("immutable_source_raw_hash", "immutableSourceRawHash"))
    source_evidence_index: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("source_evidence_index", "sourceEvidenceIndex"))
    source_anchor_bindings: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("source_anchor_bindings", "sourceAnchorBindings"))
    source_structure: dict[str, Any] | None = Field(default=None, validation_alias=AliasChoices("source_structure", "sourceStructure"))


def _content_hash(content: str) -> str:
    return hashlib.sha256(str(content or "").encode("utf-8")).hexdigest()


def _json_object(value: str | None, fallback: Any) -> Any:
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _payload(row: ScriptIRVersion) -> dict[str, Any]:
    try:
        parsed = json.loads(row.payload_json or "{}")
    except (TypeError, ValueError):
        parsed = {}
    try:
        report = json.loads(row.validation_report or "{}")
    except (TypeError, ValueError):
        report = {}
    return {
        "id": row.id,
        "book_id": row.book_id,
        "episode": row.episode,
        "revision": row.revision,
        "status": row.status,
        "schema_version": row.schema_version,
        "source_outline_revision": row.source_outline_revision,
        "source_fact_snapshot_id": row.source_fact_snapshot_id,
        "source_fingerprint": row.source_fingerprint,
        "payload": parsed,
        "payload_hash": row.payload_hash,
        "validation_status": row.validation_status,
        "validation_report": report,
        "authority_envelope": _json_object(getattr(row, "authority_envelope_json", "{}"), {}),
        "qualification_state": getattr(row, "qualification_state", "STRUCTURALLY_VALID"),
        "stale_status": getattr(row, "stale_status", "UNKNOWN"),
        "stale_reasons": _json_object(getattr(row, "stale_reasons", "[]"), []),
        "previous_revision_id": row.previous_revision_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _source_payload(row: Script, *, book_id: int, episode: int) -> tuple[dict[str, Any], bool]:
    raw = str(row.content or "")
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        parsed = None
    if isinstance(parsed, dict) and isinstance(parsed.get("scenes"), list):
        return build_script_ir(parsed, book_id=book_id, episode=episode), False
    return legacy_markdown_to_script_ir(raw, book_id=book_id, episode=episode), True


def _enforce_fact_coverage_gate(session: Any, source_fact_snapshot_id: str) -> None:
    """Enforce coverage only when the caller binds a persisted snapshot.

    Older creative-draft callers may omit the binding entirely.  Once a
    snapshot is explicitly supplied, an evaluated insufficient result is a
    hard production prerequisite and cannot be bypassed by confirming ScriptIR.
    """
    token = str(source_fact_snapshot_id or "").strip()
    if not token.isdigit():
        return
    row = session.query(FactSnapshot).filter_by(id=int(token)).first()
    if not row:
        return
    try:
        report = json.loads(row.validation_report or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        report = {}
    coverage = report.get("fact_coverage") if isinstance(report.get("fact_coverage"), dict) else report.get("coverage")
    if not isinstance(coverage, dict):
        return
    status = str(coverage.get("status") or "").strip()
    if status and status != "FACT_COVERAGE_SUFFICIENT":
        from fastapi import HTTPException
        raise HTTPException(status_code=409, detail={"code": "FACT_COVERAGE_INSUFFICIENT", "coverage": coverage, "script_ir_gate": {"status": "BLOCKED_PENDING_TARGETED_MISSING_FACTS", "allowed": False}})


@router.post("/{book_id}/episodes/{episode}/script-ir/build")
def build_script_ir_version(book_id: int, episode: int, req: ScriptIRBuildRequest) -> dict[str, Any]:
    with Session() as session:
        script = session.query(Script).filter_by(book_id=book_id, episode=episode).order_by(Script.id.desc()).first()
        if not script:
            raise HTTPException(status_code=404, detail="No script found for this episode.")
        ir, legacy = _source_payload(script, book_id=book_id, episode=episode)
        report = validate_script_ir(ir)
        if legacy:
            report = {**report, "status": "needs_review", "warnings": [*report.get("warnings", []), {"code": "LEGACY_RECONSTRUCTION", "message": "该 ScriptIR 由旧 Markdown 重建，需人工确认。"}]}
        source_fingerprint = _content_hash(script.content or "")
        persisted_id = None
        if req.persist:
            existing = session.query(ScriptIRVersion).filter_by(book_id=book_id, episode=episode, source_fingerprint=source_fingerprint, payload_hash=script_ir_hash(ir)).order_by(ScriptIRVersion.id.desc()).first()
            if existing:
                persisted_id = existing.id
                version = existing
            else:
                previous = session.query(ScriptIRVersion).filter_by(book_id=book_id, episode=episode).order_by(ScriptIRVersion.revision.desc(), ScriptIRVersion.id.desc()).first()
                version = ScriptIRVersion(
                    book_id=book_id, episode=episode, revision=(previous.revision + 1 if previous else 1), status="draft",
                    schema_version="script_ir_v1", source_outline_revision=req.source_outline_revision.strip(), source_fact_snapshot_id=req.source_fact_snapshot_id.strip(),
                    source_fingerprint=source_fingerprint, payload_json=json.dumps(ir, ensure_ascii=False), payload_hash=script_ir_hash(ir),
                    validation_status=report["status"], validation_report=json.dumps(report, ensure_ascii=False), previous_revision_id=previous.id if previous else None,
                    created_at=datetime.now(), updated_at=datetime.now(),
                )
                session.add(version); session.commit(); session.refresh(version); persisted_id = version.id
        else:
            version = ScriptIRVersion(book_id=book_id, episode=episode, payload_json=json.dumps(ir, ensure_ascii=False), payload_hash=script_ir_hash(ir), source_fingerprint=source_fingerprint, validation_status=report["status"], validation_report=json.dumps(report, ensure_ascii=False))
        return {
            "mode": "deterministic_script_ir",
            "llm_called": False,
            "mutated": bool(persisted_id),
            "persisted_draft_id": persisted_id,
            "legacy_reconstruction": legacy,
            "validation": report,
            # Production-facing screenplay content always uses the explicit
            # Reader timeline renderer.  Keep the legacy renderer available
            # to old direct consumers, but do not expose its grouped output
            # as the production page's screenplay.
            "rendered_markdown": render_reader_script(ir),
            "version": _payload(version) if persisted_id else {"payload": ir, "payload_hash": version.payload_hash, "source_fingerprint": source_fingerprint, "validation_status": report["status"]},
        }


@router.get("/{book_id}/episodes/{episode}/script-ir")
def get_script_ir(book_id: int, episode: int) -> dict[str, Any]:
    with Session() as session:
        row = session.query(ScriptIRVersion).filter_by(book_id=book_id, episode=episode).order_by(ScriptIRVersion.revision.desc(), ScriptIRVersion.id.desc()).first()
        if not row:
            raise HTTPException(status_code=404, detail="No ScriptIR version found for this episode.")
        return _payload(row)


@router.post("/{book_id}/episodes/{episode}/script-ir/confirm")
def confirm_script_ir(book_id: int, episode: int, req: ScriptIRConfirmRequest) -> dict[str, Any]:
    if not req.confirmed:
        raise HTTPException(status_code=409, detail="ScriptIR confirmation requires confirmed=true.")
    with Session() as session:
        draft = session.query(ScriptIRVersion).filter_by(id=req.version_id, book_id=book_id, episode=episode).first()
        script = session.query(Script).filter_by(book_id=book_id, episode=episode).order_by(Script.id.desc()).first()
        if not draft or draft.status != "draft":
            raise HTTPException(status_code=409, detail="ScriptIR draft not found or already finalized.")
        if not script or _content_hash(script.content or "") != draft.source_fingerprint:
            draft.status = "superseded"; draft.updated_at = datetime.now(); session.commit()
            raise HTTPException(status_code=409, detail="Script source changed; ScriptIR draft is stale and must be regenerated.")
        _enforce_fact_coverage_gate(session, draft.source_fact_snapshot_id)
        try:
            candidate = build_script_ir(req.payload if req.payload is not None else json.loads(draft.payload_json), book_id=book_id, episode=episode, fact_snapshot_id=draft.source_fact_snapshot_id, source_outline_revision=draft.source_outline_revision)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=409, detail=f"ScriptIR candidate is invalid: {exc}") from exc
        report = validate_script_ir(candidate)
        if report["status"] != "qualified":
            raise HTTPException(status_code=409, detail={"code": "SCRIPT_IR_NOT_QUALIFIED", "validation": report})
        # Phase A: optional Creative Quality Gate.  When enforced, a hard
        # error blocks promotion to qualified.  Soft diagnostics never block.
        if req.enforce_creative_quality:
            creative = run_script_creative_quality_gate(candidate, production=True)
            if not creative["qualified"]:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "SCRIPT_CREATIVE_QUALITY_BLOCKED",
                        "message": "剧本未通过专业质量闸门（Phase A）。",
                        "creative_quality": {
                            "status": creative["status"],
                            "hard_errors": creative["hard_errors"],
                            "soft_diagnostics": creative["soft_diagnostics"],
                        },
                    },
                )
        previous = session.query(ScriptIRVersion).filter_by(book_id=book_id, episode=episode, status="qualified").order_by(ScriptIRVersion.revision.desc(), ScriptIRVersion.id.desc()).first()
        if previous:
            previous.status = "superseded"; previous.updated_at = datetime.now()
        draft.status = "qualified"; draft.payload_json = json.dumps(candidate, ensure_ascii=False); draft.payload_hash = script_ir_hash(candidate); draft.validation_status = "qualified"; draft.validation_report = json.dumps(report, ensure_ascii=False); draft.updated_at = datetime.now(); session.commit(); session.refresh(draft)
        script.current_script_ir_version_id = draft.id; script.quality_status = "qualified"; script.workflow_profile = "production"; script.production_status = "blocked"; session.commit()
        rendered = render_reader_script(candidate, production=bool(req.enforce_creative_quality))
        return {"confirmed": True, "mutated": True, "script_ir": _payload(draft), "rendered_markdown": rendered, "production_status": "blocked"}


@router.post("/{book_id}/episodes/{episode}/script-ir/creative-quality")
def script_ir_creative_quality(book_id: int, episode: int, req: ScriptIRCreativeQualityRequest) -> dict[str, Any]:
    """Run the read-only Script Creative Quality Gate on a candidate.

    Never writes a version or moves a pointer.  The payload is either supplied
    directly or resolved from an existing draft.
    """
    with Session() as session:
        if req.payload is not None:
            candidate = build_script_ir(req.payload, book_id=book_id, episode=episode)
        else:
            if req.version_id is None:
                raise HTTPException(status_code=409, detail="Provide version_id or payload to evaluate.")
            draft = session.query(ScriptIRVersion).filter_by(id=req.version_id, book_id=book_id, episode=episode).first()
            if not draft:
                raise HTTPException(status_code=404, detail="ScriptIR version not found.")
            try:
                candidate = json.loads(draft.payload_json or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                raise HTTPException(status_code=409, detail="ScriptIR payload is invalid.")
        creative = run_script_creative_quality_gate(candidate, production=True)
        return {
            "book_id": book_id,
            "episode": episode,
            "mode": "readonly_creative_quality",
            "mutated": False,
            "creative_quality": creative,
            "reader_script_preview": render_reader_script(candidate)[:600],
            "technical_view_available": True,
        }


@router.post("/{book_id}/episodes/{episode}/script-ir/activate")
def activate_script_ir_version(book_id: int, episode: int, req: ScriptIRActivateRequest) -> dict[str, Any]:
    """Bind a reviewed ScriptIR draft to immutable source and Fact authority."""

    if not req.confirmed:
        raise HTTPException(status_code=409, detail={"code": "SCRIPT_IR_ACTIVATION_CONFIRMATION_REQUIRED", "message": "ScriptIR authority activation requires confirmed=true."})
    with Session() as session:
        draft = session.query(ScriptIRVersion).filter_by(id=req.version_id, book_id=book_id, episode=episode, status="draft").first()
        script = session.query(Script).filter_by(book_id=book_id, episode=episode).order_by(Script.id.desc()).first()
        if not draft or not script:
            raise HTTPException(status_code=409, detail={"code": "SCRIPT_IR_ACTIVATION_TARGET_INVALID", "message": "ScriptIR draft or script source not found."})
        snapshot_id = req.fact_snapshot_id if req.fact_snapshot_id is not None else (int(draft.source_fact_snapshot_id) if str(draft.source_fact_snapshot_id).isdigit() else None)
        snapshot = session.query(FactSnapshot).filter_by(id=snapshot_id).first() if snapshot_id is not None else None
        source_structure = req.source_structure
        if source_structure is None:
            try:
                parsed = json.loads(script.content or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                parsed = {}
            source_structure = parsed if isinstance(parsed, dict) else {}
        try:
            return activate_script_ir(session=session, script_row=script, draft_row=draft, source_structure=source_structure, source_package_id=req.source_package_id, source_version_id=req.source_version_id, immutable_source_raw_hash=req.immutable_source_raw_hash, source_evidence_index=req.source_evidence_index, source_anchor_bindings=req.source_anchor_bindings, fact_snapshot_row=snapshot)
        except ScriptIRAuthorityError as exc:
            raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc), **exc.details}) from exc

