"""Configuration module."""
import os
import re
import logging
from pathlib import Path
try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover
    def load_dotenv():
        return False

logger = logging.getLogger(__name__)

load_dotenv()

BASE_DIR = Path(__file__).parent
WORK_DIR = BASE_DIR / "work"
OUTPUT_DIR = BASE_DIR / "outputs"

# Directories (internal data)
BOOKS_DIR = WORK_DIR / "books"
INDEXES_DIR = WORK_DIR / "indexes"
DB_DIR = WORK_DIR / "db"

# ── LLM ──
def _load_str(key: str, default: str) -> str:
    val = os.getenv(key, default)
    if val == "sk-placeholder" or val == "***":
        logger.warning("API key %s is not set (using placeholder). Set environment variable.", key)
    return val

def _load_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        logger.warning("Invalid %s, using default: %s", key, default)
        return default

def _load_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        logger.warning("Invalid %s, using default: %s", key, default)
        return default

OPENAI_API_KEY = _load_str("OPENAI_API_KEY", "sk-placeholder")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://10.126.126.2:11434/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen3-max")
LLM_TEMPERATURE = _load_float("LLM_TEMPERATURE", 0.3)
LLM_MAX_TOKENS = _load_int("LLM_MAX_TOKENS", 8192)

# Embedding (Ollama)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
EMBEDDING_DIM = _load_int("EMBEDDING_DIM", 768)

# ChromaDB
CHROMA_PERSIST_DIR = os.getenv(
    "CHROMA_PERSIST_DIR",
    str(BASE_DIR / "work" / "indexes" / "chroma"),
)

# SQLite
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_DIR}/screenplay.db?timeout=30")


def _ensure_dirs():
    """确保内部目录存在（延迟加载，不阻塞 import）。"""
    for d in [BOOKS_DIR, INDEXES_DIR, DB_DIR]:
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error("Failed to create directory %s: %s", d, e)


_ensure_dirs()


# ── Truncation Limits ──
# 控制文本截断边界，配置化替代散落的魔术数字
CHAPTER_MAX_CHARS = 15000        # 单章最大字符数
BIBLE_EXCERPT_CHARS = 6000       # Bible 正文截断
SCRIPT_EXCERPT_CHARS = 8000      # 剧本正文截断
PORTRAIT_EXCERPT_CHARS = 3000    # 角色画像截断
CHAR_INFO_CHARS = 3000           # 角色信息截断
TIMELINE_EXCERPT_CHARS = 3000    # 时间线截断
RULES_EXCERPT_CHARS = 2000       # 规则文件截断
SCENE_EXCERPT_CHARS = 4000       # 场景描述截断
OUTLINE_EXCERPT_CHARS = 8000     # 分集大纲截断
ADAPTATION_EXCERPT_CHARS = 8000  # 改编方案截断
PROPS_LOCS_CHARS = 2000          # 道具/地点截断
ESTIMATED_TOKENS_DEFAULT = 4000  # 默认预估 token 数
ESTIMATED_TOKENS_SMALL = 2000    # 小 prompt 预估 token
ESTIMATED_TOKENS_LARGE = 12000   # 大 prompt 预估 token
ESTIMATED_TOKENS_CHAPTER = 6000  # 单章分析预估 token


def sanitize_filename(name: str) -> str:
    """清理文件名字符，保留中文、字母、数字和基本符号。"""
    if not isinstance(name, str):
        name = str(name)
    # 移除路径分隔符和危险字符
    return re.sub(r'[<>:"/\\|?*\n\r]', '', name).strip()


def output_path(book_title: str, *parts: str) -> Path:
    """返回 outputs/{book_title}/{parts} 路径，自动创建目录。"""
    safe_title = sanitize_filename(book_title)
    if not safe_title:
        safe_title = "untitled"
    path = OUTPUT_DIR / safe_title / Path(*parts)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error("Failed to create output directory %s: %s", path.parent, e)
    return path
