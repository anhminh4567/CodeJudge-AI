"""Embeddings via Gemini `gemini-embedding-001`.

Keeps everything on one provider (same API key as generation). We set the
task_type so the model optimizes document vs. query embeddings differently,
which measurably improves retrieval quality for the same text.
"""

from __future__ import annotations

from google import genai
from google.genai import types

from .. import config

# gemini-embedding-001 accepts multiple inputs per call; keep batches modest to
# stay well under request-size limits and to fail in small units.
_BATCH_SIZE = 64


def _client() -> genai.Client:
    if not config.GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Put it in codejudge-ai/.env "
            "(see .env.example) or export it before running."
        )
    return genai.Client(api_key=config.GEMINI_API_KEY)


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed corpus chunks (task_type=RETRIEVAL_DOCUMENT)."""
    return _embed(texts, task_type="RETRIEVAL_DOCUMENT")


def embed_query(text: str) -> list[float]:
    """Embed a single search query (task_type=RETRIEVAL_QUERY)."""
    return _embed([text], task_type="RETRIEVAL_QUERY")[0]


def _embed(texts: list[str], task_type: str) -> list[list[float]]:
    if not texts:
        return []
    client = _client()
    cfg = types.EmbedContentConfig(task_type=task_type)
    vectors: list[list[float]] = []
    for start in range(0, len(texts), _BATCH_SIZE):
        batch = texts[start : start + _BATCH_SIZE]
        resp = client.models.embed_content(
            model=config.EMBED_MODEL,
            contents=batch,
            config=cfg,
        )
        vectors.extend(e.values for e in resp.embeddings)
    return vectors
