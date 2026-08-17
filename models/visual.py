"""Visual asset models."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from .base import Base


ASSET_STATUS_DRAFT = "draft"
ASSET_STATUS_REF_READY = "ref_ready"
ASSET_STATUS_LOCKED = "locked"


class VisualEraSpec(Base):
    __tablename__ = "visual_era_specs"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, unique=True)
    timeline_start = Column(String, default="")
    timeline_end = Column(String, default="")
    time_periods = Column(Text, default="[]")
    clothing_spec = Column(Text, default="")
    color_palette = Column(Text, default="")
    architecture_spec = Column(Text, default="")
    environment_spec = Column(Text, default="")
    prop_spec = Column(Text, default="")
    color_curve = Column(Text, default="")
    genre_adapt_rules = Column(Text, default="")
    raw_periods = Column(Text, default="[]")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class VisualProp(Base):
    __tablename__ = "visual_props"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False)
    book_title = Column(String, default="")
    name = Column(String, nullable=False)
    category = Column(String, default="")
    description = Column(Text, default="")
    associated_characters = Column(Text, default="")
    episodes = Column(Text, default="[]")
    time_period = Column(String, default="")
    visual_prompt_en = Column(Text, default="")
    visual_prompt_zh = Column(Text, default="")
    core_prompt_en = Column(Text, default="")
    core_prompt_zh = Column(Text, default="")
    style_ref_en = Column(Text, default="")
    style_ref_zh = Column(Text, default="")
    importance = Column(String, default="medium")
    notes = Column(Text, default="")
    shot_ids = Column(Text, default="[]")
    jimeng_ref_name = Column(String, default="")
    negative_prompt = Column(Text, default="")
    asset_status = Column(String, default=ASSET_STATUS_DRAFT)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class VisualLocation(Base):
    __tablename__ = "visual_locations"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False)
    book_title = Column(String, default="")
    name = Column(String, nullable=False)
    category = Column(String, default="")
    style = Column(String, default="")
    description = Column(Text, default="")
    color_palette = Column(Text, default="")
    lighting_mood = Column(Text, default="")
    key_props = Column(Text, default="[]")
    episodes = Column(Text, default="[]")
    time_period = Column(String, default="")
    visual_prompt_en = Column(Text, default="")
    visual_prompt_zh = Column(Text, default="")
    core_prompt_en = Column(Text, default="")
    core_prompt_zh = Column(Text, default="")
    scene_mood_en = Column(Text, default="")
    scene_mood_zh = Column(Text, default="")
    importance = Column(String, default="medium")
    notes = Column(Text, default="")
    shot_ids = Column(Text, default="[]")
    jimeng_ref_name = Column(String, default="")
    negative_prompt = Column(Text, default="")
    asset_status = Column(String, default=ASSET_STATUS_DRAFT)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class VisualMakeup(Base):
    __tablename__ = "visual_makeups"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False)
    book_title = Column(String, default="")
    episode = Column(Integer, nullable=False)
    character_name = Column(String, nullable=False)
    stage_name = Column(String, default="")
    refined_outfit = Column(Text, default="")
    refined_accessories = Column(Text, default="")
    makeup_spec = Column(Text, default="")
    hair_style = Column(Text, default="")
    expression_mood = Column(Text, default="")
    visual_prompt_en = Column(Text, default="")
    visual_prompt_zh = Column(Text, default="")
    core_prompt_en = Column(Text, default="")
    core_prompt_zh = Column(Text, default="")
    outfit_prompt_en = Column(Text, default="")
    outfit_prompt_zh = Column(Text, default="")
    scene_prompt_en = Column(Text, default="")
    scene_prompt_zh = Column(Text, default="")
    consistency_notes = Column(Text, default="")
    meta_info = Column(Text, default="{}")
    shot_ids = Column(Text, default="[]")
    jimeng_ref_name = Column(String, default="")
    negative_prompt = Column(Text, default="")
    asset_status = Column(String, default=ASSET_STATUS_DRAFT)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class VisualReferenceAsset(Base):
    __tablename__ = "visual_reference_assets"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False)
    episode = Column(Integer, nullable=True)
    asset_type = Column(String, nullable=False)
    asset_id = Column(String, nullable=False)
    asset_name = Column(String, default="")
    image_url = Column(Text, default="")
    local_path = Column(Text, default="")
    reference_token = Column(String, default="")
    status = Column(String, default="candidate")
    prompt = Column(Text, default="")
    model = Column(String, default="")
    notes = Column(Text, default="")
    meta_info = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)
