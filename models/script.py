"""Script and QA models."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from .base import Base


class EpisodeOutline(Base):
    __tablename__ = "episode_outlines"
    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False)
    genre = Column(String(50), default="short_drama", comment="风格标识")
    episode = Column(Integer, nullable=False, default=0)
    title = Column(String, default="")
    core_event = Column(Text, default="")
    opening_hook = Column(Text, default="")
    core_conflict = Column(Text, default="")
    climax = Column(Text, default="")
    ending_hook = Column(Text, default="")
    characters = Column(Text, default="")
    scenes = Column(Text, default="")
    is_fixed = Column(Integer, default=0, comment="是否为改编方案锁定的固定纲次 (1=fixed, 0=自由生成)")
    raw_content = Column(Text, default="", comment="完整大纲原文，兼容旧数据")
    created_at = Column(DateTime, default=datetime.now)


class Script(Base):
    __tablename__ = "scripts"
    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False)
    genre = Column(String(50), default="short_drama", comment="风格标识")
    episode = Column(Integer, nullable=False)
    content = Column(Text, default="")
    word_count = Column(Integer, default=0)
    status = Column(String, default="draft")
    execution_status = Column(String, default="succeeded", nullable=False)
    quality_status = Column(String, default="draft", nullable=False)
    production_status = Column(String, default="blocked", nullable=False)
    workflow_profile = Column(String, default="creative_draft", nullable=False)
    created_at = Column(DateTime, default=datetime.now)


class QAResult(Base):
    __tablename__ = "qa_results"
    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False)
    episode = Column(Integer, nullable=False)
    result = Column(Text, default="")
    error_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)
