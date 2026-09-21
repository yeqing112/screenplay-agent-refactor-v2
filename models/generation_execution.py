"""Durable Phase F generation execution and media-candidate records."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint

from .base import Base


class GenerationExecutionRecord(Base):
    """One preview or explicitly authorised provider execution attempt.

    The request fingerprint is the durable idempotency boundary.  Provider
    secrets are intentionally absent; request/response snapshots are
    canonical non-secret audit projections only.
    """

    __tablename__ = "generation_execution_records"
    __table_args__ = (
        UniqueConstraint("provider_request_fingerprint", name="uq_generation_execution_provider_request_fingerprint"),
    )

    id = Column(Integer, primary_key=True)
    execution_id = Column(String, nullable=False, unique=True, index=True)
    schema_version = Column(String, nullable=False, default="generation_execution_request_v1")
    book_id = Column(Integer, nullable=False, index=True)
    episode = Column(Integer, nullable=False, index=True)
    storyboard_shot_id = Column(Integer, nullable=False, index=True)
    plan_shot_id = Column(String, nullable=False, default="")
    execution_mode = Column(String, nullable=False, default="PREVIEW")
    status = Column(String, nullable=False, default="PREVIEWED", index=True)
    target_media = Column(String, nullable=False, default="IMAGE")
    prompt_ir_version_id = Column(Integer, nullable=False, index=True)
    prompt_ir_authority_id = Column(Integer, nullable=False, index=True)
    prompt_ir_payload_hash = Column(String, nullable=False)
    generation_payload_fingerprint = Column(String, nullable=False, index=True)
    generation_policy_fingerprint = Column(String, nullable=False)
    model_profile_id = Column(String, nullable=False)
    model_profile_fingerprint = Column(String, nullable=False)
    provider_adapter_id = Column(String, nullable=False)
    provider_adapter_version = Column(String, nullable=False)
    reference_bindings_fingerprint = Column(String, nullable=False, default="")
    provider_request_fingerprint = Column(String, nullable=False, index=True)
    request_snapshot_json = Column(Text, nullable=False, default="{}")
    confirmation_binding_hash = Column(String, nullable=False, default="")
    provider = Column(String, nullable=False, default="")
    model = Column(String, nullable=False, default="")
    provider_request_id = Column(String, nullable=False, default="")
    provider_task_id = Column(String, nullable=False, default="")
    provider_response_hash = Column(String, nullable=False, default="")
    logical_provider_calls = Column(Integer, nullable=False, default=0)
    transport_retry_count = Column(Integer, nullable=False, default=0)
    submitted_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    failure_code = Column(String, nullable=False, default="")
    failure_message = Column(Text, nullable=False, default="")
    official_promotion_count = Column(Integer, nullable=False, default=0)
    candidate_id = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, index=True)


class MediaCandidateRecord(Base):
    """Canonical bytes and provenance below official media authority."""

    __tablename__ = "media_candidate_records"
    __table_args__ = (
        UniqueConstraint("execution_id", name="uq_media_candidate_execution_id"),
        UniqueConstraint("storage_identity", name="uq_media_candidate_storage_identity"),
    )

    id = Column(Integer, primary_key=True)
    candidate_id = Column(String, nullable=False, unique=True, index=True)
    execution_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="MEDIA_CANDIDATE", index=True)
    media_type = Column(String, nullable=False)
    storage_identity = Column(String, nullable=False, index=True)
    storage_reference_json = Column(Text, nullable=False, default="{}")
    checksum_sha256 = Column(String, nullable=False, index=True)
    mime_type = Column(String, nullable=False)
    byte_size = Column(Integer, nullable=False)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    prompt_ir_version_id = Column(Integer, nullable=False, index=True)
    prompt_ir_payload_hash = Column(String, nullable=False)
    generation_payload_fingerprint = Column(String, nullable=False, index=True)
    model_profile_id = Column(String, nullable=False)
    model_profile_fingerprint = Column(String, nullable=False)
    provider_request_fingerprint = Column(String, nullable=False, index=True)
    provider_response_hash = Column(String, nullable=False)
    provider_task_id = Column(String, nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
