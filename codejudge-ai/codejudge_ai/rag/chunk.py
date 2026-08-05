"""Chunking: split a long document into small, overlapping pieces.

We use LangChain's `RecursiveCharacterTextSplitter` rather than hand-rolling one.
It's the standard, well-tested implementation of "split on the biggest natural
boundary first (paragraph), fall back to finer ones (line, sentence, word) only
when a piece is still too big," with overlap carried between chunks so a fact
spanning a boundary isn't lost. This module is a thin wrapper so the rest of the
code just calls `split_text(...)` and doesn't depend on LangChain directly.
"""

from __future__ import annotations

from langchain_text_splitters import RecursiveCharacterTextSplitter


def split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Split `text` into ~chunk_size-character chunks with chunk_overlap overlap.

    Sizes are measured in characters (a simple, predictable proxy for tokens).
    """
    text = text.strip()
    if not text:
        return []
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
    )
    return [c for c in splitter.split_text(text) if c.strip()]
