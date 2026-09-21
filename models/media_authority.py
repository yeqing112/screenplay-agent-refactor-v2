"""Phase G2 validation and official media authority persistence models."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint

from .base import Base


class MediaValidationRecord(Base):
    __tablename__ = "media_validation_records"
    __table_args__ = (
        UniqueConstraint("candidate_fingerprint", "authority_snapshot_fingerprint", "validator_version", name="uq_media_validation_idempotency"),
    )

    id = Column(Integer, primary_key=True)
    validation_id = Column(String, nullable=False, unique=True, index=True)
    candidate_id = Column(String, nullable=False, index=True)
    execution_id = Column(String, nullable=False, index=True)
    candidate_fingerprint = Column(String, nullable=False, index=True)
    technical_validation_payload_json = Column(Text, nullable=False, default="{}")
    technical_validation_fingerprint = Column(String, nullable=False)
    authority_snapshot_json = Column(Text, nullable=False, default="{}")
    authority_snapshot_fingerprint = Column(String, nullable=False)
    validator_version = Column(String, nullable=False)
    status = Column(String, nullable=False, default="VALIDATION_PENDING", index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow)


class OfficialMediaVersion(Base):
    __tablename__ = "official_media_versions"
    __table_args__ = (
        UniqueConstraint("book_id", "episode", "storyboard_shot_id", "media_role", "revision", name="uq_official_media_version_revision"),
    )

    id = Column(Integer, primary_key=True)
    official_media_version_id = Column(String, nullable=False, unique=True, index=True)
    book_id = Column(Integer, nullable=False, index=True)
    episode = Column(Integer, nullable=False, index=True)
    storyboard_shot_id = Column(Integer, nullable=False, index=True)
    plan_shot_id = Column(String, nullable=False, default="")
    media_role = Column(String, nullable=False, index=True)
    media_type = Column(String, nullable=False)
    candidate_id = Column(String, nullable=False, index=True)
    candidate_fingerprint = Column(String, nullable=False, index=True)
    storage_identity = Column(String, nullable=False)
    checksum_sha256 = Column(String, nullable=False)
    mime_type = Column(String, nullable=False)
    byte_size = Column(Integer, nullable=False)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    prompt_ir_version_id = Column(Integer, nullable=False)
    prompt_ir_payload_hash = Column(String, nullable=False)
    generation_payload_fingerprint = Column(String, nullable=False)
    provider_request_fingerprint = Column(String, nullable=False)
    provider_response_hash = Column(String, nullable=False)
    validation_id = Column(String, nullable=False, index=True)
    validation_fingerprint = Column(String, nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, default="CURRENT", index=True)
    payload_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class OfficialMediaAuthority(Base):
    __tablename__ = "official_media_authorities"
    __table_args__ = (UniqueConstraint("official_media_version_id", name="uq_official_media_authority_version"),)

    id = Column(Integer, primary_key=True)
    authority_id = Column(String, nullable=False, unique=True, index=True)
    official_media_version_id = Column(String, nullable=False, index=True)
    authority_envelope_json = Column(Text, nullable=False, default="{}")
    payload_hash = Column(String, nullable=False)
    lineage_hash = Column(String, nullable=False, index=True)
    validation_fingerprint = Column(String, nullable=False)
    promotion_fingerprint = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="CURRENT", index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class OfficialMediaPointer(Base):
    __tablename__ = "official_media_pointers"
    __table_args__ = (UniqueConstraint("book_id", "episode", "storyboard_shot_id", "media_role", name="uq_official_media_pointer_scope"),)

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    episode = Column(Integer, nullable=False, index=True)
    storyboard_shot_id = Column(Integer, nullable=False, index=True)
    media_role = Column(String, nullable=False)
    official_media_version_id = Column(String, nullable=False, index=True)
    authority_id = Column(String, nullable=False, index=True)
    fingerprint = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
