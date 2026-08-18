# Adversarial grading (Phase 3, S10-S12)

How the agent stress-tests someone's real CodeJudge submission with
AI-generated adversarial cases and reports how robust it actually is. Code:
[`codejudge_ai/agent/adversarial_grader.py`](../codejudge_ai/agent/adversarial_grader.py),
[`codejudge_mcp/server.py`](../codejudge_mcp/server.py).

## The workflow

```
"grade submission X" or "here's my code for problem Y"
                │
                ▼
     resolve problem_id / language / source_code
     (get_submission, or code pasted directly in chat)
                │
                ▼
     get_problem_spec(problem_id)  ◀── the ONLY source of truth;
                │                      no reference solution reachable, ever
                ▼
     design a batch: problem's own sample cases (free, zero-risk oracle)
              + hand-crafted adversarial cases with hand-derived expected
                output (confident → scored; unsure → left unscored)
                │
                ▼
     run_submission(problem_id, language, source_code, cases)  ◀── no approval
                │                                                  needed, nothing
                │ (≤1 narrower follow-up call allowed)              persisted
                ▼
     report: samples → scored verdicts → observed/unscored cases →
             overall read → "this is diagnostic, not an official verdict"
```

This reuses `run_submission` (built in Phase 2 for authoring dry-runs) for a
different caller and purpose: instead of proving a candidate solution/case
pair agree before committing them, it proves whether *someone else's already-
submitted* code holds up against cases it never saw. Same tool, same contract
(client-supplied cases, scored per-case, nothing persisted, excluded from
submission history) — see
[PROBLEM_AUTHORING.md](PROBLEM_AUTHORING.md#dry-running-before-you-commit-run_submission)
for how it's implemented.

## Why a sub-agent, not more tools on `root_agent`

Same rationale as `problem_author`: `root_agent` answers visitor Q&A, a
different job from a multi-step grading workflow with its own tool scoping
concerns (see below). `root_agent` transfers to `adversarial_grader`
automatically via ADK's `sub_agents=[...]`, based on `adversarial_grader`'s
`description` field — no custom routing code.

## The MCP tools

| Tool | Wraps | Approval needed? |
|------|-------|----|
| `get_problem_spec` | public `GET /problems/:id` | no (read) |
| `get_submission` | public `GET /submissions/:id` | no (read) |
| `run_submission` | `POST /submissions/run`, **polled internally** until finished | no — nothing persisted, excluded from history |

All three are read-only or non-persisting, so — unlike `problem_author` —
`adversarial_grader`'s instruction has **no approval-gate step at all**.
Nothing this agent does needs a human "yes" first, because nothing it does
can be undone-because-it-never-happened-in-the-first-place: no draft, no
committed case, no publish.

`get_submission` is new this phase: it wraps `codejudge_client.get_submission()`
(`GET /submissions/:id`), which already existed internally (used by the
polling helper) but wasn't exposed as a tool until now. It lets someone say
"grade submission abc123" instead of re-pasting code they already sent to
CodeJudge.

## Where the answer key comes from

This is the one real design gap Phase 1/2's planning left open. `problem_author`
always has an answer key because it drafts the reference solution and the
cases together. `adversarial_grader` has no such luxury — it's judging code it
didn't write, for a problem whose reference solution is deliberately
unreachable to it: `get_problem_status` (the admin tool that exposes a
reference solution) is not in this agent's toolset at all, not filtered out by
instruction but structurally absent, so there's no way for the model to reach
for it even if confused. Handing a grading agent the answer key would mean it
could always report "PASS" by comparing against ground truth it was never
supposed to have — worse, for a real learner asking to have their own
submission graded, that reference solution would effectively be exposed.

So the agent derives every adversarial case's expected output itself, from the
problem statement alone, in step 3 of its workflow — the same kind of
reasoning `problem_author` does when it first drafts cases before it has
proven a reference solution. Two safety nets keep this honest rather than
hand-wavy:

1. **The problem's own sample cases are always included**, unmodified. Their
   expected outputs came from CodeJudge itself, not the grading agent's own
   reasoning — a free, zero-risk anchor in every report.
2. **Confidence is tracked per case.** A case the agent is confident about
   gets a real `expected_stdout`, so `run_submission` scores it AC/WA for
   real. A case it isn't sure about is submitted with `expected_stdout` left
   empty — `run_submission`/`RunCase` already support this (the same
   mechanism `problem_author` uses to eyeball a case before committing) — so
   the agent gets the actual output back and applies its own judgment,
   labeled as such, never presented with the same weight as a scored verdict.

The report's final line is always the same caveat, not optional: this is a
diagnostic self-check, not an official CodeJudge verdict, and a scored WA
could reflect a mistake in the *agent's own* derivation, not a bug in the
submission — because there's no reference solution to check its own work
against.

## Known limitations

- **Accuracy is bounded by the agent's own reasoning, not verified against
  ground truth.** This is the core, accepted tradeoff described above — not a
  bug to fix, but something every report must keep surfacing rather than
  letting a scored WA read as more authoritative than it is.
- **`get_submission` has no auth**, same as every other CodeJudge endpoint
  today (see the repo root `CLAUDE.md` / `docs/ARCHITECTURE.md`) — any
  submission id is fetchable by anyone who can reach the MCP server. This is
  an inherited gap from CodeJudge's current single-operator/no-auth stage,
  not something this tool introduces or can fix on its own.
- **Bounded, not exhaustive.** The two-call cap on `run_submission` (see the
  agent's instruction) keeps this a predictable, quick check rather than an
  open-ended search for bugs — a "clean" report means the cases tried didn't
  find anything, not that none exist.

## Testing status

Verified: static import/wiring (`adversarial_grader` builds, appears in
`root_agent.sub_agents`, `get_submission` registers as an MCP tool alongside
the existing ten); scripted transfer-routing via `InMemoryRunner` (an
authoring request → `problem_author`, a grading request → `adversarial_grader`,
plain Q&A → neither, all as expected); a manual run against a live CodeJudge
via `adk web` — the hand-off, tool sequence, and report all worked end-to-end.
Quality assessed as **average**: the workflow runs, but the adversarial cases
and reasoning it produces need more prompt refinement to be reliably sharp —
deferred, not urgent.

**Not yet verified**: the `get_submission` shape in a case where
`problemId`/`language`/`sourceCode` are actually missing (the fallback path
hasn't been exercised, only the happy path), and a rigorous end-to-end test
with a *deliberately* buggy submission to confirm the generated cases would
actually catch a known bug (the manual run above didn't specifically target
this). See [RUNNING.md](RUNNING.md) for the 3-process topology.

Related: [PROBLEM_AUTHORING.md](PROBLEM_AUTHORING.md) (the sibling sub-agent,
and where `run_submission` was originally built), [ARCHITECTURE.md](ARCHITECTURE.md),
[GUARDRAIL.md](GUARDRAIL.md) (the same input guardrail also runs on
`adversarial_grader`).
