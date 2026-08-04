"""A small recursive character text splitter.

Same idea as LangChain's RecursiveCharacterTextSplitter, but ~40 lines and no
dependency: try to split on the biggest natural boundary (paragraphs), and only
fall back to finer separators when a piece is still too big. Chunks target
`chunk_size` characters with `chunk_overlap` characters carried between them so a
fact spanning a boundary is not lost.
"""

from __future__ import annotations

# Coarse-to-fine boundaries: paragraph, line, sentence-ish, word, char.
_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


def split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")
    text = text.strip()
    if not text:
        return []
    pieces = _split_recursive(text, _SEPARATORS, chunk_size)
    return _merge_with_overlap(pieces, chunk_size, chunk_overlap)


def _split_recursive(text: str, separators: list[str], chunk_size: int) -> list[str]:
    """Break `text` into atoms no larger than chunk_size where possible."""
    if len(text) <= chunk_size:
        return [text]

    sep, *rest = separators
    if sep == "":
        # Hard character split: nothing finer to try.
        return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]

    out: list[str] = []
    for part in text.split(sep):
        if not part:
            continue
        part = part + sep if sep != "" else part
        if len(part) <= chunk_size:
            out.append(part)
        else:
            out.extend(_split_recursive(part, rest, chunk_size))
    return out


def _merge_with_overlap(pieces: list[str], chunk_size: int, chunk_overlap: int) -> list[str]:
    """Greedily glue atoms into ~chunk_size chunks, carrying a tail of overlap."""
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if current and len(current) + len(piece) > chunk_size:
            chunks.append(current.strip())
            current = current[-chunk_overlap:] if chunk_overlap else ""
        current += piece
    if current.strip():
        chunks.append(current.strip())
    return [c for c in chunks if c]
