# CodeJudge-AI — Development Phases

The roadmap for the whole AI layer, from where we are now to the full vision.
Each **phase** is a capability that works end-to-end; each phase breaks into
small **steps (S#)** that are individually buildable and reviewable. Commits
(A, B1…) map onto steps so git history mirrors this plan.

Legend: ✅ done · 🔨 in progress · ⬜ not started · ⛔ blocked on CodeJudge (read-only; another agent owns it)

---

## Phase 1 — Visitor Q&A (RAG + live lookup)   🔨 ← we are here

**Goal / definition of done:** one agent that, per question, decides whether to
answer from ingested documents (RAG) or from a live CodeJudge lookup, and answers
grounded in the right source. This is the **PoC milestone** — it proves real
model-driven tool selection, MCP, and RAG working together.

| Step | What | Where | Status |
|------|------|-------|--------|
| S0 | MCP server scaffold + `get_problem_spec` tool | `codejudge_mcp/` (Python) | ✅ |
| S1 | Docs sync script (copy CodeJudge Markdown → `corpus/`) | `codejudge_ai/scripts/sync_docs.py` | ✅ |
| S2 | RAG ingest pipeline (extract → chunk → embed → in-memory vector store) | `codejudge_ai/rag/*`, `codejudge_ai/scripts/ingest.py` | ✅ |
| S2v | Verify live embedding + a real query end-to-end | needs `GEMINI_API_KEY` | ⬜ |
| S3 | `search_ingested_docs` tool + a bare RAG-only agent (first working Q&A) | `codejudge_ai/agent/`, `scripts/chat.py` | ✅ |
| S4 | Live MCP tools (`list_problems`, `get_problem_spec`) so the agent *chooses* RAG vs live lookup | agent wiring + MCP client | ✅ wired & routing-verified (live-data test pending a running CodeJudge) **← PoC**|

**Status:** Phase 1 is functionally complete. The agent (ADK `LlmAgent`) routes
between RAG (`search_ingested_docs`) and live MCP tools (`list_problems`,
`get_problem_spec`) per question, run locally via `InMemoryRunner`/`adk web`. The
only unverified piece is live problem *data*, which needs a running CodeJudge.
(`list_problems` was pulled forward from Phase 2's S5 since it's the natural
first read-path test.)

---

## Phase 2 — Problem authoring (admin, human-in-the-loop)   ⬜ next

**Goal:** as an admin you say "add a problem about X"; the agent proposes one,
you approve, it drafts example + edge test cases, you accept/reject, and only
then does it create the problem through CodeJudge's API. Every write is gated by
your approval — the agent never persists anything unilaterally.

| Step | What | Notes |
|------|------|-------|
| S5 | Read tools via MCP: `list_problems`, `list_languages` (+ existing `get_problem_spec`) | so the agent sees what already exists before proposing |
| S6 | **Draft step** — agent proposes a problem (statement, mode, signature, limits), then returns to you and waits | no writes yet; pure proposal |
| S7 | **Test-case sub-loop** — on approval, agent drafts sample + edge cases, returns for accept/reject/tweak | iterative until you're happy |
| S8 | **Persist on accept** — agent calls MCP `add_problem` + `commit_test_case` → real problem via `POST /problems`, `POST /problems/:id/testcases` | first real writes |
| S9 | **(Future) staging → verify → ready** — create problem as *staging*, run a reference solution through `run_submission`, confirm all cases pass, then flip to *ready* | ⛔ needs NEW CodeJudge endpoints (staging state, reference-solution run). Flag to the other agent; don't fake it. |

New MCP tools this phase adds: `list_problems`, `list_languages`, `add_problem`,
`commit_test_case` (and later `run_submission`). Each is one file in
`codejudge_mcp/server.py` (each tool is a `@mcp.tool()`).

---

## Phase 3 — AI grading with adversarial cases   ⬜ later

**Goal:** a genuine agent loop that, for a submission, generates adversarial test
cases, runs them through CodeJudge's real sandbox, and reasons over the actual
results to judge robustness.

- Add MCP `run_submission` (POST `/submissions` + poll `GET /submissions/:id`).
- Agent loop: hypothesize edge cases → run → observe verdicts → refine.
- **Hard rule (D5): the LLM never executes code itself** — all execution goes
  through CodeJudge's judge/sandbox. Non-negotiable.
- Likely ⛔ on some CodeJudge admin endpoints (ad-hoc runs without persisting a
  problem); flag as we hit them.

---

## Phase 4 — Productionizing   ⬜ someday

Not needed for the PoC; captured so we don't forget:

- Real UI to replace the terminal `InMemoryRunner` (the human-in-the-loop "screen").
- Deployment: containerize `codejudge-mcp` and `codejudge-ai` as separate services.
- RAG upgrades: swap the flat file for a real vector DB (Chroma/Qdrant) *only if*
  the doc set outgrows it; consider multimodal `gemini-embedding-2` for PDFs.
- Split the RAG module into its own `docs-rag-mcp` server if other MCP clients
  (Claude Code, Gemini CLI) should query the same ingested docs.

---

## How commits map to steps

| Commit | Covers | Status |
|--------|--------|--------|
| A | S0 (codejudge-mcp scaffold + `get_problem_spec`) | ✅ committed |
| B1 | codejudge-ai skeleton, config, docs (OVERVIEW/README) | ✅ committed |
| B2 | RAG text processing (extract + chunk) | ✅ committed |
| B3 | RAG vector layer (embed + store + search) | ✅ committed |
| B4 | Runnable scripts (sync_docs + ingest) | ✅ committed |
| (restructure) | Python AI to repo root, MCP under a subfolder | ✅ committed |
| (RAG libs) | LangChain splitter + InMemoryVectorStore | ✅ committed |
| C1 | S3 — RAG-only ADK agent + chat script | ✅ committed |
| (server) | Example FastAPI server with /healthz | ✅ committed |
| (mcp-python) | Rewrite MCP server in Python (drop Go; revises D2) | ✅ committed |
| C2 | S4 — live MCP tools wired into the agent (the PoC) + `list_problems` | ✅ committed |
| (hardening) | Observability hooks (callbacks/plugin/OTel) + input guardrail + RAG min-score + instruction fix | pending review |

See `OVERVIEW.md` for a plain-language tour of the Python project,
and the repo root `CLAUDE.md` for the locked architecture decisions.
