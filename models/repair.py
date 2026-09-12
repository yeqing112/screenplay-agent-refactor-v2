"""Runtime repair attempts shared by qualification and production layers."""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from .base import Base


class RepairAttempt(Base):
    """Durable, immutable-ish audit row for one bounded local repair.

    The row deliberately stores fingerprints and a redacted operation rather
    than provider secrets or raw model responses.  It is usable by Scene
    Blocking, ScriptIR, ShotPlan and Prompt qualification alike.
    """

    __tablename__ = "repair_attempts"

    id = Column(Integer, primary_key=True)
    issue_code = Column(String, nullable=False, default="")
    target_layer = Column(String, nullable=False, default="")
    target_id = Column(String, nullable=False, default="")
    book_id = Column(Integer, nullable=True, index=True)
    episode = Column(Integer, nullable=True, index=True)
    scene_id = Column(String, nullable=True, default="")
    shot_id = Column(String, nullable=True, default="")
    before_fingerprint = Column(String, nullable=False, default="")
    repair_operation = Column(Text, nullable=False, default="{}")
    after_fingerprint = Column(String, nullable=False, default="")
    attempt_number = Column(Integer, nullable=False, default=1)
    revalidation_status = Column(String, nullable=False, default="pending")
    revalidation_details = Column(Text, nullable=False, default="{}")
    model = Column(String, nullable=False, default="")
    prompt_fingerprint = Column(String, nullable=False, default="")
    created_at = Column(DateTime, default=datetime.now)
