"""The vector store: LangChain's `InMemoryVectorStore` with save/load.

In-memory (no service to run) but library-backed rather than hand-rolled — it
holds the vectors in RAM, does brute-force cosine similarity, and persists to a
single JSON file. Perfect for a personal-scale doc set (D6: no vector DB). If we
ever outgrow it, swapping in Chroma/Qdrant means changing only this file, because
everything above talks to the small `VectorStore`/`Chunk`/`Hit` API here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from langchain_core.vectorstores import InMemoryVectorStore

from .embed import GeminiEmbeddings

_STORE_FILE = "store.json"


@dataclass
class Chunk:
    """One retrievable unit: a slice of a source document plus provenance."""

    id: str           # stable id, e.g. "codejudge-docs/WARM_POOL.md#3"
    source: str       # source document (relative path within the corpus)
    chunk_index: int  # position within the source
    text: str


@dataclass
class Hit:
    """A retrieval result: the chunk and its cosine similarity to the query."""

    chunk: Chunk
    score: float


class VectorStore:
    """Thin wrapper over InMemoryVectorStore that speaks in Chunks and Hits."""

    def __init__(self, inner: InMemoryVectorStore):
        self._inner = inner

    @classmethod
    def build(cls, chunks: list[Chunk]) -> "VectorStore":
        """Embed and index chunks. The embedding happens inside add_texts via
        GeminiEmbeddings, so this is the step that calls Gemini."""
        inner = InMemoryVectorStore(GeminiEmbeddings())
        inner.add_texts(
            texts=[c.text for c in chunks],
            metadatas=[{"id": c.id, "source": c.source, "chunk_index": c.chunk_index} for c in chunks],
            ids=[c.id for c in chunks],
        )
        return cls(inner)

    def save(self, store_dir: Path) -> None:
        store_dir.mkdir(parents=True, exist_ok=True)
        self._inner.dump(str(store_dir / _STORE_FILE))

    @classmethod
    def load(cls, store_dir: Path) -> "VectorStore":
        path = store_dir / _STORE_FILE
        if not path.exists():
            raise FileNotFoundError(
                f"no vector store at {path}. Run the ingest script first "
                "(python -m codejudge_ai.scripts.ingest)."
            )
        inner = InMemoryVectorStore.load(str(path), GeminiEmbeddings())
        return cls(inner)

    def __len__(self) -> int:
        return len(self._inner.store)

    def search(self, query: str, top_k: int) -> list[Hit]:
        """Return the top_k chunks by cosine similarity to `query`. The query is
        embedded internally (RETRIEVAL_QUERY task type via GeminiEmbeddings)."""
        results = self._inner.similarity_search_with_score(query, k=top_k)
        hits: list[Hit] = []
        for doc, score in results:
            meta = doc.metadata or {}
            hits.append(
                Hit(
                    chunk=Chunk(
                        id=meta.get("id", doc.id or ""),
                        source=meta.get("source", ""),
                        chunk_index=meta.get("chunk_index", -1),
                        text=doc.page_content,
                    ),
                    score=float(score),
                )
            )
        return hits
