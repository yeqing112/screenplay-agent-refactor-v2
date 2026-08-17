"""Acceptance records for generated storyboard assets."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from .base import Base


class StoryboardAcceptanceRecord(Base):
    __tablename__ = "storyboard_acceptance_records"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False)
    episode = Column(Integer, nullable=False)
    shot_id = Column(Integer, nullable=False)
    asset_kind = Column(String, default="image")
    asset_id = Column(String, default="")
    status = Column(String, default="retrying")
    failure_tags = Column(Text, default="[]")
    notes = Column(Text, default="")
    meta_info = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)
