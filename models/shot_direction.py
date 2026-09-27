"""Shot direction relation anchored to the existing StoryboardShot authority."""
from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import synonym

from .base import Base


SHOT_DIRECTION_STATUSES = ("ACTIVE", "STALE")


class ShotDirection(Base):
    """Camera, composition and performance direction for one existing shot."""

    __tablename__ = "shot_directions"

    id = Column(Integer, primary_key=True)
    storyboard_shot_id = Column(Integer, ForeignKey("storyboard_shots.id", ondelete="RESTRICT"), nullable=False, unique=True, index=True)
    shot_type = Column(String, nullable=False, default="")
    camera_profile = Column(Text, nullable=False, default="{}")
    movement_profile = Column(Text, nullable=False, default="{}")
    composition_profile = Column(Text, nullable=False, default="{}")
    performance_profile = Column(Text, nullable=False, default="{}")
    emotion_profile = Column(Text, nullable=False, default="{}")
    revision = Column(Integer, nullable=False, default=1)
    direction_fingerprint = Column(String, nullable=False, unique=True)
    status = Column(String, nullable=False, default="ACTIVE", index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # API callers use the shorter shot_id spelling; persistence remains tied
    # to StoryboardShot's primary key.
    shot_id = synonym("storyboard_shot_id")

    __table_args__ = (
        CheckConstraint("revision >= 1", name="ck_shot_direction_revision"),
        CheckConstraint("status IN ('ACTIVE','STALE')", name="ck_shot_direction_status"),
    )


__all__ = ["SHOT_DIRECTION_STATUSES", "ShotDirection"]
