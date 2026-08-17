"""Key-value store model."""
from sqlalchemy import Column, String, Text
from .base import Base


class KV(Base):
    __tablename__ = "kv"
    key = Column(String, primary_key=True)
    value = Column(Text, default="")
