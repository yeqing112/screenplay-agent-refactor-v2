"""Human review workflow records for typed Production Asset Versions."""
from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text

from .base import Base


REVIEW_STATES = (
    "GENERATED",
    "NORMALIZED",
    "AI_VALIDATED",
    "HUMAN_REVIEW_PENDING",
    "HUMAN_APPROVED",
    "PRODUCTION_READY",
    "ARCHIVED",
    "REJECTED",
    "REQUEST_CHANGE",
)
REVIEWER_TYPES = ("DIRECTOR", "ART_DIRECTOR", "PRODUCER", "SYSTEM")
REVIEW_DECISIONS = ("APPROVE", "REJECT", "REQUEST_CHANGE")


class ProductionAssetReview(Base):
    __tablename__ = "production_asset_reviews"

    id = Column(Integer, primary_key=True)
    review_id = Column(String, nullable=False, unique=True, index=True)
    asset_type = Column(String, nullable=False, index=True)
    asset_id = Column(String, nullable=False, index=True)
    asset_version_id = Column(
        String,
        ForeignKey("production_asset_version_registry.version_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    prompt_lineage_id = Column(
        String,
        ForeignKey("production_prompt_lineages.prompt_lineage_id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    review_state = Column(String, nullable=False, index=True)
    reviewer_type = Column(String, nullable=False)
    decision = Column(String, nullable=True)
    comment = Column(Text, nullable=True)
    version_fingerprint = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("asset_type IN ('CHARACTER','SCENE','PROP')", name="ck_production_asset_review_asset_type"),
        CheckConstraint(
            "review_state IN ('GENERATED','NORMALIZED','AI_VALIDATED','HUMAN_REVIEW_PENDING','HUMAN_APPROVED','PRODUCTION_READY','ARCHIVED','REJECTED','REQUEST_CHANGE')",
            name="ck_production_asset_review_state",
        ),
        CheckConstraint("reviewer_type IN ('DIRECTOR','ART_DIRECTOR','PRODUCER','SYSTEM')", name="ck_production_asset_review_reviewer_type"),
        CheckConstraint("decision IS NULL OR decision IN ('APPROVE','REJECT','REQUEST_CHANGE')", name="ck_production_asset_review_decision"),
    )


class ProductionAssetReviewHistory(Base):
    __tablename__ = "production_asset_review_history"

    id = Column(Integer, primary_key=True)
    history_id = Column(String, nullable=False, unique=True, index=True)
    review_id = Column(
        String,
        ForeignKey("production_asset_reviews.review_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    asset_version_id = Column(
        String,
        ForeignKey("production_asset_version_registry.version_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    from_state = Column(String, nullable=True)
    to_state = Column(String, nullable=False)
    actor = Column(String, nullable=False)
    decision = Column(String, nullable=True)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("from_state IS NULL OR from_state IN ('GENERATED','NORMALIZED','AI_VALIDATED','HUMAN_REVIEW_PENDING','HUMAN_APPROVED','PRODUCTION_READY','ARCHIVED','REJECTED','REQUEST_CHANGE')", name="ck_production_asset_review_history_from_state"),
        CheckConstraint("to_state IN ('GENERATED','NORMALIZED','AI_VALIDATED','HUMAN_REVIEW_PENDING','HUMAN_APPROVED','PRODUCTION_READY','ARCHIVED','REJECTED','REQUEST_CHANGE')", name="ck_production_asset_review_history_to_state"),
        CheckConstraint("actor IN ('DIRECTOR','ART_DIRECTOR','PRODUCER','SYSTEM')", name="ck_production_asset_review_history_actor"),
        CheckConstraint("decision IS NULL OR decision IN ('APPROVE','REJECT','REQUEST_CHANGE')", name="ck_production_asset_review_history_decision"),
    )


__all__ = [
    "REVIEW_STATES",
    "REVIEWER_TYPES",
    "REVIEW_DECISIONS",
    "ProductionAssetReview",
    "ProductionAssetReviewHistory",
]
