# Problem authoring (Phase 2, S5-S8)

How the agent creates, validates, and publishes new CodeJudge problems, with a
human approving every mutating step. Code:
[`codejudge_ai/agent/problem_author.py`](../codejudge_ai/agent/problem_author.py),
[`codejudge_mcp/server.py`](../codejudge_mcp/server.py). CodeJudge's own design
(read-only reference): `CodeJudge/docs/PROBLEM_AUTHORING.md`.

## The workflow

```
propose problem ──▶ (approve) ──▶ DRAFT
                                     │
                                     ▼
     draft candidate cases + a candidate reference solution
                                     │
                                     ▼
     run_submission(candidate solution, candidate cases)  ◀── no approval needed,
             │                                                nothing persisted;
             │ mismatch                                       iterate freely
             └───────────────── fix candidate, run_submission again
             │ every case scored AC
             ▼
     commit for real: add_test_cases (approve) → set_reference_solution (approve)
                                     │
                                     ▼
                     validate_problem (real sandbox run of the PERSISTED state)
             ▲                      │
             └── fix & re-validate ◀┤ fails
                                     │ passes
                                     ▼
                       ask to publish ──▶ (approve) ──▶ PUBLISHED
```

This is CodeJudge's own draft → validate → publish lifecycle (see its design
doc), driven by a dedicated ADK sub-agent, `problem_author`, with a human
approval step in chat before every step that mutates anything (the agent asks,
you reply, then it calls the tool — see "How approval works" below).
`run_submission` is the dry-run seam: it lets the agent prove a candidate
solution/case pair actually agrees *before* committing either — see
"Dry-running before you commit" below.

## Why a sub-agent, not more tools on `root_agent`

`root_agent` answers visitor Q&A (RAG + live lookups) — a very different job
from a multi-step authoring workflow with a strict order and hard gates.
Splitting them means each agent's instruction stays a tight, single-purpose
checklist instead of one instruction juggling two unrelated jobs. `root_agent`
transfers to `problem_author` automatically: ADK's `sub_agents=[...]` adds a
`transfer_to_agent` tool, and the model decides to use it based on
`problem_author`'s `description` field — no custom routing code.

## The MCP tools

| Tool | Wraps | Approval needed? |
|------|-------|----|
| `list_problems`, `get_problem_spec` | public `GET /problems`(`/:id`) | no (read) |
| `get_problem_status` | `GET /admin/problems/:id` (admin view: drafts, hidden cases, reference) | no (read) |
| `validate_problem` | `POST /admin/problems/:id/validate`, **polled internally** until finished | no — doesn't mutate anything public |
| `run_submission` | `POST /submissions/run`, **polled internally** until finished | no — nothing persisted, excluded from history |
| `create_draft_problem` | `POST /admin/problems` | **yes, in chat** |
| `add_test_cases` | `POST /admin/problems/:id/testcases`, **looped** over a batch | **yes, in chat** |
| `set_reference_solution` | `PUT /admin/problems/:id/reference` | **yes, in chat** |
| `publish_problem` | `POST /admin/problems/:id/publish` | **yes, in chat** |
| `unpublish_problem` | `POST /admin/problems/:id/unpublish` | **yes, in chat** |

"Yes, in chat" means: `problem_author` shows the admin what it's about to do,
asks for confirmation, and waits for their next message before calling the
tool — see "How approval works" below. None of these tools are gated at the
MCP/ADK level; the toolset in `problem_author.py` sets no `require_confirmation`
and every tool is callable the moment the model decides to call it. The only
thing standing between a model decision and a real write is the instruction.

Three deliberate departures from a strict 1:1 endpoint mapping:

- **`validate_problem` polls internally.** CodeJudge's `/validate` is
  async — it enqueues a submission and returns an id to poll. The tool polls
  `GET /submissions/:id` itself (bounded to ~60s) so the agent gets one clean
  pass/fail instead of hand-rolling a poll loop. Deterministic plumbing (D3),
  not agent judgment. `run_submission` shares this same polling helper
  (`_poll_submission` in `codejudge_client.py`) since `POST /submissions/run`
  is async the same way.
- **`add_test_cases` is a batch**, not one call per case. The intent was "review
  a set of examples once, not five times" — so the tool loops
  `POST .../testcases` server-side and one confirmation covers the whole batch.
- **`run_submission` requires an existing `problem_id`.** CodeJudge's Run mode
  borrows that problem's `mode`/`signature`/`limits` so a trial run compiles,
  wraps, and bounds identically to a real submission — only the cases (and the
  code being tried) differ. This is why `create_draft_problem` must happen
  before any dry-running: the draft supplies those fields.

## Dry-running before you commit (`run_submission`)

CodeJudge added a "client-driven Run mode" (`POST /submissions/run`) after the
initial authoring endpoints landed — a way to grade arbitrary code against
arbitrary cases *without persisting anything*. A case with a non-empty expected
output is scored (AC/WA) the same way a real submission would be; a case left
empty just runs and returns what the code printed, for eyeballing. It never
touches submission history.

