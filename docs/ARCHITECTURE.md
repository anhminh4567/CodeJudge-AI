# Architecture

CodeJudge-AI is the **AI layer** on top of the existing `CodeJudge` online judge.
This doc is the map: the decisions, the pieces, and how they talk. The original
design brief is [codejudge-ai-final-plan.md](codejudge-ai-final-plan.md); the
build roadmap is [DEVELOPMENT_PHASES.md](DEVELOPMENT_PHASES.md); a gentle tour is
[OVERVIEW.md](OVERVIEW.md).

## The three capabilities

1. **Answer visitor questions** — RAG over ingested docs + live problem lookups.
2. **Author problems / generate & validate test cases** — a mostly-deterministic
   pipeline with an iterative sub-loop (Phase 2).
3. **Grade a submission with AI-generated adversarial cases** — a real agent loop
   grounded by actual sandboxed execution in CodeJudge (Phase 3).

## Components

```
CodeJudge-AI/  (this repo — single-language Python)
├── codejudge_ai/     the AI: RAG pipeline + ADK agent
│   ├── rag/          extract → chunk → embed → in-memory vector store → search
│   ├── agent/        LlmAgent, tools, guardrail, observability
│   └── scripts/      sync_docs, ingest, chat
├── codejudge_mcp/    MCP server (FastMCP/Streamable HTTP) fronting CodeJudge
├── adk_app/          launcher so `adk web`/`adk run` discover the agent
└── server.py         example custom FastAPI server

CodeJudge/   (sibling repo, READ-ONLY, owned by another agent — the HTTP endpoint)
```

## How it talks

```
        codejudge_ai (ADK LlmAgent)
          |                      |
   search_ingested_docs     MCP tools (Streamable HTTP)
          |                      |
    in-memory vector       codejudge_mcp  --HTTP-->  CodeJudge API
    store (store.json)          |
          |               (list_problems, get_problem_spec, …)
     Gemini embeddings
   + Gemini generation (the agent's model)
```

The agent chooses per question: RAG for "how does CodeJudge work", live MCP tools
for "what problems exist / show me problem X". Two genuinely different sources,
one model deciding between them — that's the PoC.

## Locked decisions

- **D1 — Microservices.** `codejudge_mcp` and `codejudge_ai` are independent
  deployables. They never share a module; they talk over HTTP/MCP only.
- **D2 (REVISED) — Single-language Python.** Originally polyglot (Go MCP + Python
  AI). The MCP layer turned out thin enough that a second language bought nothing,
  and the official Python `mcp` SDK (FastMCP) covers the server, so `codejudge_mcp`
  is Python too. One language, one venv, one `pyproject.toml`. (Still separate
  deployables per D1.) Pin `mcp<2` — ADK's MCP client is incompatible with 2.x.
- **D3 — Workflow where predictable, agent where judgment is needed.**
- **D4 — MCP over Streamable HTTP** at every tool boundary.
- **D5 — The LLM never executes code.** All execution goes through CodeJudge's
  judge/sandbox via a `run_submission` tool (Phase 3). Non-negotiable.
- **D6 — Light RAG, no vector DB service.** In-memory vector store persisted to a
  single JSON file; a real vector DB is a later upgrade behind the same
  `VectorStore` API.

## Cross-cutting seams

- **Guardrail** — screens input before the model runs. See [GUARDRAIL.md](GUARDRAIL.md).
- **Observability** — callbacks, plugins, OpenTelemetry. See [OBSERVABILITY.md](OBSERVABILITY.md).

## CodeJudge API surface (observed, READ-ONLY)

Gin, base path `/`, envelopes: object `{data:…}`, list adds paging, error
`{error:{code,message}}`.

- `GET /healthz`
- `POST /submissions` · `GET /submissions` · `GET /submissions/:id`
- `GET /problems` · `POST /problems` · `GET /problems/:id`
- `POST /problems/:id/testcases` · `GET /languages`

**Open boundary:** the plan assumes CodeJudge gains a service-token-gated admin API
(ad-hoc `run_submission`, `add_problem`, `commit_test_case`). Today only the public
read/write endpoints above exist. The MCP wraps what exists; anything needing new
endpoints is a dependency on the other agent — flag it, don't assume it.
