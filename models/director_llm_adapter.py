"""Durable audit state for Director LLM adapter generation attempts."""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text

from .base import Base


class DirectorReasoningGeneration(Base):
    """One provider invocation that may produce a reviewable reasoning draft.

    The adapter never receives a database session.  This record is written by
    the API boundary before/after the adapter call so provider output cannot
    mutate production authority directly.
    """

    __tablename__ = "director_reasoning_generations"

    id = Column(Integer, primary_key=True)
    generation_id = Column(String, nullable=False, unique=True, index=True)
    episode_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="RUNNING", index=True)
    provider = Column(String, nullable=False, default="mock")
    adapter_name = Column(String, nullable=False, default="")
    context_hash = Column(String, nullable=False, default="")
    request_hash = Column(String, nullable=False, default="")
    response_hash = Column(String, nullable=False, default="")
    director_reasoning_id = Column(Integer, ForeignKey("director_reasonings.id", ondelete="SET NULL"), nullable=True, index=True)
    director_reasoning_version = Column(Integer, nullable=True)
    provider_calls = Column(Integer, nullable=False, default=0)
    source_fact_mutated = Column(Boolean, nullable=False, default=False)
    script_ir_mutated = Column(Boolean, nullable=False, default=False)
    human_review_required = Column(Boolean, nullable=False, default=True)
    error_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('RUNNING','REVIEW_REQUIRED','FAILED')", name="ck_director_reasoning_generation_status"),
        CheckConstraint("provider_calls >= 0", name="ck_director_reasoning_generation_provider_calls_nonnegative"),
    )


__all__ = ["DirectorReasoningGeneration"]
