"""Video generation intent anchored to existing shots and execution lineage."""
from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, Float, ForeignKey, Integer, String, Text

from .base import Base


VIDEO_INTENT_STATUSES = ("READY", "EXECUTING", "SUCCEEDED", "FAILED")


class VideoGenerationIntent(Base):
    """One provider-neutral video request for an existing storyboard shot."""

    __tablename__ = "video_generation_intents"

    id = Column(Integer, primary_key=True)
    storyboard_shot_id = Column(Integer, ForeignKey("storyboard_shots.id", ondelete="RESTRICT"), nullable=False, index=True)
    duration = Column(Float, nullable=False)
    aspect_ratio = Column(String, nullable=False)
    motion_profile = Column(Text, nullable=False, default="{}")
    first_frame_asset = Column(Text, nullable=False, default="{}")
    last_frame_asset = Column(Text, nullable=False, default="{}")
    prompt_version = Column(String, nullable=False)
    intent_fingerprint = Column(String, nullable=False, unique=True, index=True)
    status = Column(String, nullable=False, default="READY", index=True)
    generation_execution_id = Column(String, nullable=True, unique=True, index=True)
    task_id = Column(String, nullable=True, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("duration > 0", name="ck_video_generation_intent_duration_positive"),
        CheckConstraint("status IN ('READY','EXECUTING','SUCCEEDED','FAILED')", name="ck_video_generation_intent_status"),
    )

    @property
    def shot_id(self) -> int:
        return int(self.storyboard_shot_id)

    @property
    def generation_type(self) -> str:
        return "VIDEO"


__all__ = ["VIDEO_INTENT_STATUSES", "VideoGenerationIntent"]
