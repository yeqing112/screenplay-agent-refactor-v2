"""Automatic keyframe planning records over the existing keyframe runtime."""
from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint

from .base import Base


AUTOMATIC_KEYFRAME_PLAN_STATUSES = (
    "REVIEW_REQUIRED",
    "APPROVED",
    "REJECTED",
    "REVISE",
    "STALE",
    "COMPILED",
    "SUPERSEDED",
)


class AutomaticKeyframePlan(Base):
    """Versioned, reviewable keyframe plan; never a second keyframe system."""

    __tablename__ = "automatic_keyframe_plans"

    id = Column(Integer, primary_key=True)
    episode_id = Column(String, nullable=False, index=True)
    storyboard_shot_id = Column(Integer, ForeignKey("storyboard_shots.id", ondelete="RESTRICT"), nullable=False, index=True)
    storyboard_materialization_set_id = Column(Integer, ForeignKey("storyboard_materialization_sets.id", ondelete="RESTRICT"), nullable=False, index=True)
    storyboard_materialization_version = Column(Integer, nullable=False, default=1)
    materialization_set_fingerprint = Column(String, nullable=False, index=True)
    shot_plan_id = Column(Integer, nullable=False, index=True)
    shot_plan_revision = Column(Integer, nullable=False, default=1)
    shot_direction_id = Column(Integer, ForeignKey("shot_directions.id", ondelete="RESTRICT"), nullable=False, index=True)
    shot_direction_revision = Column(Integer, nullable=False, default=1)
    shot_direction_fingerprint = Column(String, nullable=False, index=True)
    generation_intent_id = Column(String, nullable=False, index=True)
    generation_intent_fingerprint = Column(String, nullable=False, index=True)
    production_prompt_version_id = Column(String, nullable=False, index=True)
    production_prompt_fingerprint = Column(String, nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, default="REVIEW_REQUIRED", index=True)
    duration = Column(Float, nullable=False)
    plan_json = Column(Text, nullable=False, default="{}")
    source_fingerprint = Column(String, nullable=False, unique=True, index=True)
    source_lineage_json = Column(Text, nullable=False, default="{}")
    created_by = Column(String, nullable=False, default="automatic-keyframe-planner")
    reviewed_by = Column(String, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_lineage_json = Column(Text, nullable=False, default="{}")
    compiled_sequence_id = Column(Integer, ForeignKey("keyframe_sequences.id", ondelete="RESTRICT"), nullable=True, index=True)
    compiled_sequence_fingerprint = Column(String, nullable=True, index=True)
    stale_reasons = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("storyboard_shot_id", "version", name="uq_automatic_keyframe_plan_shot_version"),
        CheckConstraint("version >= 1", name="ck_automatic_keyframe_plan_version"),
        CheckConstraint("duration > 0", name="ck_automatic_keyframe_plan_duration"),
        CheckConstraint("storyboard_materialization_version >= 1", name="ck_automatic_keyframe_plan_materialization_version"),
        CheckConstraint("shot_plan_revision >= 1", name="ck_automatic_keyframe_plan_shot_plan_revision"),
        CheckConstraint("shot_direction_revision >= 1", name="ck_automatic_keyframe_plan_direction_revision"),
        CheckConstraint(
            "status IN ('REVIEW_REQUIRED','APPROVED','REJECTED','REVISE','STALE','COMPILED','SUPERSEDED')",
            name="ck_automatic_keyframe_plan_status",
        ),
    )


__all__ = ["AUTOMATIC_KEYFRAME_PLAN_STATUSES", "AutomaticKeyframePlan"]
