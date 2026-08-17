"""ChromaDB vector search wrapper with batch embedding rate control."""
import time
import logging
import config
from core import OllamaEmbedding

try:
    import chromadb
except ModuleNotFoundError:
    chromadb = None

logger = logging.getLogger(__name__)

_client = None
_embed_fn = None
_embed_signature = None
_available = None

# Embedding rate limiter: Ollama local, but avoid overwhelming the server
_EMBED_BATCH_SIZE = 32
_EMBED_DELAY = 0.1  # seconds between batches


def _get_client():
    global _client, _available
    if chromadb is None:
        if _available is not False:
            logger.warning("ChromaDB unavailable: missing optional dependency 'chromadb'")
            _available = False
        return None
    if _available is False:
        return None
    if _client is None:
        try:
            _client = chromadb.PersistentClient(path=config.CHROMA_PERSIST_DIR)
            _available = True
        except Exception as e:
            logger.warning("ChromaDB unavailable: %s", e)
            _available = False
            return None
    return _client


def _get_embed_fn():
    global _embed_fn, _embed_signature
    if _embed_fn is None:
        _embed_fn = OllamaEmbedding()
        _embed_signature = (_embed_fn.profile_id, _embed_fn.model, _embed_fn.base_url)
        return _embed_fn
    fresh = OllamaEmbedding()
    signature = (fresh.profile_id, fresh.model, fresh.base_url)
    if signature != _embed_signature:
        _embed_fn = fresh
        _embed_signature = signature
    return _embed_fn


def is_available():
    return _get_client() is not None


def get_collection(name: str):
    client = _get_client()
    if client is None:
        return None
    return client.get_or_create_collection(
        name=name,
        embedding_function=_get_embed_fn(),
        metadata={"hnsw:space": "cosine"},
    )


def add_documents(col_name: str, ids: list[str], documents: list[str],
                  metadatas: list[dict] | None = None, batch_size: int = None):
    """Add documents in controlled batches with rate limiting."""
    col = get_collection(col_name)
    if col is None:
        return
    bs = batch_size or _EMBED_BATCH_SIZE
    total = len(ids)
    for i in range(0, total, bs):
        end = min(i + bs, total)
        try:
            col.add(
                ids=ids[i:end],
                documents=documents[i:end],
                metadatas=metadatas[i:end] if metadatas else None,
            )
            # Delay between batches to avoid overwhelming embedding server
            if end < total:
                time.sleep(_EMBED_DELAY)
        except Exception as e:
            logger.warning("Vector index add failed (batch %d-%d): %s", i, end, e)


def search(col_name: str, query: str, n_results: int = 10,
           where: dict | None = None) -> list[dict]:
    """Vector similarity search. Returns empty list if ChromaDB unavailable."""
    col = get_collection(col_name)
    if col is None:
        return []
    try:
        kwargs = {"query_texts": [query], "n_results": n_results}
        if where:
            kwargs["where"] = where
        results = col.query(**kwargs)
        out = []
        for i in range(len(results["ids"][0])):
            out.append({
                "id": results["ids"][0][i],
                "document": results["documents"][0][i],
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "distance": results["distances"][0][i] if results["distances"] else 0,
            })
        return out
    except Exception as e:
        logger.warning("Vector search failed: %s", e)
        return []


def delete_where(col_name: str, where: dict):
    col = get_collection(col_name)
    if col is None:
        return
    try:
        col.delete(where=where)
    except Exception:
        pass
