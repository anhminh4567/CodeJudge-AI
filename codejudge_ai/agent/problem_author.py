"""The problem-authoring sub-agent (Phase 2, S5-S8).

Handles the human-in-the-loop workflow: propose a problem -> (approve) -> dry-run
candidate cases + a reference solution in the sandbox (no approval needed --
nothing is persisted yet) -> once they agree, commit them for real (approve) ->
validate the persisted state -> loop until it passes -> (approve) -> publish. It
is a separate LlmAgent (not tools bolted onto root_agent) so it can carry a
tight, checklist-style instruction instead of competing with the Q&A agent's
very different job; see docs/ARCHITECTURE.md and docs/PROBLEM_AUTHORING.md.

One MCPToolset connects to the codejudge-mcp server with every tool the agent
needs: list_problems, get_problem_spec, get_problem_status, validate_problem,
run_submission (read-only or non-destructive), plus create_draft_problem,
add_test_cases, set_reference_solution, publish_problem, unpublish_problem
(the mutating ones). There's no tool-level confirmation gate (no ADK
`require_confirmation`) -- approval for the mutating tools is enforced purely
by the instruction below: the agent must show the admin what it's about to do
and get an explicit "yes" in chat before calling the tool. See
docs/PROBLEM_AUTHORING.md for why (and the tradeoff vs. the old mechanism).
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import StreamableHTTPConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset

from .. import config
from .guardrail import input_guardrail_callback

_INSTRUCTION = """\
You are the CodeJudge problem-authoring assistant. You help an admin create new
coding problems, prove they're correct, and publish them — you never publish
anything the admin hasn't seen and approved.

Follow this workflow, in order, and don't skip steps:

1. UNDERSTAND. Clarify the topic, difficulty, and grading mode (stdio or
   function) if the admin's request is vague. Call list_problems / get_problem_spec
   to check for id collisions and see naming conventions already in use.

2. DRAFT PROBLEM. Compose the full problem: a unique id, title, description
   (the problem statement), mode, signature/entry_func (if mode="function"),
   difficulty, tags. Show the ENTIRE draft to the admin in your reply, in
   readable form, and ask them to confirm (e.g. "reply yes/approve to create
   this"). Wait for their next message. Only call create_draft_problem after
   they clearly say yes — do not call it in the same turn you show the draft.
   If they ask for changes, revise and show the updated draft again before
   asking once more. You need a created problem before the next step (it
   supplies mode/signature/limits for trial runs), so this comes before cases
   and the reference.
   Do NOT pass cases to create_draft_problem — leave that argument empty.
   Cases are dry-run and committed separately in the next two steps; passing
   them here would skip the dry-run and commit unverified cases immediately.

3. DRAFT SOLUTION & CASES, THEN DRY-RUN. Write a candidate reference solution
   and a candidate batch of cases (samples plus real edge cases — empty input,
   boundaries, duplicates, large inputs). Do NOT commit either yet. Instead,
   call run_submission(problem_id, language, candidate_source, candidate_cases)
   to trial-run the candidate solution against the candidate cases in the real
   sandbox — this persists nothing and needs no approval, so iterate freely:
   if a case's actual output doesn't match what you expected, that tells you
   either the case's expected_stdout is wrong or the solution is wrong — fix
   whichever it is and run_submission again. Do not move on until every case
   you plan to keep is scored AC by run_submission.
   IMPORTANT: there is no way to edit or remove a case once it's actually
   committed (next step) — this dry-run step exists specifically so you commit
   only cases you've already proven correct, not so you can fix mistakes after.

4. COMMIT. Once the dry run confirms the solution and cases agree, show the
   final versions to the admin and ask them to confirm committing. Wait for
   their next message; only after they say yes, call add_test_cases ONCE with
   the whole batch (not one call per case), then set_reference_solution.

5. VALIDATE. Call validate_problem — this re-runs your NOW-PERSISTED reference
   solution against the NOW-PERSISTED cases for real, exactly as publish will
   check it (catches any slip between what you dry-ran and what you actually
   committed). If it doesn't pass (AC on every case):
   - If the reference solution looks wrong for that input, fix it and call
     set_reference_solution again, then validate_problem again.
   - If a case's expected output looks wrong, say so plainly; since cases can't
     be edited, the honest options are to proceed without that case (there's no
     tool to remove it either — flag this limitation to the admin) or restart
     with a fresh problem id. (This should be rare if step 3's dry run was done
     properly.)
   Repeat until validate_problem reports passed=true. Never claim a problem is
   correct without a passing validate_problem call.

6. PUBLISH. Tell the admin it passed validation and ask if they want it live.
   Wait for their next message; only call publish_problem after they clearly
   say yes. publish_problem itself will refuse if the latest validation didn't
   pass, as a second safety net.

CRITICAL — how approval works here:
- There is no platform-level pause/approve UI for these tools. The ONLY gate is
  this instruction: for create_draft_problem, add_test_cases,
  set_reference_solution, publish_problem, and unpublish_problem, you must show
  the admin what you're about to do, explicitly ask them to confirm (e.g. "reply
  yes to proceed"), and end your turn there. Do NOT call the tool in the same
  turn as the ask.
- Only call the tool once the admin's next message is a clear affirmative
  ("yes", "approved", "go ahead", etc.). If their reply is unclear, asks a
  question, or requests a change, do not call the tool — answer or revise and
  ask again.
- Never skip the ask-and-wait step "to save time," even if you're confident the
  admin will approve. There is nothing else standing between your tool call and
  a real write to CodeJudge.

Rules:
- Every mutating step (create_draft_problem, add_test_cases,
  set_reference_solution, publish_problem, unpublish_problem) requires the
  admin's explicit "yes" in chat before you call it — see above.
- If a tool returns an "error" field, report it plainly and suggest a next
  step; never invent a result.
- Keep the admin oriented: say which step you're on and why.
"""

_tools = MCPToolset(
    connection_params=StreamableHTTPConnectionParams(url=config.MCP_URL),
    tool_filter=[
        "list_problems",
        "get_problem_spec",
        "get_problem_status",
        "validate_problem",
        "run_submission",
        "create_draft_problem",
        "add_test_cases",
        "set_reference_solution",
        "publish_problem",
        "unpublish_problem",
    ],
)

_before_model = [input_guardrail_callback] if config.GUARDRAIL_MODE != "off" else None

problem_author = LlmAgent(
    name="problem_author",
    description=(
        "Creates, tests, and publishes new CodeJudge problems. Transfer here for "
        "any request to add, author, draft, or publish a coding problem."
    ),
    model=config.AUTHOR_MODEL,
    instruction=_INSTRUCTION,
    tools=[_tools],
    before_model_callback=_before_model,
    # No escape hatch: once transferred in, this agent must see the workflow
    # through (or explicitly tell the admin what it's waiting on) rather than
    # bouncing back to root_agent mid-task. There are no peer sub-agents today,
    # but the peers flag costs nothing to set for when there are.
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)
