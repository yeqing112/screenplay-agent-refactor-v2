"""Immutable production prompt and generation lineage records."""
from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, event

from .base import Base


class ProductionPromptVersion(Base):
    """An append-only version of a production prompt."""

    __tablename__ = "production_prompt_versions"

    id = Column(Integer, primary_key=True)
    prompt_version_id = Column(String, nullable=False, unique=True, index=True)
    prompt_id = Column(String, nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    prompt_text = Column(Text, nullable=False)
    prompt_structure = Column(Text, nullable=False, default="{}")
    prompt_fingerprint = Column(String, nullable=False, index=True)
    created_from = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("prompt_id", "version_number", name="uq_production_prompt_version_number"),
        CheckConstraint("version_number > 0", name="ck_production_prompt_version_positive"),
    )


class ProductionGenerationIntent(Base):
    """The shot-derived reason and constraints for generating an asset."""

    __tablename__ = "production_generation_intents"

    id = Column(Integer, primary_key=True)
    generation_intent_id = Column(String, nullable=False, unique=True, index=True)
    shot_id = Column(Integer, ForeignKey("storyboard_shots.id", ondelete="RESTRICT"), nullable=False, index=True)
    character_requirements = Column(Text, nullable=False, default="{}")
    scene_requirements = Column(Text, nullable=False, default="{}")
    camera_requirements = Column(Text, nullable=False, default="{}")
    style_requirements = Column(Text, nullable=False, default="{}")
    constraint_snapshot = Column(Text, nullable=False, default="{}")
    shot_requirement_snapshot = Column(Text, nullable=False, default="{}")
    shot_requirement_fingerprint = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ProductionPromptLineage(Base):
    """The auditable edge joining a shot, prompt, intent and asset version."""

    __tablename__ = "production_prompt_lineages"

    id = Column(Integer, primary_key=True)
    prompt_lineage_id = Column(String, nullable=False, unique=True, index=True)
    asset_id = Column(String, nullable=False, index=True)
    asset_version_id = Column(
        String,
        ForeignKey("production_asset_version_registry.version_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    shot_id = Column(Integer, ForeignKey("storyboard_shots.id", ondelete="RESTRICT"), nullable=False, index=True)
    prompt_version_id = Column(
        String,
        ForeignKey("production_prompt_versions.prompt_version_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    generation_intent_id = Column(
        String,
        ForeignKey("production_generation_intents.generation_intent_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    prompt_fingerprint = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "asset_version_id",
            "prompt_version_id",
            "generation_intent_id",
            name="uq_production_prompt_lineage_edge",
        ),
    )


@event.listens_for(ProductionPromptVersion, "before_update")
def _reject_prompt_version_update(_mapper, _connection, _target):
    raise ValueError("production prompt versions are immutable; append a new version")


__all__ = [
    "ProductionPromptVersion",
    "ProductionGenerationIntent",
    "ProductionPromptLineage",
]
