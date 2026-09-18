"""Versioned visual asset authority persistence models."""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from .base import Base


class VisualAssetVersion(Base):
    __tablename__ = "visual_asset_versions"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    asset_key = Column(String, nullable=False, index=True)
    asset_type = Column(String, nullable=False, index=True)
    canonical_id = Column(String, nullable=False, index=True)
    canonical_identity_json = Column(Text, nullable=False, default="{}")
    scope_json = Column(Text, nullable=False, default="{}")
    revision = Column(Integer, nullable=False, default=1)
    base_version_id = Column(Integer, nullable=True)
    payload_json = Column(Text, nullable=False, default="{}")
    payload_hash = Column(String, nullable=False, index=True)
    source_constraints_json = Column(Text, nullable=False, default="[]")
    authoring_decisions_json = Column(Text, nullable=False, default="[]")
    variant_binding_json = Column(Text, nullable=False, default="{}")
    source_constraint_fingerprint = Column(String, nullable=False, default="")
    authoring_decision_fingerprint = Column(String, nullable=False, default="")
    variant_fingerprint = Column(String, nullable=False, default="")
    authority_status = Column(String, nullable=False, default="SPEC_DRAFT")
    stale_status = Column(String, nullable=False, default="FRESH")
    stale_reasons = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class VisualAssetPointer(Base):
    __tablename__ = "visual_asset_pointers"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    asset_key = Column(String, nullable=False, index=True)
    asset_type = Column(String, nullable=False, index=True)
    scope_key = Column(String, nullable=False, index=True)
    current_version_id = Column(Integer, nullable=False, unique=True)
    payload_hash = Column(String, nullable=False)
    authority_status = Column(String, nullable=False, default="SPEC_APPROVED")
    stale_status = Column(String, nullable=False, default="FRESH")
    stale_reasons = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class VisualAuthoringDecisionRequest(Base):
    __tablename__ = "visual_authoring_decision_requests"

    id = Column(Integer, primary_key=True)
    request_id = Column(String, nullable=False, unique=True, index=True)
    book_id = Column(Integer, nullable=False, index=True)
    asset_key = Column(String, nullable=False, index=True)
    asset_type = Column(String, nullable=False)
    missing_field = Column(String, nullable=False)
    source_constraints_json = Column(Text, nullable=False, default="[]")
    free_authoring_space_json = Column(Text, nullable=False, default="{}")
    forbidden_contradictions_json = Column(Text, nullable=False, default="[]")
    scope_json = Column(Text, nullable=False, default="{}")
    required_by_stage = Column(String, nullable=False, default="PromptIR")
    status = Column(String, nullable=False, default="PENDING")
    resolution_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class VisualAuthoringDecision(Base):
    __tablename__ = "visual_authoring_decisions"

    id = Column(Integer, primary_key=True)
    decision_id = Column(String, nullable=False, unique=True, index=True)
    request_id = Column(String, nullable=True, index=True)
    book_id = Column(Integer, nullable=False, index=True)
    asset_key = Column(String, nullable=False, index=True)
    asset_type = Column(String, nullable=False)
    field = Column(String, nullable=False)
    value_json = Column(Text, nullable=False, default="null")
    scope_json = Column(Text, nullable=False, default="{}")
    authority_class = Column(String, nullable=False, default="PRODUCTION_VISUAL_AUTHORING_DECISION")
    source_constraint_refs_json = Column(Text, nullable=False, default="[]")
    author = Column(String, nullable=False, default="human")
    authoring_policy = Column(String, nullable=False, default="visual_authoring_policy_v1")
    status = Column(String, nullable=False, default="PROPOSED")
    provenance_json = Column(Text, nullable=False, default="{}")
    revision = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class VisualReferenceAuthority(Base):
    __tablename__ = "visual_reference_authorities"

    id = Column(Integer, primary_key=True)
    visual_reference_asset_id = Column(Integer, nullable=False, index=True)
    asset_key = Column(String, nullable=False, index=True)
    asset_version_id = Column(Integer, nullable=False, index=True)
    asset_version_fingerprint = Column(String, nullable=False)
    reference_scope_json = Column(Text, nullable=False, default="{}")
    image_identity = Column(String, nullable=False)
    checksum = Column(String, nullable=False)
    storage_reference_json = Column(Text, nullable=False, default="{}")
    generation_provenance_json = Column(Text, nullable=False, default="{}")
    reference_token_mapping_json = Column(Text, nullable=False, default="{}")
    lock_revision = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, default="CANDIDATE")
    authority_fingerprint = Column(String, nullable=False, unique=True, index=True)
    stale_status = Column(String, nullable=False, default="FRESH")
    stale_reasons = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class VisualReferenceSet(Base):
    __tablename__ = "visual_reference_sets"

    id = Column(Integer, primary_key=True)
    asset_key = Column(String, nullable=False, index=True)
    asset_version_id = Column(Integer, nullable=False, index=True)
    set_type = Column(String, nullable=False, default="single_hero_reference")
    roles_json = Column(Text, nullable=False, default="[]")
    status = Column(String, nullable=False, default="CANDIDATE")
    fingerprint = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class VisualReferenceGenerationRequest(Base):
    __tablename__ = "visual_reference_generation_requests"

    id = Column(Integer, primary_key=True)
    request_fingerprint = Column(String, nullable=False, unique=True, index=True)
    asset_key = Column(String, nullable=False, index=True)
    asset_version_id = Column(Integer, nullable=False, index=True)
    variant_id = Column(String, nullable=False, default="")
    request_json = Column(Text, nullable=False, default="{}")
    status = Column(String, nullable=False, default="READY_FOR_PROVIDER_CANARY")
    provider_not_called = Column(String, nullable=False, default="true")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)
