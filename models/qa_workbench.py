"""Structured QA issue and script version models for repair workbench."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from .base import Base


class QAIssue(Base):
    __tablename__ = "qa_issues"

    id = Column(Integer, primary_key=True)
    issue_key = Column(String, nullable=False, unique=True)
    book_id = Column(Integer, nullable=False)
    episode = Column(Integer, nullable=False)
    qa_result_id = Column(Integer, nullable=True)
    severity = Column(String, default="medium")
    issue_type = Column(String, default="unknown")
    title = Column(String, default="")
    description = Column(Text, default="")
    script_section = Column(String, default="")
    line_start = Column(Integer, nullable=True)
    line_end = Column(Integer, nullable=True)
    suggestion = Column(Text, default="")
    fix_mode = Column(String, default="semi_auto")
    fix_status = Column(String, default="pending")
    status_reason = Column(Text, default="")
    source_excerpt = Column(Text, default="")
    meta_info = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class ScriptVersion(Base):
    __tablename__ = "script_versions"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False)
    episode = Column(Integer, nullable=False)
    script_id = Column(Integer, nullable=True)
    version_no = Column(Integer, nullable=False, default=1)
    label = Column(String, default="")
    change_type = Column(String, default="manual_fix")
    change_reason = Column(Text, default="")
    qa_issue_key = Column(String, default="")
    operator_name = Column(String, default="system")
    content_before = Column(Text, default="")
    content_after = Column(Text, default="")
    diff_text = Column(Text, default="")
    recheck_status = Column(String, default="pending")
    recheck_summary = Column(Text, default="")
    meta_info = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)
