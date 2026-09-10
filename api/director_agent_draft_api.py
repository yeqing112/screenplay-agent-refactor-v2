"""Review-first Smart Director LLM draft endpoints.

Preview is pure/read-only. Invoke is intentionally guarded by two explicit
consents and can only create Agent session/plan/audit records; it cannot touch
production content or generation task tables.
"""
from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import asyncio
import time
import uuid
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

import core.llm as llm_client
from core.agent_model_config import get_agent_model_profile_for_invocation, read_agent_runtime_policy
from core.director_agent_draft import AGENT_DRAFT_REQUIRED_KEYS, build_agent_draft_preview
from core.director_agent_evidence import build_project_evidence
from core.director_tool_registry import list_tools
from core.director_tool_registry import resolve_tool
from core.director_agent_budget import check_budget, read_budget, write_budget
from core.agent_project_updates import derive_project_updates, project_status_summary
from core.agent_chat import CHAT_REQUIRED_KEYS, build_agent_chat_prompt, normalize_chat_result
from core.prompt_cache import summarize_audit_records
import config
from models import AgentAttachment, AgentAuditLog, AgentMessage, AgentPlan, AgentSession, AgentProjectUpdate, Book, Session

router = APIRouter(prefix="/api/agent", tags=["smart-director"])
logger = logging.getLogger(__name__)


def _int(value: Any) -> int | None:
    try:
        parsed = int(value)
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None


class AgentDraftRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    objective: str = ""
    plan: dict[str, Any]
    draft_fingerprint: str = Field(default="", validation_alias=AliasChoices("draft_fingerprint", "draftFingerprint"))
    confirmed: bool = False
    allow_external_call: bool = Field(default=False, validation_alias=AliasChoices("allow_external_call", "allowExternalCall"))
    attachment_ids: list[int] = Field(default_factory=list, validation_alias=AliasChoices("attachment_ids", "attachmentIds"))
    session_id: int | None = Field(default=None, validation_alias=AliasChoices("session_id", "sessionId"))

class AgentBudgetRequest(BaseModel):
    max_estimated_tokens: int = Field(validation_alias=AliasChoices("max_estimated_tokens", "maxEstimatedTokens"))


class AgentMessageRequest(BaseModel):
    role: str = "user"
    content: str = ""
    attachment_ids: list[int] = Field(default_factory=list, validation_alias=AliasChoices("attachment_ids", "attachmentIds"))


class AgentSessionRequest(BaseModel):
    book_id: int = Field(validation_alias=AliasChoices("book_id", "bookId"))
    user_prompt: str = Field(default="", validation_alias=AliasChoices("user_prompt", "userPrompt"))


class AgentProjectUpdateReconcileRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    book_id: int = Field(validation_alias=AliasChoices("book_id", "bookId"))
    scope: dict[str, Any] = Field(default_factory=dict)


class AgentProjectUpdateStateRequest(BaseModel):
    status: str


class AgentChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    book_id: int = Field(validation_alias=AliasChoices("book_id", "bookId"))
    message: str = ""
    scope: dict[str, Any] = Field(default_factory=dict)
    attachment_ids: list[int] = Field(default_factory=list, validation_alias=AliasChoices("attachment_ids", "attachmentIds"))
    session_id: int | None = Field(default=None, validation_alias=AliasChoices("session_id", "sessionId"))


@router.post("/sessions")
def create_agent_session(req: AgentSessionRequest) -> dict[str, Any]:
    if not req.user_prompt.strip():
        raise HTTPException(status_code=400, detail="会话需要一条非空消息")
    with Session() as session:
        if not session.get(Book, req.book_id):
            raise HTTPException(status_code=404, detail="项目不存在")
        row = AgentSession(book_id=req.book_id, user_prompt=req.user_prompt[:4000], status="draft")
        session.add(row); session.flush()
        session.add(AgentMessage(session_id=row.id, role="user", content=req.user_prompt[:50000], attachment_ids="[]"))
        session.commit(); session.refresh(row)
        return {"session_id": row.id, "status": row.status, "mutated": True}


@router.get("/sessions/{session_id}/messages")
def list_agent_messages(session_id: int) -> dict[str, Any]:
    with Session() as session:
        if not session.get(AgentSession, session_id):
            raise HTTPException(status_code=404, detail="智能导演台会话不存在")
        rows = session.query(AgentMessage).filter_by(session_id=session_id).order_by(AgentMessage.id.asc()).limit(200).all()
    return {"messages": [{"id": row.id, "role": row.role, "content": row.content, "attachment_ids": json.loads(row.attachment_ids or "[]"), "created_at": row.created_at.isoformat() if row.created_at else None} for row in rows], "mutated": False}


@router.get("/sessions/{session_id}/state")
def get_agent_session_state(session_id: int) -> dict[str, Any]:
    """Restore a reviewable conversation state without executing anything."""
    with Session() as session:
        agent_session = session.get(AgentSession, session_id)
        if not agent_session:
            raise HTTPException(status_code=404, detail="智能导演台会话不存在")
        messages = session.query(AgentMessage).filter_by(session_id=session_id).order_by(AgentMessage.id.asc()).limit(200).all()
        plan_row = session.query(AgentPlan).filter_by(session_id=session_id).order_by(AgentPlan.id.desc()).first()
    plan = None
    if plan_row:
        steps = json.loads(plan_row.steps or "[]")
        counts = {"A": 0, "B": 0, "C": 0, "D": 0}
        for step in steps:
            tier = str(step.get("tier") or "A") if isinstance(step, dict) else "A"
            if tier in counts: counts[tier] += 1
        plan = {
            "objective": plan_row.objective, "scope": json.loads(plan_row.scope or "{}"),
            "scope_key": "", "evidence_snapshot": json.loads(plan_row.evidence_snapshot or "{}"),
            "steps": steps, "tier_counts": counts,
            "preconditions": json.loads(plan_row.preconditions or "[]"),
            "blocking_issues": json.loads(plan_row.blocking_issues or "[]"),
            "approval_policy": json.loads(plan_row.approval_policy or "{}"),
            "cost_envelope": json.loads(plan_row.cost_envelope or "{}"),
            "rollback_anchor": json.loads(plan_row.rollback_anchor or "{}"),
            "status": plan_row.status, "auto_executable": counts["C"] + counts["D"] == 0,
            "plan_fingerprint": plan_row.plan_fingerprint,
        }
    return {"session": {"id": agent_session.id, "status": agent_session.status}, "messages": [{"id": row.id, "role": row.role, "content": row.content, "attachment_ids": json.loads(row.attachment_ids or "[]"), "created_at": row.created_at.isoformat() if row.created_at else None} for row in messages], "plan": plan, "mutated": False}


