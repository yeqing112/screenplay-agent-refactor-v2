"""Versioned canonical fact snapshots shared by script and production stages."""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text

from .base import Base


class FactSnapshot(Base):
    __tablename__ = "fact_snapshots"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    episode = Column(Integer, nullable=True, index=True)
    revision = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, default="draft")  # draft / confirmed / superseded
    source_fingerprint = Column(String, nullable=False, default="")
    payload_hash = Column(String, nullable=False, default="")
    records_json = Column(Text, nullable=False, default="[]")
    validation_report = Column(Text, nullable=False, default="{}")
    previous_snapshot_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class FactRecord(Base):
    __tablename__ = "fact_records"

    id = Column(Integer, primary_key=True)
    snapshot_id = Column(Integer, nullable=False, index=True)
    fact_id = Column(String, nullable=False)
    subject_type = Column(String, nullable=False, default="")
    subject_id = Column(String, nullable=False, default="")
    predicate = Column(String, nullable=False, default="")
    value_json = Column(Text, nullable=False, default="null")
    scope = Column(String, nullable=False, default="global")
    authority = Column(String, nullable=False, default="derived_fact")
    status = Column(String, nullable=False, default="proposed")
    confidence = Column(Float, nullable=False, default=0.0)
    evidence_json = Column(Text, nullable=False, default="[]")
    conflict_group = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
