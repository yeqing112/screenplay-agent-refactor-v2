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
