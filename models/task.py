"""Persistent task state models."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from .base import Base


class TaskRun(Base):
    __tablename__ = "task_runs"

    id = Column(Integer, primary_key=True)
    task_id = Column(String, nullable=False, unique=True, index=True)
    task_kind = Column(String, nullable=False, index=True)
    status = Column(String, default="queued", index=True)
    progress = Column(Integer, default=0)
    book_id = Column(Integer, nullable=True, index=True)
    episode = Column(Integer, nullable=True, index=True)
    payload = Column(Text, default="{}")
    error = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, index=True)
    finished_at = Column(DateTime, nullable=True, index=True)
