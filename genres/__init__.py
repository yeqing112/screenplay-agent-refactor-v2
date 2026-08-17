"""Genre registry - 管理所有可用的编剧赛道。

现在从 prompts/genres/*.json 配置加载，无需为每个赛道编写独立的 Python 类。
"""
from genres.base import get_genre, list_genres
