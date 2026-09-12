"""DirectorTreatment domain model.

Treatment is the creative directing layer between a script scene and a shot
plan.  It is intentionally independent from ``AgentPlan`` (which describes
assistant operations) and from ``StoryboardShot`` (which describes executable
shots).  A treatment can therefore be generated in shadow mode without
changing production data.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from .base import Base


class DirectorTreatment(Base):
    __tablename__ = "director_treatments"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    episode = Column(Integer, nullable=False, index=True)
    scene_name = Column(String, nullable=False, default="")

    revision = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, default="draft")
    execution_status = Column(String, nullable=False, default="queued")
    quality_status = Column(String, nullable=False, default="draft")
    production_status = Column(String, nullable=False, default="blocked")
    workflow_profile = Column(String, nullable=False, default="creative_draft")

    source_script_revision = Column(String, nullable=False, default="")
    source_script_hash = Column(String, nullable=False, default="")

    dramatic_objective = Column(Text, nullable=False, default="")
    audience_question = Column(Text, nullable=False, default="")
    character_intents = Column(Text, nullable=False, default="{}")
    beat_map = Column(Text, nullable=False, default="[]")
    relationship_power_shift = Column(Text, nullable=False, default="")
    audience_emotion = Column(Text, nullable=False, default="")
    information_strategy = Column(Text, nullable=False, default="")
    performance_direction = Column(Text, nullable=False, default="")
    visual_strategy = Column(Text, nullable=False, default="")
    coverage_strategy = Column(Text, nullable=False, default="")
    sound_strategy = Column(Text, nullable=False, default="")
    edit_rhythm = Column(Text, nullable=False, default="")

    constraints = Column(Text, nullable=False, default="[]")
    unknowns = Column(Text, nullable=False, default="[]")
    skill_id = Column(String, nullable=False, default="")
    skill_version = Column(String, nullable=False, default="")
    decision_packet_id = Column(Integer, nullable=True)
    model_info = Column(Text, nullable=False, default="{}")
    prompt_fingerprint = Column(String, nullable=False, default="")

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)
