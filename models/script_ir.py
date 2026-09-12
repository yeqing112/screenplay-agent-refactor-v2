"""Versioned machine-readable script representation."""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from .base import Base


class ScriptIRVersion(Base):
    __tablename__ = "script_ir_versions"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    episode = Column(Integer, nullable=False, index=True)
    revision = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, default="draft")  # draft / qualified / superseded
    schema_version = Column(String, nullable=False, default="script_ir_v1")
    source_outline_revision = Column(String, nullable=False, default="")
    source_fact_snapshot_id = Column(String, nullable=False, default="")
    source_fingerprint = Column(String, nullable=False, default="")
    payload_json = Column(Text, nullable=False, default="{}")
    payload_hash = Column(String, nullable=False, default="")
    validation_status = Column(String, nullable=False, default="needs_review")
    validation_report = Column(Text, nullable=False, default="{}")
    previous_revision_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)

