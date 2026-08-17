"""Character portrait models."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from .base import Base


class CharacterProfile(Base):
    __tablename__ = "character_profiles"
    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False)
    name = Column(String(100), nullable=False)
    aliases = Column(Text, default="[]")

    # 基础信息
    gender = Column(String(20), default="")
    age_range = Column(String(50), default="")
    role = Column(String(50), default="")
    identity = Column(String(200), default="")

    # 外貌特征
    face_shape = Column(String(50), default="")
    facial_features = Column(Text, default="")
    body_type = Column(String(100), default="")
    skin_tone = Column(String(50), default="")
    distinguishing_marks = Column(Text, default="")

    # 人物来源
    nationality = Column(String(50), default="中国")
    precise_age = Column(Integer, nullable=True)

    # 穿搭造型
    style_era = Column(String(100), default="")
    signature_outfit = Column(Text, default="")
    accessories = Column(Text, default="")
    hairstyle = Column(Text, default="")

    # 气质与氛围
    temperament = Column(Text, default="")
    vibe = Column(String(100), default="")
    color_palette = Column(Text, default="")

    # 人物内在
    personality = Column(Text, default="")
    speech_style = Column(Text, default="")
    body_language = Column(Text, default="")
    relationships = Column(Text, default="{}")

    # 全量生成提示词（向后兼容）
    visual_prompt_en = Column(Text, default="")
    visual_prompt_zh = Column(Text, default="")

    # 分层提示词 (Phase 3)
    core_prompt_en = Column(Text, default="")
    core_prompt_zh = Column(Text, default="")
    outfit_prompt_en = Column(Text, default="")
    outfit_prompt_zh = Column(Text, default="")
    scene_prompt_en = Column(Text, default="")
    scene_prompt_zh = Column(Text, default="")

    # 元数据
    chapter_range = Column(String(255), default="")
    importance = Column(String(50), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class CharacterStage(Base):
    """人物阶段画像 - 同一角色在不同时期的独立画像。"""
    __tablename__ = "character_stages"
    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False)
    character_name = Column(String(100), nullable=False)

    # 阶段定义
    stage_name = Column(String(100), nullable=False)
    chapter_start = Column(Integer, nullable=False)
    chapter_end = Column(Integer, nullable=False)
    timeline = Column(String(100), default="")

    # 阶段身份
    identity = Column(String(200), default="")
    age_description = Column(String(100), default="")

    # 本阶段外貌
    face_shape = Column(String(50), default="")
    facial_features = Column(Text, default="")
    body_type = Column(String(100), default="")
    skin_tone = Column(String(50), default="")
    distinguishing_marks = Column(Text, default="")
    signature_outfit = Column(Text, default="")
    accessories = Column(Text, default="")
    hair_style = Column(Text, default="")
    makeup_spec = Column(Text, default="")

    # 本阶段气质
    temperament = Column(Text, default="")
    vibe = Column(String(100), default="")
    color_palette = Column(Text, default="")
    personality = Column(Text, default="")
    speech_style = Column(Text, default="")
    body_language = Column(Text, default="")

    # 全量生成提示词（向后兼容）
    visual_prompt_en = Column(Text, default="")
    visual_prompt_zh = Column(Text, default="")

    # 分层提示词 (Phase 3)
    core_prompt_en = Column(Text, default="")
    core_prompt_zh = Column(Text, default="")
    outfit_prompt_en = Column(Text, default="")
    outfit_prompt_zh = Column(Text, default="")
    scene_prompt_en = Column(Text, default="")
    scene_prompt_zh = Column(Text, default="")

    # 元数据
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
