# codejudge-ai

The **AI layer** for CodeJudge: a document-RAG pipeline plus (soon) an ADK
agent that answers questions and helps author problems. It talks to CodeJudge
only through `codejudge-mcp`, and to Gemini directly for embeddings/generation.
See the repo root `CLAUDE.md` for the architecture decisions.

> **New here? Read [OVERVIEW.md](OVERVIEW.md) first** — a plain-language tour of
> what RAG/ADK are, what each folder does, and how to run things. This README is
> the terse command reference.

## Layout

```
codejudge_ai/
├── config.py            # env-driven config (paths, models, chunking)
├── rag/
│   ├── extract.py       # md/txt/pdf/docx -> plain text
│   ├── chunk.py         # recursive character splitter (no LangChain dep)
│   ├── embed.py         # Gemini gemini-embedding-001 (doc vs query task types)
│   ├── store.py         # flat-file vector store (chunks.json + vectors.npy) + cosine search
│   └── search.py        # search(query) -> top-k hits  (the agent's RAG tool seam)
└── scripts/
    ├── sync_docs.py     # S1: copy CodeJudge/docs Markdown into ./corpus (READ-ONLY source)
    └── ingest.py        # S2: extract -> chunk -> embed -> save the store
```

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows;  source .venv/bin/activate on POSIX
pip install -e .                  # RAG pipeline
pip install -e ".[agent]"         # + the ADK agent runtime (later steps)
cp .env.example .env              # then put your GEMINI_API_KEY in .env
```

## RAG pipeline

```bash
# S1 - pull CodeJudge's Markdown docs into ./corpus (re-runnable; skips unchanged)
python -m codejudge_ai.scripts.sync_docs

# S2 - build the vector store (needs GEMINI_API_KEY)
python -m codejudge_ai.scripts.ingest
python -m codejudge_ai.scripts.ingest --dry-run   # extract+chunk only, no API calls
```

Add your own PDFs/Word docs by dropping them anywhere under `corpus/` before
ingesting — `.pdf` and `.docx` are extracted alongside Markdown.

## Configuration

All settings live in `config.py` and are overridable via env / `.env`. Key ones:
`GEMINI_API_KEY`, `CODEJUDGE_DOCS_DIR` (READ-ONLY CodeJudge docs source),
`CODEJUDGE_AI_CHUNK_SIZE`/`_OVERLAP`, `CODEJUDGE_AI_TOP_K`, `CODEJUDGE_MCP_URL`.
