# codejudge-ai

The **AI layer** for CodeJudge: a document-RAG pipeline plus (soon) an ADK
agent that answers questions and helps author problems. It talks to CodeJudge
only through `codejudge-mcp`, and to Gemini directly for embeddings/generation.
See the repo root `CLAUDE.md` for the architecture decisions.

> **New here? Read [OVERVIEW.md](OVERVIEW.md) first** — a plain-language tour of
> what RAG/ADK are, what each folder does, and how to run things. For the exact
> "what do I start and when" steps, see [RUNNING.md](RUNNING.md). This README is
> the terse command reference.

## Layout

This repo root **is** the Python project (run all Python commands from here). The
MCP server is a second Python package, `codejudge_mcp/` (see its own README).

```
CodeJudge-AI/                # repo root = this Python project
├── pyproject.toml
├── codejudge_ai/
│   ├── config.py            # env-driven config (paths, models, chunking)
│   ├── rag/
│   │   ├── extract.py       # md/txt/pdf/docx -> plain text
│   │   ├── chunk.py         # LangChain RecursiveCharacterTextSplitter (thin wrapper)
│   │   ├── embed.py         # Gemini gemini-embedding-001 (doc vs query task types) + LangChain adapter
│   │   ├── store.py         # InMemoryVectorStore (in-memory, saves to store.json) + similarity search
│   │   └── search.py        # search(query) -> top-k hits  (the agent's RAG tool seam)
│   ├── agent/
│   │   ├── tools.py         # search_ingested_docs (RAG tool the model can call)
│   │   └── root_agent.py    # the ADK LlmAgent (RAG-only for now)
│   └── scripts/
│       ├── sync_docs.py     # S1: copy CodeJudge/docs Markdown into ./corpus (READ-ONLY source)
│       ├── ingest.py        # S2: extract -> chunk -> embed -> save the store
│       └── chat.py          # S3: chat with the agent locally (ADK InMemoryRunner)
├── codejudge_mcp/           # MCP server (FastMCP/Streamable HTTP) — separate deployable
│   ├── server.py            # FastMCP instance + tools (get_problem_spec)
│   ├── codejudge_client.py  # async httpx client for CodeJudge
│   └── __main__.py          # python -m codejudge_mcp
└── adk_app/codejudge_assistant/     # launcher so `adk web`/`adk run` find the agent
```

## MCP server

```bash
python -m codejudge_mcp        # serves http://127.0.0.1:8081/mcp (needs CodeJudge on :8080 for live data)
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

## Chat with the assistant

Needs the agent extra (`pip install -e ".[agent]"`) and a built store.

```bash
python -m codejudge_ai.scripts.chat                        # interactive REPL
python -m codejudge_ai.scripts.chat "how are verdicts decided?"   # one-shot
```

The agent chooses per question between two sources:
- `search_ingested_docs` (RAG) for "how does CodeJudge work" — cites doc sources.
- live tools `list_problems` / `get_problem_spec` (over MCP) for questions about
  the actual problems on a running CodeJudge.

For the live tools, also run the MCP server (`python -m codejudge_mcp`) and, for
real data, CodeJudge itself. See [RUNNING.md](RUNNING.md) for the full topology.
It prints each tool call so you can see which source it picked.

## Configuration

All settings live in `config.py` and are overridable via env / `.env`. Key ones:
`GEMINI_API_KEY`, `CODEJUDGE_DOCS_DIR` (READ-ONLY CodeJudge docs source),
`CODEJUDGE_AI_CHUNK_SIZE`/`_OVERLAP`, `CODEJUDGE_AI_TOP_K`, `CODEJUDGE_MCP_URL`.
