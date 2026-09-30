"""Durable business retry/regenerate attempt lineage."""

from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from .base import Base


class GenerationExecutionAttemptLineage(Base):
    __tablename__ = "generation_execution_attempt_lineages"
    __table_args__ = (
        UniqueConstraint("attempt_lineage_id", name="uq_generation_attempt_lineage_id"),
        UniqueConstraint("book_id", "operation_idempotency_key", name="uq_generation_attempt_operation_key"),
        UniqueConstraint("produced_execution_id", name="uq_generation_attempt_produced_execution"),
        CheckConstraint("operation_kind IN ('RETRY','REGENERATE')", name="ck_generation_attempt_operation_kind"),
        CheckConstraint("target_media IN ('IMAGE','VIDEO')", name="ck_generation_attempt_target_media"),
        CheckConstraint("status IN ('PREVIEWED','BOUND','CANCELLED')", name="ck_generation_attempt_status"),
        CheckConstraint("attempt_number >= 1", name="ck_generation_attempt_number"),
        CheckConstraint("variant_index >= 0", name="ck_generation_attempt_variant_index"),
    )

    id = Column(Integer, primary_key=True)
    attempt_lineage_id = Column(String, nullable=False, unique=True, index=True)
    operation_idempotency_key = Column(String, nullable=False)
    operation_kind = Column(String, nullable=False, index=True)
    book_id = Column(Integer, nullable=False, index=True)
    episode = Column(Integer, nullable=False, index=True)
    storyboard_shot_id = Column(Integer, nullable=False, index=True)
    target_media = Column(String, nullable=False, index=True)
    source_execution_id = Column(String, ForeignKey("generation_execution_records.execution_id", ondelete="RESTRICT"), nullable=False, index=True)
    root_execution_id = Column(String, ForeignKey("generation_execution_records.execution_id", ondelete="RESTRICT"), nullable=False, index=True)
    produced_execution_id = Column(String, ForeignKey("generation_execution_records.execution_id", ondelete="RESTRICT"), nullable=True, index=True)
    attempt_number = Column(Integer, nullable=False, default=1)
    variant_index = Column(Integer, nullable=False, default=1)
    reason = Column(Text, nullable=False, default="")
    source_candidate_id = Column(String, nullable=True, index=True)
    source_official_media_version_id = Column(String, nullable=True, index=True)
    source_snapshot_fingerprint = Column(String, nullable=False, index=True)
    operation_identity_fingerprint = Column(String, nullable=False, index=True)
    confirmation_binding_hash = Column(String, nullable=False)
    status = Column(String, nullable=False, default="PREVIEWED", index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
