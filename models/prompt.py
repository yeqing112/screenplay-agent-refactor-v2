"""Prompt compilation version models."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from .base import Base


class StoryboardPromptVersion(Base):
    __tablename__ = "storyboard_prompt_versions"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False)
    episode = Column(Integer, nullable=False)
    shot_id = Column(Integer, nullable=False)
    version = Column(Integer, nullable=False)
    compile_reason = Column(String, default="manual")
    prompt_static = Column(Text, default="")
    prompt_motion = Column(Text, default="")
    negative_prompt = Column(Text, default="")
    meta_info = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.now)


class PromptIRVersion(Base):
    """Versioned structured PromptIR artifact; text serialization is derived."""

    __tablename__ = "prompt_ir_versions"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    episode = Column(Integer, nullable=False, index=True)
    scene_id = Column(String, nullable=False, index=True)
    storyboard_shot_id = Column(Integer, nullable=False, index=True)
    materialization_set_id = Column(Integer, nullable=False, index=True)
    plan_shot_id = Column(String, nullable=False, index=True)
    schema_version = Column(String, nullable=False)
    payload_json = Column(Text, nullable=False, default="{}")
    payload_hash = Column(String, nullable=False, index=True)
    compiler_version = Column(String, nullable=False)
    compiler_policy_version = Column(String, nullable=False)
    retention_policy_version = Column(String, nullable=False)
    authority_envelope_json = Column(Text, nullable=False, default="{}")
    qualification_state = Column(String, nullable=False, default="STRUCTURALLY_VALID")
    asset_reference_state = Column(String, nullable=False, default="ASSET_REFERENCE_PENDING")
    model_generation_ready = Column(String, nullable=False, default="false")
    stale_status = Column(String, nullable=False, default="FRESH")
    stale_reasons = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class PromptIRAuthority(Base):
    """Immutable authority envelope for a PromptIR version."""

    __tablename__ = "prompt_ir_authorities"

    id = Column(Integer, primary_key=True)
    prompt_ir_version_id = Column(Integer, nullable=False, unique=True, index=True)
    book_id = Column(Integer, nullable=False, index=True)
    episode = Column(Integer, nullable=False, index=True)
    storyboard_shot_id = Column(Integer, nullable=False, index=True)
    envelope_fingerprint = Column(String, nullable=False, unique=True)
    envelope_json = Column(Text, nullable=False, default="{}")
    qualification_state = Column(String, nullable=False, default="PROMPT_IR_QUALIFIED")
    stale_status = Column(String, nullable=False, default="FRESH")
    stale_reasons = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class PromptIRPointer(Base):
    """StoryboardShot -> current qualified PromptIR version."""

    __tablename__ = "prompt_ir_pointers"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    episode = Column(Integer, nullable=False, index=True)
    storyboard_shot_id = Column(Integer, nullable=False, unique=True, index=True)
    prompt_ir_version_id = Column(Integer, nullable=False)
    payload_hash = Column(String, nullable=False)
    qualification_state = Column(String, nullable=False, default="PROMPT_IR_QUALIFIED")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)
