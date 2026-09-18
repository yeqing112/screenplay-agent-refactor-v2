"""ShotPlan model: executable shot intent between blocking and StoryboardShot."""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from .base import Base


class ShotPlan(Base):
    __tablename__ = "shot_plans"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    episode = Column(Integer, nullable=False, index=True)
    scene_id = Column(String, nullable=False, default="", index=True)
    scene_name = Column(String, nullable=False, default="")
    revision = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, default="draft")  # draft / approved / superseded
    schema_version = Column(String, nullable=False, default="shot_plan_v1")
    execution_status = Column(String, nullable=False, default="queued")
    quality_status = Column(String, nullable=False, default="draft")
    production_status = Column(String, nullable=False, default="blocked")
    workflow_profile = Column(String, nullable=False, default="creative_draft")
    treatment_id = Column(Integer, nullable=True)
    blocking_id = Column(Integer, nullable=True)
    shots = Column(Text, nullable=False, default="[]")
    unknowns = Column(Text, nullable=False, default="[]")
    evidence_fingerprint = Column(String, nullable=False, default="")
    model_info = Column(Text, nullable=False, default="{}")
    # Production authority projections. Legacy rows remain readable but are
    # never promoted without an explicit ShotPlan authority envelope/pointer.
    source_script_ir_version_id = Column(Integer, nullable=True, index=True)
    source_script_ir_revision = Column(Integer, nullable=True)
    source_script_ir_hash = Column(String, nullable=False, default="")
    source_script_authority_fingerprint = Column(String, nullable=False, default="")
    treatment_authority_fingerprint = Column(String, nullable=False, default="")
    treatment_payload_hash = Column(String, nullable=False, default="")
    blocking_authority_fingerprint = Column(String, nullable=False, default="")
    blocking_payload_hash = Column(String, nullable=False, default="")
    source_fact_snapshot_id = Column(String, nullable=False, default="")
    source_fact_snapshot_revision = Column(Integer, nullable=True)
    source_fact_snapshot_hash = Column(String, nullable=False, default="")
    source_immutable_raw_hash = Column(String, nullable=False, default="")
    contract_fingerprint = Column(String, nullable=False, default="")
    executability_fingerprint = Column(String, nullable=False, default="")
    continuity_fingerprint = Column(String, nullable=False, default="")
    payload_hash = Column(String, nullable=False, default="")
    authority_envelope_id = Column(Integer, nullable=True, index=True)
    qualification_state = Column(String, nullable=False, default="DRAFT")
    stale_status = Column(String, nullable=False, default="UNKNOWN")
    stale_reasons = Column(Text, nullable=False, default="[]")
    source_lineage = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class ShotPlanAuthority(Base):
    """Immutable authority envelope for a production ShotPlan."""

    __tablename__ = "shot_plan_authorities"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    episode = Column(Integer, nullable=False, index=True)
    scene_id = Column(String, nullable=False, index=True)
    shot_plan_id = Column(Integer, nullable=False, unique=True, index=True)
    plan_revision = Column(Integer, nullable=False)
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


class ShotPlanPointer(Base):
    """Explicit scene -> current authoritative ShotPlan selection."""

    __tablename__ = "shot_plan_pointers"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    episode = Column(Integer, nullable=False, index=True)
    scene_id = Column(String, nullable=False, index=True)
    shot_plan_id = Column(Integer, nullable=False)
    plan_revision = Column(Integer, nullable=False)
    authority_envelope_fingerprint = Column(String, nullable=False)
    qualification_state = Column(String, nullable=False, default="PRODUCTION_QUALIFIED")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)
