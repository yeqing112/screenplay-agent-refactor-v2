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
    # Stable ScriptIR scene identity.  ``scene_name`` remains a display/legacy
    # field; production authority never relies on it alone.
    scene_id = Column(String, nullable=False, default="", index=True)
    scene_name = Column(String, nullable=False, default="")

    revision = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, default="draft")
    execution_status = Column(String, nullable=False, default="queued")
    quality_status = Column(String, nullable=False, default="draft")
    production_status = Column(String, nullable=False, default="blocked")
    workflow_profile = Column(String, nullable=False, default="creative_draft")

    source_script_revision = Column(String, nullable=False, default="")
    source_script_hash = Column(String, nullable=False, default="")
    source_script_ir_version_id = Column(Integer, nullable=True, index=True)
    source_script_ir_revision = Column(Integer, nullable=True)
    source_script_ir_hash = Column(String, nullable=False, default="")
    source_script_authority_fingerprint = Column(String, nullable=False, default="")
    source_fact_snapshot_id = Column(String, nullable=False, default="")
    source_fact_snapshot_revision = Column(Integer, nullable=True)
    source_fact_snapshot_hash = Column(String, nullable=False, default="")

    dramatic_objective = Column(Text, nullable=False, default="")
    audience_question = Column(Text, nullable=False, default="")
    character_intents = Column(Text, nullable=False, default="{}")
    beat_map = Column(Text, nullable=False, default="[]")
    source_constraints = Column(Text, nullable=False, default="{}")
    director_decisions = Column(Text, nullable=False, default="{}")
    unknown_unresolved = Column(Text, nullable=False, default="[]")
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
    payload_hash = Column(String, nullable=False, default="")
    authority_envelope_id = Column(Integer, nullable=True, index=True)
    qualification_state = Column(String, nullable=False, default="DRAFT")
    stale_status = Column(String, nullable=False, default="UNKNOWN")
    stale_reasons = Column(Text, nullable=False, default="[]")
    approved_at = Column(DateTime, nullable=True)
    activated_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class DirectorTreatmentAuthority(Base):
    """Immutable lineage envelope explaining why a Treatment is authoritative."""

    __tablename__ = "director_treatment_authorities"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    episode = Column(Integer, nullable=False, index=True)
    scene_id = Column(String, nullable=False, index=True)
    treatment_id = Column(Integer, nullable=False, unique=True, index=True)
    treatment_revision = Column(Integer, nullable=False)
    payload_hash = Column(String, nullable=False)
    envelope_fingerprint = Column(String, nullable=False, unique=True)
    envelope_json = Column(Text, nullable=False, default="{}")
    qualification_state = Column(String, nullable=False, default="AUTHORITY_BOUND")
    stale_status = Column(String, nullable=False, default="FRESH")
    stale_reasons = Column(Text, nullable=False, default="[]")
    approved_at = Column(DateTime, nullable=True)
    activated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class DirectorTreatmentPointer(Base):
    """Explicit scene -> current authoritative Treatment selection."""

    __tablename__ = "director_treatment_pointers"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    episode = Column(Integer, nullable=False, index=True)
    scene_id = Column(String, nullable=False, index=True)
    treatment_id = Column(Integer, nullable=False)
    treatment_revision = Column(Integer, nullable=False)
    authority_envelope_fingerprint = Column(String, nullable=False)
    qualification_state = Column(String, nullable=False, default="PRODUCTION_QUALIFIED")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)
