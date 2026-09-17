"""SceneBlocking / Spatial Engine persistence model."""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from .base import Base


class SceneBlocking(Base):
    __tablename__ = "scene_blockings"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    episode = Column(Integer, nullable=False, index=True)
    scene_id = Column(String, nullable=False, default="", index=True)
    scene_name = Column(String, nullable=False, default="")
    revision = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, default="draft")  # draft / approved / superseded
    execution_status = Column(String, nullable=False, default="queued")
    quality_status = Column(String, nullable=False, default="draft")
    production_status = Column(String, nullable=False, default="blocked")
    workflow_profile = Column(String, nullable=False, default="creative_draft")
    # V2 keeps the legacy columns above readable while storing the semantic
    # spatial model in additive JSON columns.  Existing rows remain V1 until
    # explicitly regenerated; no historical artifact is rewritten.
    schema_version = Column(String, nullable=False, default="scene_blocking_v1")
    treatment_id = Column(Integer, nullable=True)
    treatment_revision = Column(Integer, nullable=True)
    source_script_hash = Column(String, nullable=False, default="")
    participants = Column(Text, nullable=False, default="[]")
    beat_transitions = Column(Text, nullable=False, default="[]")
    spatial_rules = Column(Text, nullable=False, default="[]")
    unknowns = Column(Text, nullable=False, default="[]")
    evidence_fingerprint = Column(String, nullable=False, default="")
    model_info = Column(Text, nullable=False, default="{}")
    spatial_model = Column(Text, nullable=False, default="{}")
    source_spatial_facts = Column(Text, nullable=False, default="[]")
    creative_decisions = Column(Text, nullable=False, default="[]")
    derived_constraints = Column(Text, nullable=False, default="{}")
    unresolved_facts = Column(Text, nullable=False, default="[]")
    camera_axis = Column(Text, nullable=False, default="{}")
    validation = Column(Text, nullable=False, default="{}")
    # Production authority projections.  Legacy rows remain readable and are
    # never promoted implicitly; only an explicit authority envelope/pointer
    # makes a row consumable by the production ShotPlan gate.
    source_script_ir_version_id = Column(Integer, nullable=True, index=True)
    source_script_ir_revision = Column(Integer, nullable=True)
    source_script_ir_hash = Column(String, nullable=False, default="")
    source_script_authority_fingerprint = Column(String, nullable=False, default="")
    treatment_authority_fingerprint = Column(String, nullable=False, default="")
    treatment_payload_hash = Column(String, nullable=False, default="")
    source_fact_snapshot_id = Column(String, nullable=False, default="")
    source_fact_snapshot_revision = Column(Integer, nullable=True)
    source_fact_snapshot_hash = Column(String, nullable=False, default="")
    source_immutable_raw_hash = Column(String, nullable=False, default="")
    contract_fingerprint = Column(String, nullable=False, default="")
    validation_fingerprint = Column(String, nullable=False, default="")
    payload_hash = Column(String, nullable=False, default="")
    authority_envelope_id = Column(Integer, nullable=True, index=True)
    qualification_state = Column(String, nullable=False, default="DRAFT")
    stale_status = Column(String, nullable=False, default="UNKNOWN")
    stale_reasons = Column(Text, nullable=False, default="[]")
    asset_authority = Column(Text, nullable=False, default="{}")
    continuity_state = Column(Text, nullable=False, default="{}")
    source_lineage = Column(Text, nullable=False, default="{}")
    activated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class SceneBlockingAuthority(Base):
    """Immutable authority envelope for a production SceneBlocking row."""

    __tablename__ = "scene_blocking_authorities"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    episode = Column(Integer, nullable=False, index=True)
    scene_id = Column(String, nullable=False, index=True)
    blocking_id = Column(Integer, nullable=False, unique=True, index=True)
    blocking_revision = Column(Integer, nullable=False)
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


class SceneBlockingPointer(Base):
    """Explicit scene -> current authoritative SceneBlocking selection."""

    __tablename__ = "scene_blocking_pointers"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    episode = Column(Integer, nullable=False, index=True)
    scene_id = Column(String, nullable=False, index=True)
    blocking_id = Column(Integer, nullable=False)
    blocking_revision = Column(Integer, nullable=False)
    authority_envelope_fingerprint = Column(String, nullable=False)
    qualification_state = Column(String, nullable=False, default="PRODUCTION_QUALIFIED")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)
