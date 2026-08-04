"""S1 - Sync CodeJudge's Markdown docs into this project's corpus.

CodeJudge is READ-ONLY to this project (another agent owns it). This script only
*reads* from CodeJudge/docs and copies Markdown into codejudge-ai/corpus/ so the
RAG pipeline has something to ingest. Re-runnable: run it again whenever new docs
land upstream and it copies just the new/changed ones.

Usage:
    python -m codejudge_ai.scripts.sync_docs
    python -m codejudge_ai.scripts.sync_docs --clean   # wipe corpus copies first
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from .. import config

_MARKDOWN_SUFFIXES = {".md", ".markdown"}


def sync(src_dir: Path, corpus_dir: Path, clean: bool = False) -> list[Path]:
    if not src_dir.exists():
        raise SystemExit(
            f"CodeJudge docs not found at {src_dir}. Set CODEJUDGE_DOCS_DIR if the "
            "CodeJudge repo lives elsewhere."
        )

    dest = corpus_dir / "codejudge-docs"
    if clean and dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    copied: list[Path] = []
    # rglob to pick up nested docs (e.g. docs/queue/*.md); flatten with a path
    # hint in the filename so provenance survives and names never collide.
    for src in sorted(src_dir.rglob("*")):
        if src.suffix.lower() not in _MARKDOWN_SUFFIXES or not src.is_file():
            continue
        rel = src.relative_to(src_dir)
        flat_name = "__".join(rel.parts)  # queue/FOO.md -> queue__FOO.md
        target = dest / flat_name
        if _needs_copy(src, target):
            shutil.copy2(src, target)
            copied.append(target)
    return copied


def _needs_copy(src: Path, target: Path) -> bool:
    """Copy when the target is missing or older than the source."""
    if not target.exists():
        return True
    return src.stat().st_mtime > target.stat().st_mtime


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync CodeJudge Markdown docs into the corpus.")
    parser.add_argument("--clean", action="store_true", help="remove existing copies before syncing")
    args = parser.parse_args()

    copied = sync(config.CODEJUDGE_DOCS_DIR, config.CORPUS_DIR, clean=args.clean)
    print(f"Source : {config.CODEJUDGE_DOCS_DIR}")
    print(f"Corpus : {config.CORPUS_DIR / 'codejudge-docs'}")
    if copied:
        print(f"Copied {len(copied)} file(s):")
        for path in copied:
            print(f"  + {path.name}")
    else:
        print("Nothing to copy - corpus already up to date.")


if __name__ == "__main__":
    main()
