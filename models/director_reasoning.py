"""AI Director reasoning intermediate representation models."""
from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, Integer, String, Text, UniqueConstraint

from .base import Base


class DirectorReasoning(Base):
    """Append-only, reviewable authority for one episode's reasoning IR."""

    __tablename__ = "director_reasonings"

    id = Column(Integer, primary_key=True)
    episode_id = Column(String, nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, default="DRAFT", index=True)
    reasoning_json = Column(Text, nullable=False, default="{}")
    source_script_ir_hash = Column(String, nullable=False, default="")
    source_fact_snapshot_hash = Column(String, nullable=False, default="")
    payload_hash = Column(String, nullable=False, default="", index=True)
    compiled_shot_plan_ids = Column(Text, nullable=False, default="[]")
    lineage_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("episode_id", "version", name="uq_director_reasoning_episode_version"),
        CheckConstraint("version >= 1", name="ck_director_reasoning_version_positive"),
        CheckConstraint("status IN ('DRAFT','REVIEW_REQUIRED','COMPILED','SUPERSEDED','ROLLED_BACK','REJECTED')", name="ck_director_reasoning_status"),
    )


class StoryBeat(Base):
    """Ordered narrative beat projected from a DirectorReasoning IR."""

    __tablename__ = "director_story_beats"

    id = Column(Integer, primary_key=True)
    director_reasoning_id = Column(Integer, nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    scene_id = Column(String, nullable=False, default="", index=True)
    purpose = Column(Text, nullable=False, default="")
    emotion = Column(Text, nullable=False, default="")
    visual_goal = Column(Text, nullable=False, default="")
    character_refs = Column(Text, nullable=False, default="[]")
    shot_refs = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("director_reasoning_id", "sequence", name="uq_director_story_beat_sequence"),
        CheckConstraint("sequence >= 1", name="ck_director_story_beat_sequence_positive"),
    )


class VisualDecision(Base):
    """Visual decision associated with one ordered StoryBeat."""

    __tablename__ = "director_visual_decisions"

    id = Column(Integer, primary_key=True)
    director_reasoning_id = Column(Integer, nullable=False, index=True)
    story_beat_sequence = Column(Integer, nullable=False)
    visual_style_id = Column(String, nullable=False, default="", index=True)
    camera_strategy = Column(Text, nullable=False, default="")
    lighting_strategy = Column(Text, nullable=False, default="")
    color_strategy = Column(Text, nullable=False, default="")
    composition_strategy = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("director_reasoning_id", "story_beat_sequence", name="uq_director_visual_decision_beat"),
        CheckConstraint("story_beat_sequence >= 1", name="ck_director_visual_decision_sequence_positive"),
    )


__all__ = ["DirectorReasoning", "StoryBeat", "VisualDecision"]
