"""Persisted Director Benchmark runs for reproducible model comparisons."""
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, Text
from .base import Base


class DirectorBenchmarkRun(Base):
    __tablename__ = "director_benchmark_runs"
    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    episode = Column(Integer, nullable=False, index=True)
    sample_label = Column(String, nullable=False, default="")
    model_id = Column(String, nullable=False, default="deterministic")
    report = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.now)
