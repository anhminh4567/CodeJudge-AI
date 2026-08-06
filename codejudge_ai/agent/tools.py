"""Agent tools. Each is a plain Python function; ADK turns the type hints and
docstring into the tool's schema and description, so the docstring is written
*for the model* — it's what the LLM reads to decide when and how to call it.
"""

from __future__ import annotations

from ..rag import search as rag_search


def search_ingested_docs(query: str) -> dict:
    """Search CodeJudge's ingested documentation for passages relevant to a question.

    Use this whenever the user asks how CodeJudge works — its architecture,
    sandbox, grading pipeline, queue, warm pool, verdicts, deployment, etc.
    Always search before answering such questions; do not answer from memory.

    Args:
        query: A concise natural-language search query describing what to find.

    Returns:
        A dict with a "results" list, each item having "source" (the document the
        passage came from), "text" (the passage), and "score" (0-1 relevance).
        If the store hasn't been built yet, returns an "error" explaining how.
    """
    try:
        hits = rag_search.search(query)
    except FileNotFoundError as exc:
        return {"results": [], "error": str(exc)}
    return {
        "results": [
            {"source": h.chunk.source, "text": h.chunk.text, "score": round(h.score, 3)}
            for h in hits
        ]
    }
