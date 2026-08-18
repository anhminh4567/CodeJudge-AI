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
├── codejudge_ai/     the AI: RAG pipeline + ADK agent(s)
│   ├── rag/          extract → chunk → embed → in-memory vector store → search
│   ├── agent/        root_agent (Q&A) + problem_author (authoring sub-agent) +
│   │                 adversarial_grader (grading sub-agent), tools, guardrail,
│   │                 observability
│   └── scripts/      sync_docs, ingest, chat
├── codejudge_mcp/    MCP server (FastMCP/Streamable HTTP) fronting CodeJudge
├── adk_app/          launcher so `adk web`/`adk run` discover the agent
└── server.py         example custom FastAPI server

CodeJudge/   (sibling repo, READ-ONLY, owned by another agent — the HTTP endpoint)
```

## How it talks

```
                    root_agent (Q&A)
              |                        |
     search_ingested_docs      MCP tools (read-only)   ── transfer_to_agent ──▶ problem_author (authoring)
              |                        |                     │                        |
   in-memory vector store       codejudge_mcp  ──HTTP──▶  CodeJudge API      MCP tools (read + chat-approved writes)
   (store.json)                       |                     │                        |
              |                (list_problems,               └── transfer_to_agent ──▶ adversarial_grader (grading)
     Gemini embeddings          get_problem_spec, …)                                       |
   + Gemini generation (all agents' model)                                        MCP tools (read-only: get_problem_spec,
                                                                                    get_submission, run_submission)
```

`root_agent` chooses per question: RAG for "how does CodeJudge work", live MCP
tools for "what problems exist / show me problem X" — that's the Phase 1 PoC.
For authoring requests it transfers to `problem_author`, which drives the
draft → cases → reference → validate → publish workflow, asking for an
explicit "yes" in chat before every step that mutates anything. See
[PROBLEM_AUTHORING.md](PROBLEM_AUTHORING.md). For grading/stress-testing an
existing submission it transfers to `adversarial_grader`, which generates
adversarial cases and runs them via `run_submission` — no approval needed,
since nothing it does mutates anything. See
[ADVERSARIAL_GRADING.md](ADVERSARIAL_GRADING.md).

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
  judge/sandbox via the `run_submission` MCP tool — built in Phase 2 for
  authoring dry-runs, reused as-is by Phase 3's `adversarial_grader` for
  grading. Non-negotiable.
- **D6 — Light RAG, no vector DB service.** In-memory vector store persisted to a
  single JSON file; a real vector DB is a later upgrade behind the same
  `VectorStore` API.

## Cross-cutting seams

- **Guardrail** — screens input before the model runs, on all three agents. See [GUARDRAIL.md](GUARDRAIL.md).
- **Observability** — callbacks, plugins, OpenTelemetry. See [OBSERVABILITY.md](OBSERVABILITY.md).
- **Human-in-the-loop confirmation** — `problem_author` asks in chat and waits
  for an explicit "yes" before calling any mutating tool. This is a prompt
  convention, not a platform-level pause (an earlier version used ADK's
  `require_confirmation`; removed for simplicity — see the tradeoff writeup in
  [PROBLEM_AUTHORING.md](PROBLEM_AUTHORING.md#how-approval-works)).
  `adversarial_grader` needs no such gate — every tool it has is read-only or
  non-persisting, so there's nothing to approve.

## CodeJudge API surface (observed, READ-ONLY)

Gin, base path `/`, envelopes: object `{data:…}`, list adds paging, error
`{error:{code,message}}`.

**Public:**
- `GET /healthz` · `GET /languages`
- `POST /submissions` · `POST /submissions/run` (Run mode: client-supplied cases,
  scored per-case, unpersisted — see [PROBLEM_AUTHORING.md](PROBLEM_AUTHORING.md#dry-running-before-you-commit-run_submission))
- `GET /submissions` · `GET /submissions/:id`
- `GET /problems` (published only) · `GET /problems/:id` (published only)

**Admin** (no real auth yet — single-operator stage; see CodeJudge's own
`docs/PROBLEM_AUTHORING.md`): a full draft → validate → publish lifecycle,
including running a reference solution in the real sandbox as the correctness
gate before anything can go live.
- `POST /admin/problems` · `POST /admin/problems/:id/testcases`
- `PUT /admin/problems/:id/reference` · `GET /admin/problems/:id`
- `POST /admin/problems/:id/validate` · `POST /admin/problems/:id/publish` ·
  `POST /admin/problems/:id/unpublish`

This landed sooner and more completely than the original plan's speculative
admin surface (`run_submission`/`add_problem`/`commit_test_case`) — the MCP tools
in [PROBLEM_AUTHORING.md](PROBLEM_AUTHORING.md) map to what's actually built, not
the earlier guess. (The plan's `run_submission` name did land, just for a
different purpose — see the naming note in PROBLEM_AUTHORING.md.) `GET
/submissions/:id` sat unused as a tool until Phase 3 added `get_submission` —
see [ADVERSARIAL_GRADING.md](ADVERSARIAL_GRADING.md).
