"""A flat-file vector store: chunk metadata as JSON + vectors as a .npy matrix.

No vector DB (D6). For a personal-scale doc set, retrieval is just cosine
similarity over a modest matrix — a few lines of numpy — and a flat file is far
less operational overhead than a managed DB for zero accuracy loss. Swapping in
Chroma/Qdrant later means reimplementing this one module behind the same API.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

_CHUNKS_FILE = "chunks.json"
_VECTORS_FILE = "vectors.npy"


@dataclass
class Chunk:
    """One retrievable unit: a slice of a source document plus provenance."""

    id: str          # stable id, e.g. "WARM_POOL.md#3"
    source: str      # source document name/relative path
    chunk_index: int  # position within the source
    text: str


@dataclass
class Hit:
    """A retrieval result: the chunk and its cosine similarity to the query."""

    chunk: Chunk
    score: float


def save(store_dir: Path, chunks: list[Chunk], vectors: list[list[float]]) -> None:
    """Persist chunks + their embeddings. Overwrites any existing store."""
    if len(chunks) != len(vectors):
        raise ValueError(f"chunks ({len(chunks)}) and vectors ({len(vectors)}) length mismatch")
    store_dir.mkdir(parents=True, exist_ok=True)
    (store_dir / _CHUNKS_FILE).write_text(
        json.dumps([asdict(c) for c in chunks], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    matrix = np.array(vectors, dtype=np.float32) if vectors else np.zeros((0, 0), dtype=np.float32)
    np.save(store_dir / _VECTORS_FILE, matrix)


def exists(store_dir: Path) -> bool:
    return (store_dir / _CHUNKS_FILE).exists() and (store_dir / _VECTORS_FILE).exists()


class VectorStore:
    """An in-memory view of the flat-file store, loaded once for querying."""

    def __init__(self, chunks: list[Chunk], matrix: np.ndarray):
        self._chunks = chunks
        # Pre-normalize rows so query-time cosine similarity is a single dot product.
        self._normalized = _normalize_rows(matrix)

    @classmethod
    def load(cls, store_dir: Path) -> "VectorStore":
        if not exists(store_dir):
            raise FileNotFoundError(
                f"no vector store at {store_dir}. Run the ingest script first "
                "(python -m codejudge_ai.scripts.ingest)."
            )
        raw = json.loads((store_dir / _CHUNKS_FILE).read_text(encoding="utf-8"))
        chunks = [Chunk(**c) for c in raw]
        matrix = np.load(store_dir / _VECTORS_FILE)
        return cls(chunks, matrix)

    def __len__(self) -> int:
        return len(self._chunks)

    def search(self, query_vector: list[float], top_k: int) -> list[Hit]:
        """Return the top_k chunks by cosine similarity to query_vector."""
        if not self._chunks:
            return []
        q = _normalize_rows(np.array([query_vector], dtype=np.float32))[0]
        scores = self._normalized @ q  # cosine similarity, both sides unit-norm
        k = min(top_k, len(self._chunks))
        # argpartition for the top-k, then sort just those descending.
        top_idx = np.argpartition(-scores, k - 1)[:k]
        top_idx = top_idx[np.argsort(-scores[top_idx])]
        return [Hit(chunk=self._chunks[i], score=float(scores[i])) for i in top_idx]


def _normalize_rows(matrix: np.ndarray) -> np.ndarray:
    if matrix.size == 0:
        return matrix
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0  # avoid divide-by-zero on any zero vector
    return matrix / norms
