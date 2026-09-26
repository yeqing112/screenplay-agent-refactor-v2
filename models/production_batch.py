"""Durable production image batch orchestration records."""

from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from .base import Base


class ProductionBatch(Base):
    """One ordered image-generation batch for a project episode."""

    __tablename__ = "production_batches"
    __table_args__ = (
        UniqueConstraint("batch_key", name="uq_production_batch_key"),
        UniqueConstraint("task_id", name="uq_production_batch_task_id"),
        CheckConstraint(
            "status IN ('CREATED','QUEUED','RUNNING','COMPLETED','FAILED')",
            name="ck_production_batch_status",
        ),
    )

    id = Column(Integer, primary_key=True)
    batch_key = Column(String, nullable=False, unique=True, index=True)
    project_id = Column(Integer, nullable=False, index=True)
    episode_id = Column(Integer, nullable=False, index=True)
    # ``episode_number`` is the resolved StoryboardShot scope.  It remains
    # separate from episode_id so callers may pass either an EpisodeOutline id
    # or the existing numeric episode scope without losing the original input.
    episode_number = Column(Integer, nullable=False, index=True)
    task_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="CREATED", index=True)
    total_tasks = Column(Integer, nullable=False, default=0)
    completed_tasks = Column(Integer, nullable=False, default=0)
    failed_tasks = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True)


class ProductionBatchItem(Base):
    """One shot-to-GenerationExecution binding within a ProductionBatch."""

    __tablename__ = "production_batch_items"
    __table_args__ = (
        UniqueConstraint("batch_id", "shot_id", name="uq_production_batch_item_shot"),
        UniqueConstraint("execution_id", name="uq_production_batch_item_execution"),
        CheckConstraint(
            "status IN ('CREATED','QUEUED','RUNNING','SUCCEEDED','FAILED','RETRYING','SKIPPED')",
            name="ck_production_batch_item_status",
        ),
    )

    id = Column(Integer, primary_key=True)
    batch_id = Column(Integer, ForeignKey("production_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    shot_id = Column(Integer, nullable=False, index=True)
    execution_id = Column(String, ForeignKey("generation_execution_records.execution_id", ondelete="RESTRICT"), nullable=False, index=True)
    status = Column(String, nullable=False, default="CREATED", index=True)
    priority = Column(Integer, nullable=False, default=0, index=True)
    retry_count = Column(Integer, nullable=False, default=0)
    candidate_id = Column(String, nullable=True, index=True)
    promotion_id = Column(String, nullable=True, index=True)
    error = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


__all__ = ["ProductionBatch", "ProductionBatchItem"]
