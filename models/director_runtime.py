"""AI Director runtime foundation persistence models.

The runtime stores append-only, reviewable plans.  Scene plans are kept as
children of a DirectorPlan while shot plans continue to use the existing
scene-level ``ShotPlan`` table (its JSON payload contains individual shots).
"""
from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, Integer, String, Text, UniqueConstraint

from .base import Base


class DirectorPlan(Base):
    __tablename__ = "director_plans"

    id = Column(Integer, primary_key=True)
    episode_id = Column(String, nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, default="DRAFT", index=True)
    created_by = Column(String, nullable=False, default="director-runtime")
    reasoning_trace = Column(Text, nullable=False, default="{}")
    scene_plans = Column(Text, nullable=False, default="[]")
    shot_plans = Column(Text, nullable=False, default="[]")
    shot_directions = Column(Text, nullable=False, default="[]")
    generation_intents = Column(Text, nullable=False, default="[]")
    source_script_ir_version_id = Column(Integer, nullable=True, index=True)
    source_script_ir_hash = Column(String, nullable=False, default="")
    source_fact_snapshot_hash = Column(String, nullable=False, default="")
    source_immutable_raw_hash = Column(String, nullable=False, default="")
    payload_hash = Column(String, nullable=False, default="", index=True)
    lineage_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("episode_id", "version", name="uq_director_plan_episode_version"),
        CheckConstraint("version >= 1", name="ck_director_plan_version_positive"),
        CheckConstraint("status IN ('DRAFT','REVIEW_REQUIRED','APPROVED','SUPERSEDED','REJECTED')", name="ck_director_plan_status"),
    )


class ScenePlan(Base):
    __tablename__ = "director_scene_plans"

    id = Column(Integer, primary_key=True)
    director_plan_id = Column(Integer, nullable=False, index=True)
    episode_id = Column(String, nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    scene_id = Column(String, nullable=False, index=True)
    location = Column(String, nullable=False, default="")
    time = Column(String, nullable=False, default="")
    mood = Column(String, nullable=False, default="")
    characters = Column(Text, nullable=False, default="[]")
    visual_requirements = Column(Text, nullable=False, default="{}")
    source_lineage = Column(Text, nullable=False, default="{}")
    payload_hash = Column(String, nullable=False, default="", index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("director_plan_id", "scene_id", name="uq_director_scene_plan_scene"),
        CheckConstraint("version >= 1", name="ck_director_scene_plan_version_positive"),
    )


__all__ = ["DirectorPlan", "ScenePlan"]
