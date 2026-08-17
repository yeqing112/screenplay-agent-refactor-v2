"""Book and Chapter models."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from .base import Base


class Book(Base):
    __tablename__ = "books"
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    filename = Column(String(255), nullable=False)
    chapter_count = Column(Integer, default=0)
    total_words = Column(Integer, default=0)
    status = Column(String(50), default="imported")
    created_at = Column(DateTime, default=datetime.utcnow)


class Chapter(Base):
    __tablename__ = "chapters"
    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False)
    seq = Column(Integer, nullable=False)
    title = Column(String(255), default="")
    content = Column(Text, default="")
    word_count = Column(Integer, default=0)
    status = Column(String(50), default="imported")
    summary = Column(Text, default="")
    character_table = Column(Text, default="[]")
    events = Column(Text, default="[]")
    scenes = Column(Text, default="[]")
    foreshadowing = Column(Text, default="[]")
    appearance_fragments = Column(Text, default="{}")
    analyzed_at = Column(DateTime, nullable=True)


class BookBible(Base):
    __tablename__ = "book_bibles"
    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, unique=True, nullable=False)
    content = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
