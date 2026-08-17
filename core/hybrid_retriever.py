"""Hybrid retriever: combines vector search + keyword search."""
import logging

from core import vector_search as vs
from core import keyword_search as ks

logger = logging.getLogger(__name__)


class HybridRetriever:
    """Combine vector similarity and keyword search with score fusion."""

    def __init__(self, book_id: int):
        self.book_id = book_id

    def search(self, query: str, n_results: int = 10,
               vector_weight: float = 0.7, keyword_weight: float = 0.3,
               where: dict | None = None) -> list[dict]:
        """Hybrid search with RRF-like score fusion."""
        if not query or not query.strip():
            logger.warning("Empty query passed to hybrid search")
            return []

        # Vector search
        try:
            v_results = vs.search("chapters", query, n_results=n_results * 2, where=where)
        except Exception as e:
            logger.error("Vector search failed for query %r: %s", query, e)
            v_results = []

        # Keyword search
        try:
            ks.init_fts()
        except Exception as e:
            logger.error("FTS init failed: %s", e)
        try:
            k_results = ks.keyword_search(query, book_id=self.book_id, limit=n_results * 2)
        except Exception as e:
            logger.error("Keyword search failed for query %r: %s", query, e)
            k_results = []

        # Merge by chapter_id with weighted scoring
        scores = {}
        for i, r in enumerate(v_results):
            cid = r.get("id")
            if cid is None:
                continue
            score = vector_weight * (1.0 / (1.0 + i))
            scores[cid] = {
                "chapter_id": cid, "score": score, "source": "vector",
                "document": r.get("document", ""),
                "metadata": r.get("metadata", {}),
            }

        for i, r in enumerate(k_results):
            cid = r.get("chapter_id")
            if cid is None:
                continue
            score = keyword_weight * (1.0 / (1.0 + i))
            if cid in scores:
                scores[cid]["score"] += score
                scores[cid]["source"] = "hybrid"
            else:
                scores[cid] = {
                    "chapter_id": cid, "score": score, "source": "keyword",
                    "document": r.get("snippet", ""),
                    "metadata": {},
                }

        # Sort by combined score
        results = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
        return results[:n_results]

    def search_character(self, name: str, n: int = 5) -> list[dict]:
        """Search for a specific character across chapters."""
        where = {"characters": {"$contains": name}} if name else None
        return self.search(f"角色 {name} 人物", n_results=n, where=where)

    def search_event(self, keyword: str, n: int = 5) -> list[dict]:
        """Search for events matching a keyword."""
        return self.search(keyword, n_results=n)

    def search_scene(self, location: str, n: int = 5) -> list[dict]:
        """Search for scenes at a specific location."""
        return self.search(f"场景 {location}", n_results=n)
