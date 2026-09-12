"""SceneBlocking / Spatial Engine persistence model."""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from .base import Base


class SceneBlocking(Base):
    __tablename__ = "scene_blockings"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    episode = Column(Integer, nullable=False, index=True)
    scene_name = Column(String, nullable=False, default="")
    revision = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, default="draft")  # draft / approved / superseded
    treatment_id = Column(Integer, nullable=True)
    treatment_revision = Column(Integer, nullable=True)
    source_script_hash = Column(String, nullable=False, default="")
    participants = Column(Text, nullable=False, default="[]")
    beat_transitions = Column(Text, nullable=False, default="[]")
    spatial_rules = Column(Text, nullable=False, default="[]")
    unknowns = Column(Text, nullable=False, default="[]")
    evidence_fingerprint = Column(String, nullable=False, default="")
    model_info = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)
