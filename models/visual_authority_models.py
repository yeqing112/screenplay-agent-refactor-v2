"""Database models for provider proposals and authority review artifacts."""

from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint
from .base import Base


class VisualAuthoringDecisionRequest(Base):
    __tablename__ = "visual_authoring_decision_requests"
    id = Column(Integer, primary_key=True)
    request_id = Column(String(128), nullable=False, unique=True, index=True)
    book_id = Column(Integer, nullable=False, index=True)
    asset_key = Column(String(255), nullable=False, index=True)
    asset_type = Column(String(32), nullable=False)
    canonical_id = Column(String(128), nullable=False)
    scope = Column(Text, nullable=False, default="{}")
    source_constraints = Column(Text, nullable=False, default="{}")
    free_authoring_space = Column(Text, nullable=False, default="[]")
    forbidden_contradictions = Column(Text, nullable=False, default="[]")
    context_json = Column(Text, nullable=False, default="{}")
    status = Column(String(32), nullable=False, default="PENDING")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class VisualAuthoringDecision(Base):
    __tablename__ = "visual_authoring_decisions"
    id = Column(Integer, primary_key=True)
    decision_id = Column(String(128), nullable=False, unique=True, index=True)
    request_id = Column(String(128), nullable=False, index=True)
    book_id = Column(Integer, nullable=False, index=True)
    asset_key = Column(String(255), nullable=False)
    asset_type = Column(String(32), nullable=False)
    decision_json = Column(Text, nullable=False, default="{}")
    confirmed = Column(Integer, nullable=False, default=0)
    status = Column(String(32), nullable=False, default="APPROVED")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class VisualAuthoringProposal(Base):
    __tablename__ = "visual_authoring_proposals"
    __table_args__ = (UniqueConstraint("request_id", "provider_request_fingerprint", name="uq_visual_authoring_proposal_request_fingerprint"),)
    id = Column(Integer, primary_key=True)
    proposal_id = Column(String(128), nullable=False, unique=True, index=True)
    request_id = Column(String(128), nullable=False, index=True)
    book_id = Column(Integer, nullable=False, index=True)
    asset_key = Column(String(255), nullable=False)
    asset_type = Column(String(32), nullable=False)
    scope = Column(Text, nullable=False, default="{}")
    proposed_fields_json = Column(Text, nullable=False, default="{}")
    explanation_summary = Column(Text, nullable=False, default="")
    source_constraint_refs = Column(Text, nullable=False, default="[]")
    provider_profile_id = Column(String(128), nullable=False)
    provider_model = Column(String(255), nullable=False, default="")
    provider_vendor_host = Column(String(255), nullable=False, default="")
    provider_request_fingerprint = Column(String(128), nullable=False, index=True)
    provider_response_hash = Column(String(128), nullable=False, default="")
    proposal_payload_hash = Column(String(128), nullable=False, default="")
    validator_status = Column(String(32), nullable=False, default="PENDING")
    validator_diagnostics = Column(Text, nullable=False, default="{}")
    audit_json = Column(Text, nullable=False, default="{}")
    status = Column(String(32), nullable=False, default="CANDIDATE")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class VisualAssetVersion(Base):
    __tablename__ = "visual_asset_versions"
    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    asset_key = Column(String(255), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    payload_json = Column(Text, nullable=False, default="{}")
    status = Column(String(32), nullable=False, default="DRAFT")
    created_at = Column(DateTime, default=datetime.utcnow)


class VisualAssetPointer(Base):
    __tablename__ = "visual_asset_pointers"
    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    asset_key = Column(String(255), nullable=False, unique=True)
    version_id = Column(Integer, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)


class VisualReferenceAuthority(Base):
    __tablename__ = "visual_reference_authorities"
    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    asset_key = Column(String(255), nullable=False, index=True)
    reference_json = Column(Text, nullable=False, default="{}")
    status = Column(String(32), nullable=False, default="CANDIDATE")
    created_at = Column(DateTime, default=datetime.utcnow)
