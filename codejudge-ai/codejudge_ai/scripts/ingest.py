"""S2 - Ingest the corpus into the flat-file vector store.

Runs the pipeline over every supported file in the corpus:
    extract -> chunk -> embed (Gemini) -> save (chunks.json + vectors.npy)

Usage:
    python -m codejudge_ai.scripts.ingest
    python -m codejudge_ai.scripts.ingest --dry-run   # chunk only, no embedding
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .. import config
from ..rag import chunk as chunker
from ..rag import embed, extract
from ..rag.store import Chunk, save


def collect_chunks(corpus_dir: Path) -> list[Chunk]:
    """Extract and chunk every supported document under corpus_dir."""
    if not corpus_dir.exists():
        raise SystemExit(
            f"Corpus not found at {corpus_dir}. Run the sync script first "
            "(python -m codejudge_ai.scripts.sync_docs) or add documents there."
        )

    chunks: list[Chunk] = []
    files = [p for p in sorted(corpus_dir.rglob("*")) if p.is_file() and extract.is_supported(p)]
    if not files:
        raise SystemExit(f"No supported documents found under {corpus_dir}.")

    for path in files:
        source = str(path.relative_to(corpus_dir)).replace("\\", "/")
        try:
            text = extract.extract_text(path)
        except extract.UnsupportedDocument as exc:
            print(f"  ! skipping {source}: {exc}")
            continue
        pieces = chunker.split_text(text, config.CHUNK_SIZE, config.CHUNK_OVERLAP)
        for i, piece in enumerate(pieces):
            chunks.append(Chunk(id=f"{source}#{i}", source=source, chunk_index=i, text=piece))
        print(f"  - {source}: {len(pieces)} chunk(s)")
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest the corpus into the vector store.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="extract + chunk only; skip embedding and writing the store",
    )
    args = parser.parse_args()

    print(f"Corpus : {config.CORPUS_DIR}")
    chunks = collect_chunks(config.CORPUS_DIR)
    print(f"Total  : {len(chunks)} chunk(s) from the corpus")

    if args.dry_run:
        print("Dry run - skipping embedding and store write.")
        return

    print(f"Embedding with {config.EMBED_MODEL} ...")
    vectors = embed.embed_documents([c.text for c in chunks])
    save(config.STORE_DIR, chunks, vectors)
    print(f"Saved store to {config.STORE_DIR} ({len(chunks)} vectors).")


if __name__ == "__main__":
    main()