This closes a real gap: originally the only way to check a candidate case was
correct was to commit it via `add_test_cases` and then `validate_problem` —
but cases can't be edited or removed once committed (see below), so a wrong
guess was a dead end. Now `problem_author`'s instruction inserts a dry-run step
between drafting and committing: write a candidate reference solution and
candidate cases, call `run_submission(problem_id, language, candidate_source,
candidate_cases)`, and iterate — free, ungated, nothing persisted — until every
case the admin wants to keep is scored AC. Only then does it call
`add_test_cases` / `set_reference_solution` for real. `validate_problem`
afterward is still the authoritative final check (it grades what was actually
persisted, catching any slip between the dry run and the commit).

**Naming note:** the original plan (`codejudge-ai-final-plan.md`) reserved the
name `run_submission` for a *different*, not-yet-built Phase 3 tool — grading a
user's real submission against agent-generated adversarial cases. That turned
out to be the same shape (client-supplied cases, scored per-case, unpersisted)
as this Run-mode wrapper, so Phase 3 will just reuse this tool rather than
build a second one under a different name — see
[DEVELOPMENT_PHASES.md](DEVELOPMENT_PHASES.md).

**A real bug this caught during testing:** without an explicit instruction
against it, the model bundled candidate cases directly into
`create_draft_problem`'s optional `cases` argument — skipping the dry-run
entirely, since that argument commits cases immediately. Fixed by having the
tool's own docstring say "leave this empty" and having the agent instruction
say the same, explaining why. Verified after the fix: `create_draft_problem`
calls now carry an empty `cases` list.

## How approval works

There is no tool-level gate anymore. Earlier this used ADK's real
`require_confirmation` primitive (`long_running_tool_ids` + a synthetic
`adk_request_confirmation` pause/resume) — a genuine suspension of the run that
only a UI rendering approve/reject cards (like `adk web`'s dashboard) could
drive. That meant authoring conversations only worked in `adk web`; our own
`chat.py` REPL had no code to notice the pause or resume the right
`invocation_id`.

That mechanism was removed. Approval is now purely conversational, enforced by
`problem_author`'s instruction (`codejudge_ai/agent/problem_author.py`):

1. Before calling any mutating tool (`create_draft_problem`, `add_test_cases`,
   `set_reference_solution`, `publish_problem`, `unpublish_problem`), the agent
   shows the admin what it's about to do and asks them to confirm, then ends
   its turn — it does not call the tool in the same turn as the ask.
2. The admin's next chat message is read by the model like any other turn. If
   it's a clear "yes"/"approve"/"go ahead", the instruction tells the model to
   proceed with the tool call. Anything else (a question, a requested change,
   an unclear reply) means don't call it.
3. There's no platform enforcement of step 2 — nothing stops the model from
   calling the tool anyway if it misreads the reply. This is a real, accepted
   tradeoff: it's simpler, it works in any chat surface (including our own
   `chat.py`, closing the old `adk web`-only gap), and it's easier to reason
   about than the pause/resume mechanics — but the safety now rests entirely on
   the model actually following the instruction. See `AUTHOR_MODEL` in
   `config.py`: a weak/cheap model is more likely to skip the ask, which is why
   authoring defaults to a capable model and that's configurable independently
   of the Q&A agent's model.

If this turns out to be unreliable in practice (the model calls a mutating tool
without waiting for a "yes"), the fix is either a stronger `AUTHOR_MODEL` or
reintroducing a tool-level gate for just the highest-risk tools
(`publish_problem` is the one genuinely hard-to-reverse action here, since
drafts and unpublished mistakes are cheap to abandon).

## Known limitation: cases can't be edited or removed

CodeJudge exposes no update/delete for a test case once added — this is still
true. The dry-run step above is the mitigation: cases should already be proven
correct via `run_submission` before `add_test_cases` ever runs, so this
limitation should rarely bite in practice. If it still happens (e.g. the admin
directs a fresh case be added without dry-running), `problem_author`'s
instruction falls back to: fix the reference solution instead (most
"validation failed" cases are actually a wrong reference, not a wrong case) or
start a fresh problem id — and say so plainly rather than pretending a fix is
possible.

## Testing status

Verified end-to-end against a live CodeJudge via `adk web`: propose → approve
draft → dry-run candidates via `run_submission` → commit (`add_test_cases`,
`set_reference_solution`) → `validate_problem` → publish, with the
chat-approval convention (ask, wait for "yes", then call) holding up through
every mutating step of that run. Also verified earlier: sub-agent transfer,
and that `create_draft_problem` no longer bundles unverified cases.

Not a platform guarantee, though — one clean run doesn't rule out a future
model skipping the ask under different phrasing or pressure. Worth an
occasional spot-check, especially before pointing a new/cheaper `AUTHOR_MODEL`
at this. See [RUNNING.md](RUNNING.md) for the 3-process topology.

Related: [ARCHITECTURE.md](ARCHITECTURE.md), [GUARDRAIL.md](GUARDRAIL.md) (the
same input guardrail also runs on `problem_author`), [OBSERVABILITY.md](OBSERVABILITY.md).
