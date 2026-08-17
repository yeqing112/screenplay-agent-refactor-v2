"""核心通用工具与向量嵌入封装。"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

import config

logger = logging.getLogger(__name__)


def safe_json_loads(data: str | None, default: Any = None) -> Any:
    """安全解析 JSON，失败时返回默认值。"""
    if not data:
        return default if default is not None else ([] if isinstance(default, type) else default)
    try:
        return json.loads(data)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("JSON parse failed (%s): %s...", exc, str(data)[:100])
        return default if default is not None else ({} if str(data).startswith("{") else [])


def _resolve_embedding_profile() -> dict[str, Any]:
    try:
        from api.model_registry import get_default_profile

        profile = get_default_profile("embedding")
        if profile:
            return profile
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning("Resolve embedding profile failed, fallback to env: %s", exc)

    return {
        "id": "builtin-embedding-env",
        "provider": "ollama",
        "base_url": config.OLLAMA_BASE_URL.rstrip("/"),
        "model_name": config.EMBEDDING_MODEL,
        "default_params": {"dimension": config.EMBEDDING_DIM},
    }


class OllamaEmbedding:
    """兼容 ChromaDB 的 Ollama embedding function。"""

    def __init__(self, model: str | None = None, base_url: str | None = None):
        profile = _resolve_embedding_profile()
        self.profile_id = str(profile.get("id") or "builtin-embedding-env")
        self.provider = str(profile.get("provider") or "ollama")
        self.model = model or str(profile.get("model_name") or config.EMBEDDING_MODEL)
        resolved_base_url = base_url or str(profile.get("base_url") or config.OLLAMA_BASE_URL)
        self.base_url = resolved_base_url.rstrip("/")
        self.dimension = int((profile.get("default_params") or {}).get("dimension") or config.EMBEDDING_DIM)

    def name(self) -> str:
        return f"ollama-{self.model}"

    def embed_query(self, text: str | None = None, input=None) -> list[list[float]]:
        value = input if input is not None else text
        if isinstance(value, str):
            value = [value]
        return self(value)

    def embed_documents(self, texts: list[str] | None = None, input: list[str] | None = None) -> list[list[float]]:
        return self(texts or input or [])

    def __call__(self, input: list[str]) -> list[list[float]]:
        with httpx.Client(timeout=120) as client:
            response = client.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": input},
            )
            response.raise_for_status()
            data = response.json()
            embeddings = data["embeddings"]
            logger.info(
                "Embedding request resolved via profile=%s provider=%s model=%s batch=%s",
                self.profile_id,
                self.provider,
                self.model,
                len(input),
            )
            return embeddings
