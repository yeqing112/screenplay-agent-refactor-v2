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
    execution_status = Column(String, nullable=False, default="queued")
    quality_status = Column(String, nullable=False, default="draft")
    production_status = Column(String, nullable=False, default="blocked")
    workflow_profile = Column(String, nullable=False, default="creative_draft")
    # V2 keeps the legacy columns above readable while storing the semantic
    # spatial model in additive JSON columns.  Existing rows remain V1 until
    # explicitly regenerated; no historical artifact is rewritten.
    schema_version = Column(String, nullable=False, default="scene_blocking_v1")
    treatment_id = Column(Integer, nullable=True)
    treatment_revision = Column(Integer, nullable=True)
    source_script_hash = Column(String, nullable=False, default="")
    participants = Column(Text, nullable=False, default="[]")
    beat_transitions = Column(Text, nullable=False, default="[]")
    spatial_rules = Column(Text, nullable=False, default="[]")
    unknowns = Column(Text, nullable=False, default="[]")
    evidence_fingerprint = Column(String, nullable=False, default="")
    model_info = Column(Text, nullable=False, default="{}")
    spatial_model = Column(Text, nullable=False, default="{}")
    source_spatial_facts = Column(Text, nullable=False, default="[]")
    creative_decisions = Column(Text, nullable=False, default="[]")
    derived_constraints = Column(Text, nullable=False, default="{}")
    unresolved_facts = Column(Text, nullable=False, default="[]")
    camera_axis = Column(Text, nullable=False, default="{}")
    validation = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)
