"""Draft-layer automatic storyboard planning models."""

from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from .base import Base


class StoryboardPlan(Base):
    """Versioned, reviewable storyboard draft that precedes ShotPlan."""

    __tablename__ = "director_storyboard_plans"

    id = Column(Integer, primary_key=True)
    episode_id = Column(String, nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, default="REVIEW_REQUIRED", index=True)
    storyboard_json = Column(Text, nullable=False, default="{}")
    director_reasoning_id = Column(Integer, nullable=True, index=True)
    director_reasoning_version = Column(Integer, nullable=True)
    compiled_shot_plan_ids = Column(Text, nullable=False, default="[]")
    payload_hash = Column(String, nullable=False, default="", index=True)
    lineage_json = Column(Text, nullable=False, default="{}")
    approved_by = Column(String, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    review_lineage_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("episode_id", "version", name="uq_director_storyboard_episode_version"),
        CheckConstraint("version >= 1", name="ck_director_storyboard_version_positive"),
        CheckConstraint("status IN ('DRAFT','REVIEW_REQUIRED','COMPILED','APPROVED','SUPERSEDED','ROLLED_BACK','REJECTED')", name="ck_director_storyboard_status"),
    )


class StoryboardPlanShot(Base):
    """A draft storyboard shot; it is not the production StoryboardShot table."""

    __tablename__ = "director_storyboard_shots"

    id = Column(Integer, primary_key=True)
    storyboard_id = Column(Integer, ForeignKey("director_storyboard_plans.id", ondelete="RESTRICT"), nullable=False, index=True)
    shot_id = Column(String, nullable=False, default="")
    scene_id = Column(String, nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    shot_type = Column(String, nullable=False, default="medium")
    camera = Column(Text, nullable=False, default="{}")
    composition = Column(Text, nullable=False, default="{}")
    character_actions = Column(Text, nullable=False, default="{}")
    emotion = Column(Text, nullable=False, default="")
    duration = Column(Integer, nullable=False, default=3)
    visual_style_id = Column(String, nullable=False, default="")
    shot_direction = Column(Text, nullable=False, default="{}")
    source_lineage = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("storyboard_id", "sequence", name="uq_director_storyboard_shot_sequence"),
        CheckConstraint("sequence >= 1", name="ck_director_storyboard_shot_sequence_positive"),
        CheckConstraint("duration > 0 AND duration <= 60", name="ck_director_storyboard_shot_duration_range"),
    )


StoryboardShotDraft = StoryboardPlanShot

__all__ = ["StoryboardPlan", "StoryboardPlanShot", "StoryboardShotDraft"]
