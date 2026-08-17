"""Persisted delivery/export history for production mode."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from .base import Base


class ProductionExportRecord(Base):
    __tablename__ = "production_export_records"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False)
    export_format = Column(String, default="json")
    status = Column(String, default="completed")
    total_shots = Column(Integer, default=0)
    deliverable_shots = Column(Integer, default=0)
    pending_review_shots = Column(Integer, default=0)
    blocked_shots = Column(Integer, default=0)
    summary = Column(Text, default="")
    meta_info = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)