@router.get("/sessions")
def list_agent_sessions(book_id: int = Query(alias="bookId", gt=0), limit: int = Query(default=10, ge=1, le=30)) -> dict[str, Any]:
    with Session() as session:
        rows = session.query(AgentSession).filter_by(book_id=book_id).order_by(AgentSession.updated_at.desc(), AgentSession.id.desc()).limit(limit).all()
    return {"sessions": [{"id": row.id, "status": row.status, "user_prompt": row.user_prompt[:400], "created_at": row.created_at.isoformat() if row.created_at else None, "updated_at": row.updated_at.isoformat() if row.updated_at else None} for row in rows], "mutated": False}


@router.post("/sessions/{session_id}/messages")
def append_agent_message(session_id: int, req: AgentMessageRequest) -> dict[str, Any]:
    if req.role not in {"user", "assistant", "system"} or not req.content.strip():
        raise HTTPException(status_code=400, detail="消息角色或内容无效")
    with Session() as session:
        agent_session = session.get(AgentSession, session_id)
        if not agent_session:
            raise HTTPException(status_code=404, detail="智能导演台会话不存在")
        attachment_ids = sorted({int(item) for item in req.attachment_ids if int(item) > 0})
        if attachment_ids:
            attachments = session.query(AgentAttachment).filter(
                AgentAttachment.id.in_(attachment_ids),
                AgentAttachment.book_id == agent_session.book_id,
                AgentAttachment.status == "ready",
            ).all()
            valid_ids = {row.id for row in attachments}
            if valid_ids != set(attachment_ids):
                raise HTTPException(status_code=409, detail="附件不属于当前项目或已不可用")
        row = AgentMessage(session_id=session_id, role=req.role, content=req.content[:50000], attachment_ids=json.dumps(attachment_ids[:6]))
        session.add(row)
        agent_session.updated_at = datetime.now()
        session.commit(); session.refresh(row)
        return {"message": {"id": row.id, "role": row.role, "content": row.content, "attachment_ids": attachment_ids[:6], "created_at": row.created_at.isoformat() if row.created_at else None}, "mutated": True}


AGENT_ATTACHMENT_MAX_COUNT = 6
AGENT_ATTACHMENT_MAX_IMAGE_BYTES = 20 * 1024 * 1024
AGENT_ATTACHMENT_MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
AGENT_ATTACHMENT_DOCUMENT_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}
AGENT_ATTACHMENT_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def _safe_attachment_filename(filename: str | None) -> str:
    raw = str(filename or "").replace("\\", "/").split("/")[-1].strip()
    name = config.sanitize_filename(raw)
    if not name or len(name) > 180:
        raise HTTPException(status_code=400, detail="附件文件名无效")
    if Path(name).suffix.lower() not in AGENT_ATTACHMENT_DOCUMENT_EXTENSIONS | AGENT_ATTACHMENT_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="仅支持 PNG、JPG、WEBP、TXT、MD、PDF、DOCX 附件")
    return name


def _extract_document_text(content: bytes, suffix: str) -> tuple[str, str]:
    """Extract bounded text without trusting document instructions as system rules."""
    try:
        if suffix in {".txt", ".md"}:
            return content.decode("utf-8", errors="replace")[:24000], "extracted"
        if suffix == ".docx":
            with zipfile.ZipFile(BytesIO(content)) as archive:
                xml = archive.read("word/document.xml").decode("utf-8", errors="replace")
            # XML is data, not code; preserve paragraph breaks for later review.
            text = xml.replace("</w:p>", "\n")
            import re
            text = re.sub(r"<[^>]+>", "", text)
            return text[:24000], "extracted"
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader
                reader = PdfReader(BytesIO(content))
                return "\n".join((page.extract_text() or "") for page in reader.pages)[:24000], "extracted"
            except Exception:
                return "", "unavailable"
    except Exception:
        return "", "failed"
    return "", "unavailable"


def _attachment_summary(row: AgentAttachment, *, include_text: bool = False) -> dict[str, Any]:
    summary = {
        "id": row.id, "filename": row.original_filename, "kind": row.kind,
        "mime_type": row.mime_type, "size_bytes": row.size_bytes,
        "sha256": row.sha256, "extraction_status": row.extraction_status,
        "status": row.status,
    }
    if include_text and row.kind == "document" and row.extracted_text:
        summary["untrusted_extracted_text"] = row.extracted_text[:12000]
    return summary


def _load_request_attachments(book_id: int, attachment_ids: list[int]) -> list[dict[str, Any]]:
    normalized = sorted({int(item) for item in attachment_ids if int(item) > 0})
    if len(normalized) > AGENT_ATTACHMENT_MAX_COUNT:
        raise HTTPException(status_code=400, detail=f"每次对话最多附加 {AGENT_ATTACHMENT_MAX_COUNT} 个资料")
    if not normalized:
        return []
    with Session() as session:
        rows = session.query(AgentAttachment).filter(
            AgentAttachment.book_id == book_id,
            AgentAttachment.id.in_(normalized),
            AgentAttachment.status == "ready",
        ).all()
    if len(rows) != len(normalized):
        raise HTTPException(status_code=409, detail="部分附件已失效、被移除或不属于当前项目，请重新选择")
    return [_attachment_summary(row, include_text=True) for row in sorted(rows, key=lambda item: item.id)]


def _load_vision_inputs(book_id: int, attachment_ids: list[int], profile: dict[str, Any], *, vision_enabled: bool = False) -> list[str]:
    """Create in-memory data URLs only for an explicitly vision-capable model.

    Nothing is uploaded or persisted here. The caller has already passed the
    two explicit external-call confirmations by the time this runs.
    """
    if not vision_enabled or not bool((profile.get("default_params") or {}).get("supports_vision", False)):
        return []
    with Session() as session:
        rows = session.query(AgentAttachment).filter(
            AgentAttachment.book_id == book_id, AgentAttachment.id.in_(attachment_ids or [-1]),
            AgentAttachment.kind == "image", AgentAttachment.status == "ready",
        ).order_by(AgentAttachment.id).all()
    inputs = []
    for row in rows:
        try:
            content = Path(row.storage_key).read_bytes()
            if content and len(content) <= AGENT_ATTACHMENT_MAX_IMAGE_BYTES:
                import base64
                inputs.append(f"data:{row.mime_type};base64," + base64.b64encode(content).decode("ascii"))
        except OSError:
            continue
    return inputs


