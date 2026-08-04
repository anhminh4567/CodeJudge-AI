# CLAUDE.md — CodeJudge-AI

Guidance for Claude Code when working in this repository.

## Repository boundaries (READ CAREFULLY)

- **This repo (`CodeJudge-AI`) is the ONLY place I write.** It is my main work folder.
- **`CodeJudge` (sibling repo, `C:\Users\anhmi\GolandProjects\CodeJudge`) is READ-ONLY.**
  Another agent owns it. I may read it for reference (API shape, DTOs, domain
  types) but must **never** create, edit, move, or delete anything there.
  `CodeJudge` is the *endpoint* the AI agent's MCP layer will talk to over HTTP.

## Working rules (agreed with the user)

1. **Commits require explicit approval.** Before every `git commit`, ask the user
   first so they can review. Never commit unprompted.
2. **Commit size:** medium-to-large, cohesive blocks. Do **not** split into many
   tiny commits. One commit can be a large block of code when that keeps a change
   coherent.
3. **Plan before code.** Discuss and agree on a plan before implementing anything
   non-trivial.
4. Only READ `CodeJudge`; all edits land in `CodeJudge-AI`.

## What this project is

`CodeJudge-AI` is the **AI layer** on top of the existing `CodeJudge` online judge.
Full design is in [codejudge-ai-final-plan.md](codejudge-ai-final-plan.md); the
build roadmap (phases, steps, current status, commit map) is in
[DEVELOPMENT_PHASES.md](DEVELOPMENT_PHASES.md); a plain-language tour of the Python
project is in [codejudge-ai/OVERVIEW.md](codejudge-ai/OVERVIEW.md). Summary:

Three capabilities the AI layer provides:
1. **Answer visitor questions** — RAG over site docs + ingested PDFs/Word, plus
   live problem lookups. Retrieval + generation, low risk.
2. **Author problems / generate & validate test cases** — a mostly-deterministic
   pipeline (draft → validate → persist) with an iterative sub-loop.
3. **Grade a submission with AI-generated adversarial cases** — a real agent loop,
   grounded by actual sandboxed execution in CodeJudge.

### Locked architecture decisions (from the plan)

- **D1 — Microservices.** Separate repos/binaries from CodeJudge. They talk over
  CodeJudge's HTTP API only; no shared module, no in-process calls.
- **D2 — Polyglot.** `codejudge-mcp` in **Go** (thin MCP server wrapping CodeJudge's
  HTTP API). `codejudge-ai` in **Python** (Google ADK agent brain + document RAG).
- **D3 — Workflow where predictable, agent where judgment is needed.**
- **D4 — MCP over Streamable HTTP** at every tool boundary.
- **D5 — The LLM never executes code.** All execution goes through CodeJudge's
  judge/sandbox via a `run_submission` tool. Non-negotiable.
- **D6 — Light RAG, no vector DB.** Flat-file vector store + cosine similarity for
  the PoC; a real vector DB is a later upgrade.

### Planned services

| Service | Language | Depends on |
|---|---|---|
| `codejudge-mcp` | Go | CodeJudge's HTTP API |
| `codejudge-ai` | Python (`google-adk`) | `codejudge-mcp` (MCP/HTTP) + Gemini API |

RAG pipeline (deliberately minimal): extract (`pypdf`/`python-docx`) → chunk
(recursive char splitter) → embed (`gemini-embedding-001`) → flat-file store →
top-k cosine retrieval, exposed to the agent as `search_ingested_docs(query)`.

## CodeJudge API surface (the MCP wraps this) — observed, READ-ONLY

From `CodeJudge/cmd/api/main.go` (Gin, base path `/`, JSON envelopes: objects as
`{data:...}`, lists add paging, errors as `{error:{code,message}}`):

- `GET  /healthz`
- `POST /submissions` — `{id?, problemId, language, sourceCode}` → 202 `{id, status}`
- `GET  /submissions` — list
- `GET  /submissions/:id` — detail with per-case `{caseId, verdict, timeMs, memKb}`
- `GET  /problems` / `POST /problems` / `GET /problems/:id`
- `POST /problems/:id/testcases` — `{stdin, expectedStdout, sample}`
- `GET  /languages`
- `GET  /swagger/*any`

Problems have a `mode` of `stdio` or `function` (+ `signature`, `entryFunc`) and
`limits {wallTimeMs, memoryMb, cpus, pidsMax}`.

**Note / open boundary:** the plan assumes CodeJudge gains an internal/admin API
(service-token gated: ad-hoc `run_submission`, `add_problem`, `commit_test_case`).
Today only the **public** endpoints above exist and there is **no auth**. Since
CodeJudge is read-only to me, the MCP will wrap what exists; anything needing new
CodeJudge endpoints is a dependency on the other agent — flag it, don't assume it.

## PoC target (first milestone)

One `LlmAgent` that, per visitor question, chooses between `search_ingested_docs`
(RAG) and `get_problem_spec` (live lookup via `codejudge-mcp`) — proving real
model-driven tool selection across two genuinely different sources, MCP, and RAG
together. Run locally via ADK's `InMemoryRunner`; no deployment needed to see it work.
