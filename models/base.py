"""Base model config — engine, session, declarative base."""
import logging
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
import config

logger = logging.getLogger(__name__)

Base = declarative_base()
engine = create_engine(config.DATABASE_URL, echo=False)
Session = sessionmaker(bind=engine)


def init_db():
    """初始化数据库。优先使用 Alembic migration，fallback 到 create_all。"""
    try:
        from alembic.config import Config
        from alembic import command
        alembic_cfg = Config(str(Path(__file__).parent.parent / "alembic.ini"))
        command.upgrade(alembic_cfg, "head")
    except Exception as e:
        logger.warning("Alembic fallback to create_all: %s", e)
        Base.metadata.create_all(engine)
    return engine


def get_kv(key: str, default: str = "") -> str:
    """Get a key-value store entry. Returns default if not found."""
    with Session() as s:
        from .kv import KV
        row = s.get(KV, key)
        return row.value if row else default


def set_kv(key: str, value: str) -> None:
    """Set a key-value store entry."""
    with Session() as s:
        from .kv import KV
        row = s.get(KV, key)
        if row:
            row.value = str(value)
        else:
            s.add(KV(key=key, value=str(value)))
        s.commit()