@router.post("/attachments")
def upload_agent_attachment(book_id: int = Query(alias="bookId", gt=0), file: UploadFile = File(...)) -> dict[str, Any]:
    """Store a private chat attachment. Uploading never invokes an LLM or publishes media."""
    filename = _safe_attachment_filename(file.filename)
    suffix = Path(filename).suffix.lower()
    max_bytes = AGENT_ATTACHMENT_MAX_IMAGE_BYTES if suffix in AGENT_ATTACHMENT_IMAGE_EXTENSIONS else AGENT_ATTACHMENT_MAX_DOCUMENT_BYTES
    content = file.file.read(max_bytes + 1)
    if not content:
        raise HTTPException(status_code=400, detail="附件为空")
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"附件过大，最大允许 {max_bytes // 1024 // 1024}MB")
    if suffix == ".pdf" and not content.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="PDF 文件内容无效")
    if suffix == ".docx" and not content.startswith(b"PK"):
        raise HTTPException(status_code=400, detail="DOCX 文件内容无效")
    if suffix == ".png" and not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(status_code=400, detail="PNG 图片内容无效")
    if suffix in {".jpg", ".jpeg"} and not content.startswith(b"\xff\xd8\xff"):
        raise HTTPException(status_code=400, detail="JPG 图片内容无效")
    if suffix == ".webp" and not (content.startswith(b"RIFF") and content[8:12] == b"WEBP"):
        raise HTTPException(status_code=400, detail="WEBP 图片内容无效")
    with Session() as session:
        if not session.get(Book, book_id):
            raise HTTPException(status_code=404, detail="项目不存在")
    kind = "image" if suffix in AGENT_ATTACHMENT_IMAGE_EXTENSIONS else "document"
    extracted_text, extraction_status = _extract_document_text(content, suffix) if kind == "document" else ("", "not_applicable")
    storage_dir = (config.UPLOAD_DIR / "agent-attachments" / f"book-{book_id}").resolve()
    storage_dir.mkdir(parents=True, exist_ok=True)
    storage_key = (storage_dir / f"{uuid.uuid4().hex}{suffix}").resolve()
    try:
        storage_key.relative_to(storage_dir)
    except ValueError as exc:  # pragma: no cover - defensive boundary
        raise HTTPException(status_code=400, detail="附件存储路径无效") from exc
    storage_key.write_bytes(content)
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    with Session() as session:
        row = AgentAttachment(book_id=book_id, original_filename=filename, mime_type=mime_type, kind=kind,
                              size_bytes=len(content), storage_key=str(storage_key), sha256=hashlib.sha256(content).hexdigest(),
                              extraction_status=extraction_status, extracted_text=extracted_text, status="ready")
        session.add(row); session.commit(); session.refresh(row)
        return {"attachment": _attachment_summary(row), "llm_called": False, "mutated": True}


@router.get("/attachments")
def list_agent_attachments(book_id: int = Query(alias="bookId", gt=0)) -> dict[str, Any]:
    with Session() as session:
        rows = session.query(AgentAttachment).filter_by(book_id=book_id, status="ready").order_by(AgentAttachment.id.desc()).limit(50).all()
    return {"attachments": [_attachment_summary(row) for row in rows], "mutated": False}


@router.get("/attachments/{attachment_id}/content")
def get_agent_attachment_content(attachment_id: int, book_id: int = Query(alias="bookId", gt=0)):
    with Session() as session:
        row = session.query(AgentAttachment).filter_by(id=attachment_id, book_id=book_id, status="ready").first()
    if not row or not row.storage_key or not Path(row.storage_key).is_file():
        raise HTTPException(status_code=404, detail="附件不存在")
    return FileResponse(row.storage_key, media_type=row.mime_type, filename=row.original_filename)


@router.get("/tools")
def list_agent_tools() -> dict[str, Any]:
    """Read the one authoritative permission registry; never executes tools."""
    return {"tools": list_tools(), "mutated": False}


