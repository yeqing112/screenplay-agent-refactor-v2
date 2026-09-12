"""ShotPlan model: executable shot intent between blocking and StoryboardShot."""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from .base import Base


class ShotPlan(Base):
    __tablename__ = "shot_plans"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    episode = Column(Integer, nullable=False, index=True)
    scene_name = Column(String, nullable=False, default="")
    revision = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, default="draft")  # draft / approved / superseded
    execution_status = Column(String, nullable=False, default="queued")
    quality_status = Column(String, nullable=False, default="draft")
    production_status = Column(String, nullable=False, default="blocked")
    workflow_profile = Column(String, nullable=False, default="creative_draft")
    treatment_id = Column(Integer, nullable=True)
    blocking_id = Column(Integer, nullable=True)
    shots = Column(Text, nullable=False, default="[]")
    unknowns = Column(Text, nullable=False, default="[]")
    evidence_fingerprint = Column(String, nullable=False, default="")
    model_info = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)
