"""Agent domain models for the smart director workspace.

Phase 0 introduces only the three minimum tables and a small state surface.
It does not touch UI, does not call any external model, and stores no
secrets or raw model output.

- AgentSession: a session-level container for one conversation / plan /
  execution cycle, used for audit and replay.
- AgentPlan: the persisted form of DirectorPlan. evidence_snapshot,
  approval_policy, cost_envelope and rollback_anchor are stored as JSON
  text and aligned with the DecisionPacketRecord style.
- AgentAuditLog: a per-step trace. evidence_fingerprint and
  plan_fingerprint match the decision packet / plan fingerprints so
  cross-table alignment is possible.

Design principles:
- Every field has an explicit default to avoid divergence from existing
  models.
- The status enum is fixed to:
    draft / awaiting_confirmation / running / accepted / rejected /
    blocked / completed.
  Agent code is not allowed to invent new values.
- allowed_operations and approval_policy strictly follow the A / B / C
  / D four-tier system.
- No key, raw model output, or executable code is stored here.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from .base import Base


AGENT_SESSION_STATUS = {
    "draft",
    "awaiting_confirmation",
    "running",
    "paused",
    "accepted",
    "rejected",
    "blocked",
    "completed",
}


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    user_prompt = Column(Text, default="")
    status = Column(String, default="draft")
    skill_id = Column(String, default="")
    skill_version = Column(String, default="")
    evidence_fingerprint = Column(String, default="", index=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class AgentPlan(Base):
    __tablename__ = "agent_plans"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, nullable=False, index=True)
    plan_fingerprint = Column(String, default="", index=True)
    objective = Column(Text, default="")
    scope = Column(Text, default="{}")
    evidence_snapshot = Column(Text, default="{}")
    steps = Column(Text, default="[]")
    preconditions = Column(Text, default="[]")
    blocking_issues = Column(Text, default="[]")
    approval_policy = Column(Text, default="{}")
    cost_envelope = Column(Text, default="{}")
    rollback_anchor = Column(Text, default="{}")
    status = Column(String, default="draft")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class AgentAuditLog(Base):
    __tablename__ = "agent_audit_logs"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, nullable=False, index=True)
    plan_id = Column(Integer, nullable=True, index=True)
    step_index = Column(Integer, default=0)
    operation = Column(String, default="")
    tool_tier = Column(String, default="A")
    evidence_fingerprint = Column(String, default="", index=True)
    plan_fingerprint = Column(String, default="", index=True)
    # Exact non-secret identity of the provider request.  It includes the
    # canonical prompt plus safe model parameters and prevents cross-parameter
    # draft reuse when evidence happens to be identical.
    request_fingerprint = Column(String, default="", index=True)
    model_info = Column(Text, default="{}")
    llm_usage = Column(Text, default="{}")
    request_payload = Column(Text, default="{}")
    response_payload = Column(Text, default="{}")
    confirmation_user = Column(String, default="")
    confirmation_at = Column(DateTime, nullable=True)
    result_status = Column(String, default="")
    result_message = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)


class AgentAttachment(Base):
    """Private, user-supplied context for a Smart Director conversation.

    Attachments are deliberately separate from production media: uploading a
    reference for a conversation must never publish it to object storage or
    make it available to image/video generation by accident.
    """
    __tablename__ = "agent_attachments"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    session_id = Column(Integer, nullable=True, index=True)
    original_filename = Column(String, nullable=False, default="")
    mime_type = Column(String, nullable=False, default="")
    kind = Column(String, nullable=False, default="document")
    size_bytes = Column(Integer, nullable=False, default=0)
    storage_key = Column(Text, nullable=False, default="")
    sha256 = Column(String, nullable=False, default="", index=True)
    extraction_status = Column(String, nullable=False, default="pending")
    extracted_text = Column(Text, nullable=False, default="")
    status = Column(String, nullable=False, default="ready")
    created_at = Column(DateTime, default=datetime.now)


class AgentMessage(Base):
    """Human-readable conversation transcript, separate from audit payloads."""
    __tablename__ = "agent_messages"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, nullable=False, index=True)
    role = Column(String, nullable=False, default="user")
    content = Column(Text, nullable=False, default="")
    attachment_ids = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, default=datetime.now)


class AgentProjectUpdate(Base):
    """A deduplicated, user-facing project progress or issue update.

    Updates are separate from the conversation transcript and audit log: they
    represent durable project facts that can be surfaced proactively in the
    drawer and task center.  ``source_refs`` and ``evidence_fingerprint``
    make every statement replayable; no update is allowed to become an
    execution shortcut.
    """
    __tablename__ = "agent_project_updates"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    type = Column(String, nullable=False, default="progress", index=True)
    severity = Column(String, nullable=False, default="info", index=True)
    title = Column(String, nullable=False, default="")
    message = Column(Text, nullable=False, default="")
    source_refs = Column(Text, nullable=False, default="[]")
    evidence_fingerprint = Column(String, nullable=False, default="", index=True)
    action_proposal = Column(Text, nullable=False, default="{}")
    requires_confirmation = Column(Integer, nullable=False, default=0)
    status = Column(String, nullable=False, default="unread", index=True)
    dedupe_key = Column(String, nullable=False, default="", index=True)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, index=True)
