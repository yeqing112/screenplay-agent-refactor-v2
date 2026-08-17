"""Models package — exports all models and utilities.

Usage:
    from models import Book, Chapter, Session, init_db, get_kv
"""
from .base import Base, engine, Session, init_db, get_kv, set_kv
from .book import Book, Chapter, BookBible
from .character import CharacterProfile, CharacterStage
from .script import EpisodeOutline, Script, QAResult
from .kv import KV
from .visual import VisualEraSpec, VisualProp, VisualLocation, VisualMakeup, VisualReferenceAsset
from .bridge import SceneCharacter, SceneProp
from .storyboard import StoryboardShot
from .prompt import StoryboardPromptVersion
from .acceptance import StoryboardAcceptanceRecord
from .export_record import ProductionExportRecord
from .qa_workbench import QAIssue, ScriptVersion

__all__ = [
    "Base", "engine", "Session",
    "init_db", "get_kv", "set_kv",
    "Book", "Chapter", "BookBible",
    "CharacterProfile", "CharacterStage",
    "EpisodeOutline", "Script", "QAResult",
    "KV",
    "VisualEraSpec", "VisualProp", "VisualLocation", "VisualMakeup", "VisualReferenceAsset",
    "SceneCharacter", "SceneProp",
    "StoryboardShot", "StoryboardPromptVersion", "StoryboardAcceptanceRecord", "ProductionExportRecord",
    "QAIssue", "ScriptVersion",
]
