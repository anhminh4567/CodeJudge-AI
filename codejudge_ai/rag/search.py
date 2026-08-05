"""Query-time retrieval: the seam the agent calls as `search_ingested_docs`.

The store is loaded lazily and cached, so the first query pays the load cost and
subsequent queries are just an embed call + an in-memory similarity search.
"""

from __future__ import annotations

from functools import lru_cache

from .. import config
from .store import Hit, VectorStore


@lru_cache(maxsize=1)
def _load_store() -> VectorStore:
    return VectorStore.load(config.STORE_DIR)


def search(query: str, top_k: int | None = None) -> list[Hit]:
    """Return the most relevant ingested-doc chunks for `query`."""
    if not query or not query.strip():
        return []
    store = _load_store()
    return store.search(query, top_k or config.TOP_K)