@router.post("/chat")
def chat_with_agent(req: AgentChatRequest) -> dict[str, Any]:
    """Free-form assistant turn.

    Read-only conversation is handled immediately.  If the model proposes a
    side effect, the response contains a structured action proposal only; no
    domain write or media task is started by this endpoint.
    """
    message = str(req.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="消息不能为空")
    scope = dict(req.scope or {})
    scope["book_id"] = req.book_id
    try:
        evidence = build_project_evidence(scope)
        attachments = _load_request_attachments(req.book_id, req.attachment_ids)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    with Session() as session:
        if not session.get(Book, req.book_id):
            raise HTTPException(status_code=404, detail="项目不存在")
        agent_session = session.get(AgentSession, req.session_id) if req.session_id else None
        if agent_session and agent_session.book_id != req.book_id:
            raise HTTPException(status_code=409, detail="会话不属于当前项目")
        if not agent_session:
            agent_session = AgentSession(book_id=req.book_id, user_prompt=message[:4000], status="running", evidence_fingerprint="")
            session.add(agent_session)
            session.flush()
        history_rows = session.query(AgentMessage).filter_by(session_id=agent_session.id).order_by(AgentMessage.id.asc()).limit(20).all()
        history = [{"role": row.role, "content": row.content[:4000]} for row in history_rows]
        user_row = AgentMessage(session_id=agent_session.id, role="user", content=message[:50000], attachment_ids=json.dumps([item.get("id") for item in attachments], ensure_ascii=False))
        session.add(user_row)
        session.flush()
        session_id = agent_session.id
        session.commit()

    updates = derive_project_updates(evidence)
    fallback = project_status_summary(evidence, updates).get("next_action") or "我已读取当前项目状态，可以继续为你分析。"
    fallback_reply = f"我已读取项目事实。当前最值得关注的是：{fallback}。如果你希望我修改内容或提交生成，我会先给出具体动作和影响，等你确认后再执行。"
    profile = get_agent_model_profile_for_invocation()
    normalized = normalize_chat_result(None, fallback_reply=fallback_reply)
    llm_called = False
    if profile:
        try:
            system_prompt, user_prompt = build_agent_chat_prompt(message, evidence, history, attachments)
            runtime_policy = read_agent_runtime_policy()
            effective_profile = dict(profile)
            effective_params = dict((profile or {}).get("default_params") or {})
            effective_params["thinking"] = {"type": runtime_policy.get("thinking", "disabled")}
            effective_profile["default_params"] = effective_params
            audit_records: list[dict[str, Any]] = []
            result = llm_client.call_llm_json(
                user_prompt,
                system=system_prompt,
                model_profile=effective_profile,
                required_keys=CHAT_REQUIRED_KEYS,
                estimated_tokens=2500,
                retries=1,
                json_parse_retries=0,
                image_data_urls=_load_vision_inputs(req.book_id, req.attachment_ids, profile, vision_enabled=bool(runtime_policy.get("vision_enabled"))),
                audit_callback=audit_records.append,
                audit_extra={"mode": "agent_chat"},
            )
            normalized = normalize_chat_result(result, fallback_reply=fallback_reply)
            llm_called = True
        except Exception as exc:
            logger.warning("Smart Director chat fell back to deterministic response: %s", exc)
            audit_records = locals().get("audit_records", [])
    else:
        audit_records = []

    operation = "chat_turn"
    proposed_operation = str((normalized.get("action_proposal") or {}).get("operation") or "")
    tool_tier = resolve_tool(proposed_operation)["tier"] if normalized["requires_confirmation"] and proposed_operation else "A"
    status = "awaiting_confirmation" if normalized["requires_confirmation"] else "completed"
    with Session() as session:
        agent_session = session.get(AgentSession, session_id)
        agent_session.status = status
        agent_session.evidence_fingerprint = hashlib.sha256(json.dumps(evidence, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        agent_session.updated_at = datetime.now()
        assistant = AgentMessage(session_id=session_id, role="assistant", content=normalized["reply"], attachment_ids="[]")
        session.add(assistant)
        audit_row = AgentAuditLog(
            session_id=session_id,
            operation=operation,
            tool_tier=tool_tier,
            evidence_fingerprint=agent_session.evidence_fingerprint,
            plan_fingerprint="",
            model_info=json.dumps({"profile_id": (profile or {}).get("id", ""), "llm_called": llm_called, "llm_request_audit": summarize_audit_records(audit_records)}, ensure_ascii=False),
            request_payload=json.dumps({
                "intent": normalized["intent"],
                "attachment_ids": req.attachment_ids[:6],
                # Keep the navigation context as audit data only.  It is used
                # to open the existing workbench after user confirmation; it
                # is never an execution shortcut.
                "scope": scope,
                "request_fingerprint": summarize_audit_records(audit_records).get("last_request_fingerprint", ""),
            }, ensure_ascii=False),
            response_payload=json.dumps(normalized, ensure_ascii=False),
            confirmation_user="",
            confirmation_at=None,
            result_status=status,
            result_message="普通对话已直接回复；动作提案尚未执行。" if normalized["requires_confirmation"] else "普通对话已直接回复。",
        )
        audit_summary = summarize_audit_records(audit_records)
        audit_row.request_fingerprint = str(audit_summary.get("last_request_fingerprint") or "")
        audit_row.llm_usage = json.dumps({key: audit_summary.get(key) for key in ("prompt_tokens", "cached_tokens", "completion_tokens", "total_tokens", "cache_hit_rate", "last_latency_ms")}, ensure_ascii=False)
        session.add(audit_row)
        session.flush()
        audit_id = audit_row.id
        session.commit()
    return {
        "session_id": session_id,
        "message": {"role": "assistant", "content": normalized["reply"], "attachment_ids": []},
        "intent": normalized["intent"],
        "requires_confirmation": normalized["requires_confirmation"],
        "action_proposal": normalized["action_proposal"],
        "audit_id": audit_id,
        "updates": updates,
        "llm_called": llm_called,
        "mutated": True,
    }


def _serialize_project_update(row: AgentProjectUpdate) -> dict[str, Any]:
    try:
        source_refs = json.loads(row.source_refs or "[]")
    except (TypeError, json.JSONDecodeError):
        source_refs = []
    try:
        action_proposal = json.loads(row.action_proposal or "{}")
    except (TypeError, json.JSONDecodeError):
        action_proposal = {}
    return {
        "id": row.id,
        "book_id": row.book_id,
        "type": row.type,
        "severity": row.severity,
        "title": row.title,
        "message": row.message,
        "source_refs": source_refs,
        "evidence_fingerprint": row.evidence_fingerprint,
        "action_proposal": action_proposal,
        "requires_confirmation": bool(row.requires_confirmation),
        "status": row.status,
        "dedupe_key": row.dedupe_key,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.post("/updates/reconcile")
def reconcile_agent_project_updates(req: AgentProjectUpdateReconcileRequest) -> dict[str, Any]:
    """Reconcile proactive updates against a fresh server-authoritative snapshot.

    Repeating the same snapshot is idempotent and never creates a duplicate
    notification.  The browser may provide a scope, but evidence and
    fingerprints are always rebuilt on the server.
    """
    scope = dict(req.scope or {})
    scope["book_id"] = req.book_id
    try:
        evidence = build_project_evidence(scope)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    proposals = derive_project_updates(evidence)
    created: list[dict[str, Any]] = []
    reused: list[dict[str, Any]] = []
    with Session() as session:
        for proposal in proposals:
            existing = session.query(AgentProjectUpdate).filter(
                AgentProjectUpdate.book_id == req.book_id,
                AgentProjectUpdate.dedupe_key == proposal["dedupe_key"],
            ).order_by(AgentProjectUpdate.id.desc()).first()
            if existing and existing.evidence_fingerprint == proposal["evidence_fingerprint"]:
                reused.append(_serialize_project_update(existing))
                continue
            if existing and existing.type == "action_proposal" and existing.status not in {"resolved", "dismissed", "expired"}:
                existing.status = "expired"
                existing.updated_at = datetime.now()
            row = AgentProjectUpdate(
                book_id=req.book_id,
                type=proposal["type"],
                severity=proposal["severity"],
                title=proposal["title"],
                message=proposal["message"],
                source_refs=json.dumps(proposal["source_refs"], ensure_ascii=False),
                evidence_fingerprint=proposal["evidence_fingerprint"],
                action_proposal=json.dumps(proposal["action_proposal"], ensure_ascii=False),
                requires_confirmation=1 if proposal["requires_confirmation"] else 0,
                status="unread",
                dedupe_key=proposal["dedupe_key"],
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            session.add(row)
            session.flush()
            created.append(_serialize_project_update(row))
        session.commit()
    all_updates = [*created, *reused]
    summary = project_status_summary(evidence, all_updates)
    return {
        "updates": all_updates,
        "created_count": len(created),
        "reused_count": len(reused),
        "summary": summary,
        "evidence_fingerprint": summary["evidence_fingerprint"],
        "mutated": bool(created),
    }


@router.get("/updates/summary")
def get_agent_project_update_summary(book_id: int = Query(alias="bookId", gt=0)) -> dict[str, Any]:
    """Return durable project updates without creating new ones."""
    with Session() as session:
        rows = session.query(AgentProjectUpdate).filter_by(book_id=book_id).order_by(AgentProjectUpdate.id.desc()).limit(50).all()
    updates = [_serialize_project_update(row) for row in rows]
    unread = sum(1 for row in updates if row["status"] == "unread")
    blocking = sum(1 for row in updates if row["status"] not in {"resolved", "dismissed", "expired"} and row["severity"] in {"critical", "blocking"})
    return {"book_id": book_id, "updates": updates, "unread_count": unread, "blocking_count": blocking, "mutated": False}


@router.get("/updates")
def list_agent_project_updates(
    book_id: int = Query(alias="bookId", gt=0),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    with Session() as session:
        query = session.query(AgentProjectUpdate).filter_by(book_id=book_id)
        if status:
            query = query.filter_by(status=status)
        rows = query.order_by(AgentProjectUpdate.id.desc()).limit(limit).all()
    return {"book_id": book_id, "updates": [_serialize_project_update(row) for row in rows], "mutated": False}


@router.get("/updates/stream")
def stream_agent_project_updates(
    book_id: int = Query(alias="bookId", gt=0),
    since_id: int = Query(default=0, alias="sinceId", ge=0),
    wait_ms: int = Query(default=25000, alias="waitMs", ge=0, le=30000),
):
    """Read-only SSE stream for newly persisted project updates.

    The stream never reconciles or creates records.  It waits for at most
    ``waitMs`` and then closes with a heartbeat so browsers can reconnect;
    clients that cannot use EventSource continue using the existing polling
    endpoints.
    """
    async def event_stream():
        deadline = time.monotonic() + (wait_ms / 1000)
        while True:
            with Session() as session:
                rows = session.query(AgentProjectUpdate).filter(
                    AgentProjectUpdate.book_id == book_id,
                    AgentProjectUpdate.id > since_id,
                ).order_by(AgentProjectUpdate.id.asc()).limit(50).all()
            if rows:
                for row in rows:
                    payload = json.dumps(_serialize_project_update(row), ensure_ascii=False)
                    yield f"id: {row.id}\nevent: project_update\ndata: {payload}\n\n"
                return
            if wait_ms <= 0 or time.monotonic() >= deadline:
                yield ": heartbeat\nevent: heartbeat\ndata: {}\n\n"
                return
            await asyncio.sleep(1)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/updates/{update_id}/state")
def update_agent_project_update_state(update_id: int, req: AgentProjectUpdateStateRequest) -> dict[str, Any]:
    if req.status not in {"acknowledged", "resolved", "dismissed", "snoozed"}:
        raise HTTPException(status_code=400, detail="仅支持 acknowledged、resolved、dismissed、snoozed 状态")
    with Session() as session:
        row = session.get(AgentProjectUpdate, update_id)
        if not row:
            raise HTTPException(status_code=404, detail="项目动态不存在")
        if row.status == "expired":
            raise HTTPException(status_code=409, detail="该项目动态的证据已过期，不能继续操作")
        row.status = req.status
        row.updated_at = datetime.now()
        session.commit()
        session.refresh(row)
        return {"update": _serialize_project_update(row), "mutated": True}

@router.get("/budget")
def get_agent_budget() -> dict[str, Any]: return {**read_budget(), "mutated": False}

@router.put("/budget")
def put_agent_budget(req: AgentBudgetRequest) -> dict[str, Any]:
    try: return {**write_budget(req.max_estimated_tokens), "mutated": True}
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc


def _preview_or_400(req: AgentDraftRequest) -> dict[str, Any]:
    profile = get_agent_model_profile_for_invocation()
    if not profile:
        raise HTTPException(status_code=409, detail="尚未配置可用的智能导演台 LLM，请在模型管理中单独保存 Agent 模型")
    try:
        # The browser's evidence only describes UI context. Replace it with a
        # server-frozen project snapshot before calculating any fingerprint.
        server_plan = dict(req.plan)
        server_plan.pop("plan_fingerprint", None)
        server_plan["evidence_snapshot"] = build_project_evidence(server_plan.get("scope") or {})
        book_id = _book_id(server_plan)
        attachments = _load_request_attachments(book_id, req.attachment_ids)
        return build_agent_draft_preview(objective=req.objective, plan=server_plan, profile=profile, attachments=attachments, runtime_policy=read_agent_runtime_policy())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/llm-drafts/preview")
def preview_agent_draft(req: AgentDraftRequest) -> dict[str, Any]:
    """Return the exact candidate prompt.  Never invokes a model or writes DB."""
    preview = _preview_or_400(req)
    return {"preview": preview, "budget": check_budget(preview["estimated_tokens"]), "llm_called": False, "mutated": False}


def _book_id(plan: dict[str, Any]) -> int:
    scope = plan.get("scope") if isinstance(plan.get("scope"), dict) else {}
    try:
        book_id = int(scope.get("book_id") or 0)
    except (TypeError, ValueError):
        book_id = 0
    if book_id <= 0:
        raise HTTPException(status_code=400, detail="真实 Agent 草案必须绑定一个有效项目")
    with Session() as session:
        if not session.get(Book, book_id):
            raise HTTPException(status_code=404, detail="项目不存在，不能创建 Agent 草案")
    return book_id


def _persist_agent_draft_failure(book_id: int, preview: dict[str, Any], plan: dict[str, Any], error: Exception) -> None:
    """Record a bounded failed attempt; never retries a billable call itself."""
    with Session() as session:
        agent_session = AgentSession(book_id=book_id, user_prompt=str(preview["evidence"].get("objective") or ""), status="blocked", evidence_fingerprint=preview["evidence_fingerprint"])
        session.add(agent_session)
        session.flush()
        agent_plan = AgentPlan(session_id=agent_session.id, plan_fingerprint=preview["plan_fingerprint"], objective=str(preview["evidence"].get("objective") or ""), scope=json.dumps(preview["evidence"].get("scope") or {}, ensure_ascii=False), evidence_snapshot=json.dumps(preview["evidence"], ensure_ascii=False), steps=json.dumps(plan.get("steps") or [], ensure_ascii=False), status="blocked")
        session.add(agent_plan)
        session.flush()
        attachment_ids = [item.get("id") for item in preview["evidence"].get("attachments", []) if isinstance(item, dict) and isinstance(item.get("id"), int)]
        if attachment_ids:
            session.query(AgentAttachment).filter(AgentAttachment.book_id == book_id, AgentAttachment.id.in_(attachment_ids)).update({"session_id": agent_session.id}, synchronize_session=False)
        session.add(AgentAuditLog(session_id=agent_session.id, plan_id=agent_plan.id, operation="generate_llm_draft", tool_tier="D", evidence_fingerprint=preview["evidence_fingerprint"], plan_fingerprint=preview["plan_fingerprint"], model_info=json.dumps(preview["model"], ensure_ascii=False), request_payload=json.dumps({"draft_fingerprint": preview["draft_fingerprint"], "estimated_tokens": preview["estimated_tokens"]}, ensure_ascii=False), response_payload="{}", confirmation_user="local-user", confirmation_at=datetime.utcnow(), result_status="failed", result_message=f"Agent 模型调用失败；系统未自动重试。请重新预览并再次确认。{str(error)[:240]}"))
        session.commit()


@router.post("/llm-drafts/invoke")
def invoke_agent_draft(req: AgentDraftRequest) -> dict[str, Any]:
    """Perform one explicitly approved LLM call and persist only a draft/audit."""
    if not req.confirmed or not req.allow_external_call:
        raise HTTPException(status_code=400, detail="必须同时明确 confirmed=true 与 allowExternalCall=true 才能调用真实 Agent 模型")
    preview = _preview_or_400(req)
    if not check_budget(preview["estimated_tokens"])["allowed"]:
        raise HTTPException(status_code=409, detail="本次 Agent 调用超过管理员配置的单次 token 预算")
    if not req.draft_fingerprint or req.draft_fingerprint != preview["draft_fingerprint"]:
        raise HTTPException(status_code=409, detail="预览草案或证据已变化，请重新预览并确认调用")
    book_id = _book_id(req.plan)
    with Session() as session:
        # Scope deduplication to this project; identical evidence can exist
        # in different projects and must never reuse another project's draft.
        existing = session.query(AgentAuditLog).join(
            AgentSession, AgentSession.id == AgentAuditLog.session_id,
        ).filter(
            AgentSession.book_id == book_id,
            AgentAuditLog.operation == "generate_llm_draft",
            AgentAuditLog.evidence_fingerprint == preview["evidence_fingerprint"],
            AgentAuditLog.plan_fingerprint == preview["plan_fingerprint"],
            AgentAuditLog.request_fingerprint == preview["request_fingerprint"],
            AgentAuditLog.result_status == "succeeded",
        ).order_by(AgentAuditLog.id.desc()).first()
        if existing:
            return {"draft": json.loads(existing.response_payload or "{}"), "deduplicated": True, "llm_called": False, "mutated": False}

    profile = get_agent_model_profile_for_invocation()
    runtime_policy = read_agent_runtime_policy()
    audit_records: list[dict[str, Any]] = []
    try:
        vision_inputs = _load_vision_inputs(book_id, req.attachment_ids, profile or {}, vision_enabled=bool(runtime_policy.get("vision_enabled")))
        effective_profile = dict(profile or {})
        effective_params = dict((profile or {}).get("default_params") or {})
        effective_params["thinking"] = {"type": runtime_policy.get("thinking", "disabled")}
        effective_profile["default_params"] = effective_params
        result = llm_client.call_llm_json(
            preview["user_prompt"], system=preview["system_prompt"], model_profile=effective_profile,
            required_keys=AGENT_DRAFT_REQUIRED_KEYS, estimated_tokens=preview["estimated_tokens"], retries=1,
            json_parse_retries=0,
            image_data_urls=vision_inputs,
            audit_callback=audit_records.append,
            audit_extra={"mode": "agent_draft"},
        )
    except Exception as exc:
        _persist_agent_draft_failure(book_id, preview, req.plan, exc)
        raise HTTPException(status_code=502, detail=f"智能导演台模型调用失败：{str(exc)[:300]}") from exc

    safe_result = {key: result.get(key) for key in AGENT_DRAFT_REQUIRED_KEYS}
    with Session() as session:
        agent_session = session.get(AgentSession, req.session_id) if req.session_id else None
        if agent_session and agent_session.book_id != book_id:
            raise HTTPException(status_code=409, detail="会话不属于当前项目")
        if not agent_session:
            agent_session = AgentSession(book_id=book_id, user_prompt=preview["evidence"]["objective"], status="awaiting_confirmation", evidence_fingerprint=preview["evidence_fingerprint"])
            session.add(agent_session)
            session.flush()
            # Keep the initial request in the human-readable transcript as
            # well as the session summary, so a restored conversation is
            # complete even when the caller invokes directly without first
            # creating a session through the UI.
            session.add(AgentMessage(session_id=agent_session.id, role="user", content=str(preview["evidence"]["objective"])[:50000], attachment_ids="[]"))
        else:
            agent_session.status = "awaiting_confirmation"
            agent_session.evidence_fingerprint = preview["evidence_fingerprint"]
            agent_session.updated_at = datetime.now()
        agent_plan = AgentPlan(session_id=agent_session.id, plan_fingerprint=preview["plan_fingerprint"], objective=preview["evidence"]["objective"], scope=json.dumps(preview["evidence"]["scope"], ensure_ascii=False), evidence_snapshot=json.dumps(preview["evidence"], ensure_ascii=False), steps=json.dumps(req.plan.get("steps") or [], ensure_ascii=False), status="draft")
        session.add(agent_plan)
        session.flush()
        attachment_ids = [item.get("id") for item in preview["evidence"].get("attachments", []) if isinstance(item, dict) and isinstance(item.get("id"), int)]
        if attachment_ids:
            session.query(AgentAttachment).filter(AgentAttachment.book_id == book_id, AgentAttachment.id.in_(attachment_ids)).update({"session_id": agent_session.id}, synchronize_session=False)
        session.add(AgentMessage(session_id=agent_session.id, role="assistant", content=str(safe_result.get("summary") or "AI 候选建议已生成，尚未执行生产操作。")[:50000], attachment_ids=json.dumps(attachment_ids)))
        audit_summary = summarize_audit_records(audit_records)
        model_info = dict(preview["model"])
        model_info["llm_request_audit"] = audit_summary
        session.add(AgentAuditLog(session_id=agent_session.id, plan_id=agent_plan.id, operation="generate_llm_draft", tool_tier="B", evidence_fingerprint=preview["evidence_fingerprint"], plan_fingerprint=preview["plan_fingerprint"], request_fingerprint=preview["request_fingerprint"], llm_usage=json.dumps({key: audit_summary.get(key) for key in ("prompt_tokens", "cached_tokens", "completion_tokens", "total_tokens", "cache_hit_rate", "last_latency_ms")}, ensure_ascii=False), model_info=json.dumps(model_info, ensure_ascii=False), request_payload=json.dumps({"draft_fingerprint": preview["draft_fingerprint"], "request_fingerprint": preview["request_fingerprint"], "estimated_tokens": preview["estimated_tokens"]}, ensure_ascii=False), response_payload=json.dumps(safe_result, ensure_ascii=False), confirmation_user="local-user", confirmation_at=datetime.utcnow(), result_status="succeeded", result_message="候选 Agent 草案已生成；尚未执行任何生产操作"))
        session.commit()
    return {"draft": safe_result, "deduplicated": False, "llm_called": True, "mutated": False, "status": "awaiting_confirmation"}


@router.get("/audit")
def list_agent_audit(book_id: int = Query(alias="bookId", gt=0), limit: int = Query(default=30, ge=1, le=100)) -> dict[str, Any]:
    """Read-only replay index for Smart Director drafts; no provider data leaks."""
    with Session() as session:
        sessions = {row.id: row for row in session.query(AgentSession).filter_by(book_id=book_id).all()}
        rows = session.query(AgentAuditLog).filter(AgentAuditLog.session_id.in_(sessions.keys() or [-1])).order_by(AgentAuditLog.id.desc()).limit(limit).all()
    entries = []
    for row in rows:
        try:
            response = json.loads(row.response_payload or "{}")
        except (TypeError, json.JSONDecodeError):
            response = {}
        try:
            model = json.loads(row.model_info or "{}")
        except (TypeError, json.JSONDecodeError):
            model = {}
        try:
            usage = json.loads(row.llm_usage or "{}")
        except (TypeError, json.JSONDecodeError):
            usage = {}
        entries.append({"id": row.id, "session_id": row.session_id, "operation": row.operation, "tier": row.tool_tier, "evidence_fingerprint": row.evidence_fingerprint, "plan_fingerprint": row.plan_fingerprint, "request_fingerprint": row.request_fingerprint, "llm_usage": usage, "model": model, "result_status": row.result_status, "result_message": row.result_message, "confirmed_at": row.confirmation_at.isoformat() if row.confirmation_at else None, "created_at": row.created_at.isoformat() if row.created_at else None, "draft": response})
    return {"entries": entries, "mutated": False}


@router.get("/usage-summary")
def get_agent_usage_summary(book_id: int = Query(alias="bookId", gt=0)) -> dict[str, Any]:
    """Aggregate persisted Agent LLM usage without contacting a provider.

    Missing provider cache details remain ``null`` at record level.  The
    aggregate reports ``cache_observable`` separately so an unavailable field
    is never presented as a zero-hit measurement.
    """
    with Session() as session:
        sessions = [row.id for row in session.query(AgentSession.id).filter_by(book_id=book_id).all()]
        rows = session.query(AgentAuditLog).filter(AgentAuditLog.session_id.in_(sessions or [-1])).all()
    prompt_tokens = cached_tokens = completion_tokens = total_tokens = 0
    observed_calls = 0
    cache_observable_calls = 0
    latency_values: list[float] = []
    for row in rows:
        try:
            usage = json.loads(row.llm_usage or "{}")
        except (TypeError, json.JSONDecodeError):
            usage = {}
        if not isinstance(usage, dict):
            continue
        if usage.get("prompt_tokens") is not None:
            observed_calls += 1
            prompt_tokens += int(usage.get("prompt_tokens") or 0)
            completion_tokens += int(usage.get("completion_tokens") or 0)
            total_tokens += int(usage.get("total_tokens") or 0)
        if usage.get("cached_tokens") is not None:
            cache_observable_calls += 1
            cached_tokens += int(usage.get("cached_tokens") or 0)
        if usage.get("last_latency_ms") is not None:
            latency_values.append(float(usage.get("last_latency_ms") or 0))
    return {
        "book_id": book_id,
        "audit_count": len(rows),
        "observed_calls": observed_calls,
        "prompt_tokens": prompt_tokens,
        "cached_tokens": cached_tokens if cache_observable_calls else None,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cache_observable": bool(cache_observable_calls),
        "cache_observable_calls": cache_observable_calls,
        "cache_hit_rate": round(cached_tokens / prompt_tokens, 6) if cache_observable_calls and prompt_tokens else None,
        "average_latency_ms": round(sum(latency_values) / len(latency_values), 2) if latency_values else None,
        "mutated": False,
    }


@router.get("/timeline")
def list_agent_timeline(book_id: int = Query(alias="bookId", gt=0), limit: int = Query(default=50, ge=1, le=100)) -> dict[str, Any]:
    """Read-only event timeline for one project's Smart Director sessions."""
    with Session() as session:
        sessions = session.query(AgentSession).filter_by(book_id=book_id).order_by(AgentSession.updated_at.desc(), AgentSession.id.desc()).limit(limit).all()
        session_ids = [row.id for row in sessions]
        plans = session.query(AgentPlan).filter(AgentPlan.session_id.in_(session_ids or [-1])).all()
        audits = session.query(AgentAuditLog).filter(AgentAuditLog.session_id.in_(session_ids or [-1])).all()
        updates = session.query(AgentProjectUpdate).filter_by(book_id=book_id).order_by(AgentProjectUpdate.id.desc()).limit(limit).all()
    events = []
    for row in sessions:
        events.append({"kind": "session", "id": row.id, "session_id": row.id, "status": row.status, "at": row.updated_at.isoformat() if row.updated_at else None, "summary": row.user_prompt[:240], "evidence_fingerprint": row.evidence_fingerprint})
    for row in plans:
        events.append({"kind": "plan", "id": row.id, "session_id": row.session_id, "status": row.status, "at": row.updated_at.isoformat() if row.updated_at else None, "summary": row.objective[:240], "plan_fingerprint": row.plan_fingerprint})
    for row in audits:
        # created_at is the local event-order clock used by all three tables.
        # confirmation_at historically uses utcnow(), so preferring it here
        # makes a just-created confirmation look eight hours old in China and
        # can hide it behind the timeline limit.
        events.append({"kind": "audit", "id": row.id, "session_id": row.session_id, "status": row.result_status, "at": row.created_at.isoformat() if row.created_at else (row.confirmation_at.isoformat() if row.confirmation_at else None), "summary": row.result_message[:240], "operation": row.operation, "tier": row.tool_tier, "plan_fingerprint": row.plan_fingerprint})
    for row in updates:
        events.append({"kind": "project_update", "id": row.id, "session_id": 0, "status": row.status, "at": row.created_at.isoformat() if row.created_at else None, "summary": row.message[:240], "operation": row.type, "tier": "A", "evidence_fingerprint": row.evidence_fingerprint})
    events.sort(key=lambda item: item.get("at") or "", reverse=True)
    return {"book_id": book_id, "events": events[:limit], "mutated": False}


def _change_session_state(session_id: int, target: str) -> dict[str, Any]:
    with Session() as session:
        row = session.get(AgentSession, session_id)
        if not row:
            raise HTTPException(status_code=404, detail="智能导演台会话不存在")
        previous = str(row.status or "draft")
        if target == "paused":
            if previous not in {"draft", "awaiting_confirmation", "running"}:
                raise HTTPException(status_code=409, detail=f"当前会话状态 {previous} 不能暂停")
            message = "会话已暂停；未取消或修改任何生产任务。"
        elif target == "awaiting_confirmation":
            if previous != "paused":
                raise HTTPException(status_code=409, detail="只有暂停中的会话可以恢复")
            message = "会话已恢复至等待确认；不会自动执行任何操作。"
        else:
            raise HTTPException(status_code=400, detail="不支持的会话状态转换")
        row.status = target
        row.updated_at = datetime.utcnow()
        session.add(AgentAuditLog(session_id=row.id, operation="session_pause" if target == "paused" else "session_resume", tool_tier="A", evidence_fingerprint=row.evidence_fingerprint, result_status=target, result_message=message))
        session.commit()
        return {"session_id": row.id, "previous_status": previous, "status": target, "message": message, "mutated": True}


@router.post("/sessions/{session_id}/pause")
def pause_agent_session(session_id: int) -> dict[str, Any]:
    return _change_session_state(session_id, "paused")


@router.post("/sessions/{session_id}/resume")
def resume_agent_session(session_id: int) -> dict[str, Any]:
    return _change_session_state(session_id, "awaiting_confirmation")


@router.get("/audit/{audit_id}/handoff-preview")
def preview_agent_handoff(audit_id: int) -> dict[str, Any]:
    """Expose existing-workspace handoff points for one audited suggestion.

    This is intentionally navigation/contract data only.  The destination
    workflow retains its own evidence, confirmation and versioning gates.
    """
    with Session() as session:
        audit = session.get(AgentAuditLog, audit_id)
        if not audit or audit.operation not in {"generate_llm_draft", "chat_turn"} or audit.result_status not in {"succeeded", "awaiting_confirmation", "handoff_confirmed"}:
            raise HTTPException(status_code=404, detail="未找到可承接的智能导演台候选草案")
        agent_session = session.get(AgentSession, audit.session_id)
        plan = session.get(AgentPlan, audit.plan_id) if audit.plan_id else None
        if not agent_session:
            raise HTTPException(status_code=409, detail="候选草案的会话上下文不完整，不能承接")
        if plan:
            try:
                scope = json.loads(plan.scope or "{}")
                steps = json.loads(plan.steps or "[]")
            except (TypeError, json.JSONDecodeError):
                raise HTTPException(status_code=409, detail="候选草案的计划上下文无效，不能承接")
        else:
            try:
                request_payload = json.loads(audit.request_payload or "{}")
            except (TypeError, json.JSONDecodeError):
                request_payload = {}
            scope = request_payload.get("scope") if isinstance(request_payload.get("scope"), dict) else {}
            try:
                response_payload = json.loads(audit.response_payload or "{}")
            except (TypeError, json.JSONDecodeError):
                response_payload = {}
            proposal = response_payload.get("action_proposal") if isinstance(response_payload.get("action_proposal"), dict) else {}
            steps = [{"operation": proposal.get("operation")}] if proposal.get("operation") else []
    episode = _int(scope.get("episode"))
    shot_id = _int(scope.get("shot_id"))
    actions = []
    operations = {str(step.get("operation") or "") for step in steps if isinstance(step, dict)}
    if "draft_prompt" in operations and episode and shot_id:
        actions.append({"kind": "prompt_draft", "tier": "B", "requires_confirmation": False, "label": "在镜头工作台创建提示词证据包", "route": f"/api/books/{agent_session.book_id}/storyboard/{episode}/{shot_id}/prompt-drafts", "guard": "仅创建现有 Prompt Compiler 的证据包；真实 LLM 与 Prompt Version 仍需在原流程确认"})
    if "draft_repair" in operations:
        actions.append({"kind": "qa_repair", "tier": "B", "requires_confirmation": False, "label": "前往 QA 修复工作台审阅候选修复", "route": f"/workspace/books/{agent_session.book_id}/qa", "guard": "只打开既有 QA 修复入口；脚本版本写入仍需原流程确认"})
    if "write_prompt_version" in operations:
        actions.append({"kind": "prompt_version", "tier": "C", "requires_confirmation": True, "label": "在原 Prompt Version 流程中审阅并确认写入", "route": f"/workspace/books/{agent_session.book_id}/storyboard", "guard": "Agent 不可直接写入 Prompt Version；必须先通过现有证据、差异和确认门禁"})
    if "image_generation" in operations or "video_generation" in operations:
        actions.append({"kind": "media_generation", "tier": "D", "requires_confirmation": True, "label": "在镜头工作台按原双确认流程提交生成", "route": f"/workspace/books/{agent_session.book_id}/storyboard", "guard": "Agent 不可直接提交图片或视频；必须由用户在原生成界面确认"})
    return {"audit_id": audit_id, "book_id": agent_session.book_id, "plan_fingerprint": audit.plan_fingerprint, "actions": actions, "mutated": False}


@router.post("/audit/{audit_id}/handoff-confirm")
def confirm_agent_handoff(audit_id: int) -> dict[str, Any]:
    """Record explicit user intent and return a safe workbench handoff.

    This endpoint deliberately does not execute a tool, write production
    content, create a generation task, or create a Prompt Version.  It only
    records the confirmation in the audit log and gives the UI enough
    information to open the existing workflow, where its own gates remain in
    force.  Repeating the request is idempotent.
    """
    with Session() as session:
        audit = session.get(AgentAuditLog, audit_id)
        if not audit or audit.operation != "chat_turn":
            raise HTTPException(status_code=404, detail="未找到可确认的对话动作提案")
        agent_session = session.get(AgentSession, audit.session_id)
        if not agent_session:
            raise HTTPException(status_code=409, detail="对话会话不存在，不能承接")
        try:
            response_payload = json.loads(audit.response_payload or "{}")
        except (TypeError, json.JSONDecodeError):
            response_payload = {}
        proposal = response_payload.get("action_proposal") if isinstance(response_payload.get("action_proposal"), dict) else {}
        operation = str(proposal.get("operation") or "").strip()
        tool = resolve_tool(operation)
        if not operation or tool["execution"] == "blocked" or not tool["requires_confirmation"]:
            raise HTTPException(status_code=409, detail="该对话没有可确认的副作用动作")
        if audit.result_status not in {"awaiting_confirmation", "handoff_confirmed"}:
            raise HTTPException(status_code=409, detail="该动作提案已处理或已失效")
        try:
            request_payload = json.loads(audit.request_payload or "{}")
        except (TypeError, json.JSONDecodeError):
            request_payload = {}
        scope = request_payload.get("scope") if isinstance(request_payload.get("scope"), dict) else {}
        # A confirmation is only valid for the same server-authoritative
        # snapshot that produced the proposal.  Rebuild the evidence before
        # handing off so an old proposal cannot silently open a changed
        # production context.
        scope = dict(scope)
        scope["book_id"] = agent_session.book_id
        try:
            current_evidence = build_project_evidence(scope)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        current_fingerprint = hashlib.sha256(json.dumps(current_evidence, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        if audit.evidence_fingerprint and current_fingerprint != audit.evidence_fingerprint:
            audit.result_status = "expired"
            audit.result_message = "动作提案所依据的项目事实已变化，请重新向 Agent 发起请求。"
            agent_session.status = "blocked"
            agent_session.updated_at = datetime.now()
            session.commit()
            raise HTTPException(status_code=409, detail="动作提案已过期：项目事实发生变化，请重新发起请求")
        episode = _int(scope.get("episode"))
        shot_id = _int(scope.get("shot_id"))
        asset_id = _int(scope.get("asset_id"))
        if operation in {"draft_prompt", "write_prompt_version", "image_generation", "video_generation", "continuity_check"}:
            section = "storyboard"
        elif operation in {"write_asset_governance"}:
            section = "assets"
        elif operation in {"draft_repair", "qa_read"}:
            section = "qa"
        else:
            section = "dashboard"
        if audit.result_status == "awaiting_confirmation":
            audit.result_status = "handoff_confirmed"
            audit.confirmation_user = "local-user"
            audit.confirmation_at = datetime.utcnow()
            audit.result_message = "用户已确认承接意图；等待在正式工作台完成原有安全门禁。"
            agent_session.status = "accepted"
            agent_session.updated_at = datetime.now()
            session.commit()
        return {
            "audit_id": audit_id,
            "book_id": agent_session.book_id,
            "operation": operation,
            "tool": tool,
            "handoff": {
                "section": section,
                "episode": episode,
                "shot_id": shot_id,
                "asset_id": asset_id,
                "label": tool["label"],
                "guard": "已记录确认意图；正式工作台仍会再次校验证据、锁定状态、版本和生成确认。",
            },
            "mutated": True,
        }
