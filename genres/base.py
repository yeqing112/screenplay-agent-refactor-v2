"""Base genre class. 现在从 JSON 配置文件加载，不再需要每个 genre 一个 Python 子类。"""
import json
import logging
from pathlib import Path
from functools import lru_cache

from core import safe_json_loads

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts" / "genres"


class Genre:
    """Genre 配置类，从 JSON + 模板文件加载。"""

    def __init__(self, config: dict):
        self._config = config
        self._adapt_template = None
        self._script_template = None

    @property
    def name(self) -> str:
        return self._config.get("name", "unknown")

    @property
    def description(self) -> str:
        return self._config.get("description", "")

    @property
    def icon(self) -> str:
        return self._config.get("icon", "")

    @property
    def episode_duration(self) -> str:
        return self._config.get("episode_duration", "")

    @property
    def episode_count(self) -> str:
        return self._config.get("episode_count", "")

    @property
    def target_audience(self) -> str:
        return self._config.get("target_audience", "")

    @property
    def pacing(self) -> str:
        return self._config.get("pacing", "")

    @property
    def persona(self) -> str:
        return self._config.get("persona", "")

    @property
    def adapt_persona(self) -> str:
        return self._config.get("adapt_persona", self.persona)

    @property
    def system_prompt(self) -> str:
        return self._config.get("system_prompt", "")

    def get_adapt_prompt(self, bible: str, portraits: str = "") -> str:
        """加载 adapt 模板并注入变量。"""
        if self._adapt_template is None:
            path = PROMPTS_DIR / f"{self.name}_adapt.txt"
            if path.exists():
                try:
                    self._adapt_template = path.read_text(encoding="utf-8")
                except OSError as e:
                    raise IOError(f"Failed to read {path}: {e}") from e
            else:
                raise FileNotFoundError(f"Adapt template not found: {path}")

        try:
            return self._adapt_template.format(
                persona=self.adapt_persona,
                genre_name=self.description,
                bible=bible,
                portraits=portraits or "(暂无画像)",
            )
        except KeyError as e:
            logger.warning("Template variable missing in adapt prompt: %s", e)
            return self._adapt_template

    def get_script_prompt(self, bible: str, episode_outline: str,
                          source_excerpts: str, episode: int,
                          episode_title: str, portraits: str = "",
                          adaptation_settings: str = "") -> str:
        """加载 script 模板并注入变量。"""
        if self._script_template is None:
            path = PROMPTS_DIR / f"{self.name}_script.txt"
            if path.exists():
                try:
                    self._script_template = path.read_text(encoding="utf-8")
                except OSError as e:
                    raise IOError(f"Failed to read {path}: {e}") from e
            else:
                raise FileNotFoundError(f"Script template not found: {path}")

        try:
            return self._script_template.format(
                persona=self.persona,
                genre_name=self.description,
                bible=bible,
                portraits=portraits or "(暂无画像)",
                episode_outline=episode_outline,
                source_excerpts=source_excerpts,
                episode=episode,
                episode_title=episode_title,
                adaptation_settings=adaptation_settings or "(无特殊改编设定)",
            )
        except KeyError as e:
            logger.warning("Template variable missing in script prompt: %s", e)
            return self._script_template

    def to_dict(self) -> dict:
        """返回用于 CLI 显示的字典。"""
        return {
            "key": self.name,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "duration": self.episode_duration,
            "count": self.episode_count,
            "audience": self.target_audience,
        }


@lru_cache(maxsize=1)
def _load_genre_registry() -> dict[str, Genre]:
    """加载 prompts/genres/ 目录下所有 JSON 配置。"""
    registry = {}
    for f in sorted(PROMPTS_DIR.glob("*.json")):
        config = safe_json_loads(f.read_text(encoding="utf-8"), {})
        if not isinstance(config, dict):
            logger.warning("Invalid genre config (not dict): %s", f.name)
            continue
        if "name" not in config:
            logger.warning("Genre config missing 'name': %s", f.name)
            continue
        g = Genre(config)
        registry[g.name] = g
    return registry


def get_genre(name: str) -> Genre:
    """获取指定赛道的 genre 对象。"""
    registry = _load_genre_registry()
    if name not in registry:
        available = ", ".join(registry.keys())
        raise ValueError(f"Unknown genre: {name}. Available: {available}")
    return registry[name]


def list_genres() -> list[dict]:
    """列出所有可用赛道。"""
    return [g.to_dict() for g in _load_genre_registry().values()]
