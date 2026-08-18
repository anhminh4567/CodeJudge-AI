# CodeJudge-AI — Development Phases

The roadmap for the whole AI layer, from where we are now to the full vision.
Each **phase** is a capability that works end-to-end; each phase breaks into
small **steps (S#)** that are individually buildable and reviewable. Commits
(A, B1…) map onto steps so git history mirrors this plan.

Legend: ✅ done · 🔨 in progress · ⬜ not started · ⛔ blocked on CodeJudge (read-only; another agent owns it)

---

## Phase 1 — Visitor Q&A (RAG + live lookup)   🔨

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

## Phase 2 — Problem authoring (admin, human-in-the-loop)   ✅ done

**Goal:** as an admin you say "add a problem about X"; the agent proposes one,
you approve, it drafts example + edge test cases, you accept/reject, sets a
reference solution, runs it for real to prove the cases are correct, and only
then publishes. Every mutating step is gated by your approval.

CodeJudge's admin/drafting endpoints (S9's staging→verify→ready idea) landed
sooner than expected — the other agent shipped the full draft → validate →
publish lifecycle, including running a reference solution in the real sandbox as
the correctness gate. Details: [PROBLEM_AUTHORING.md](PROBLEM_AUTHORING.md).

| Step | What | Notes |
|------|------|-------|
| S5 | Read tools via MCP: `list_problems`, `get_problem_status` (+ existing `get_problem_spec`) | so the agent sees what already exists before proposing |
| S6 | **Draft step** — `problem_author` sub-agent proposes a problem, `create_draft_problem` is gated on human approval | ✅ |
| S7 | **Test-case batch** — dry-run candidates via `run_submission` (nothing persisted, no approval needed), then `add_test_cases` (loops the endpoint, one approval per batch, not per case) | ✅ |
| S8 | **Persist + verify** — `set_reference_solution`, `validate_problem` (runs the reference for real, polls to completion), `publish_problem`/`unpublish_problem` — all real writes, all gated except validate (gate is a chat-approval instruction, not a tool-level mechanism) | ✅ verified end-to-end against a live CodeJudge: draft → dry-run → commit → validate → publish, chat-approval gate held up through all of it |
| S9 | Staging → verify → ready | ✅ **this is what S8 turned out to be** — CodeJudge's DRAFT/PUBLISHED + validate gate covers it; no separate step needed |

Tools added this phase (`codejudge_mcp/server.py`, each a `@mcp.tool()`):
`get_problem_status`, `validate_problem`, `run_submission`,
`create_draft_problem`, `add_test_cases`, `set_reference_solution`,
`publish_problem`, `unpublish_problem`. A new sub-agent, `problem_author`
(`codejudge_ai/agent/problem_author.py`), owns them; `root_agent` transfers to it
for authoring requests. `run_submission` (wrapping CodeJudge's later-added
"Run mode", `POST /submissions/run`) lets the agent dry-run a candidate
solution against candidate cases before committing either — see
[PROBLEM_AUTHORING.md](PROBLEM_AUTHORING.md#dry-running-before-you-commit-run_submission).

**Done:** a full draft → dry-run → commit → validate → publish run against a
live CodeJudge succeeded via `adk web`, and the chat-approval convention (see
PROBLEM_AUTHORING.md's "How approval works") held up through every mutating
step of that run with no tool-level mechanism backing it up. Still worth an
occasional eye on — nothing platform-level stops a future model from skipping
the ask — but no longer a blocker.

---

## Phase 3 — AI grading with adversarial cases   ⬜ next up ← we are here

**Goal:** a genuine agent loop that, for a submission, generates adversarial test
cases, runs them through CodeJudge's real sandbox, and reasons over the actual
results to judge robustness.

- No new MCP tool needed for the core loop — `run_submission` (built in Phase 2
  for authoring dry-runs, wrapping `POST /submissions/run`) already does exactly
  this shape: run arbitrary code against client-supplied cases, scored per-case,
  nothing persisted. Grading a user's submission against agent-generated
  adversarial cases is the same call with a different caller/purpose.
- Agent loop: hypothesize edge cases → run_submission → observe verdicts → refine.
- **Hard rule (D5): the LLM never executes code itself** — all execution goes
  through CodeJudge's judge/sandbox via run_submission. Non-negotiable.
- Open question: does the adversarial-grading agent need its own MCP tool
  scoping/permissions distinct from problem_author's, or can it share
  run_submission's toolset? Decide when this phase starts.

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
| (hardening) | Observability hooks (callbacks/plugin/OTel) + input guardrail + RAG min-score + instruction fix | ✅ committed |
| D1 | S5-S8 — problem_author sub-agent, 8 admin MCP tools (incl. `run_submission` dry-run), chat-approval convention for mutating tools (superseded `require_confirmation` before this ever shipped), persistent ADK session storage | ✅ committed (`febbdd1`) |

See `OVERVIEW.md` for a plain-language tour of the Python project,
and the repo root `CLAUDE.md` for the locked architecture decisions.
