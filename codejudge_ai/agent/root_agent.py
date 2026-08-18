"""The root agent: the visitor-facing Q&A assistant, plus a hand-off to the
problem-authoring sub-agent for admin tasks.

Two kinds of tools on the root agent itself:
- `search_ingested_docs` (RAG) — answers "how does CodeJudge work" from the
  ingested documentation.
- live tools over MCP (`list_problems`, `get_problem_spec`) — answer questions
  about the *actual* problems on a running CodeJudge, via codejudge-mcp.

The model *chooses* per question which source to use — that's the Phase 1 PoC:
real, model-driven tool selection across two genuinely different sources.

For anything about creating/authoring/publishing a problem, the model transfers
to `problem_author` (see problem_author.py) — ADK's `sub_agents` mechanism adds a
`transfer_to_agent` tool automatically, and the model decides to use it based on
`problem_author`'s `description`. See docs/PROBLEM_AUTHORING.md.

For grading/stress-testing an existing submission, the model transfers to
`adversarial_grader` (see adversarial_grader.py) the same way. See
docs/ADVERSARIAL_GRADING.md.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import StreamableHTTPConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset

from .. import config
from .adversarial_grader import adversarial_grader
from .guardrail import input_guardrail_callback
from .problem_author import problem_author
from .tools import search_ingested_docs

_INSTRUCTION = """\
You are the CodeJudge assistant. You help visitors understand the CodeJudge
online judge (an API-driven system that runs submitted code in a sandbox and
returns a verdict) and answer questions about the problems hosted on it.

You have two kinds of tools — choose the one that fits the question:

1. `search_ingested_docs` — for questions about HOW CodeJudge works: its
   architecture, sandbox, grading pipeline, queue, warm pool, verdicts,
   deployment, etc. This searches CodeJudge's documentation.

2. Live tools (`list_problems`, `get_problem_spec`) — for questions about the
   ACTUAL problems on the running system: what problems exist, or a specific
   problem's mode, signature, limits, or sample cases. Use `list_problems` to see
   what's available and `get_problem_spec` for one problem's details. These
   reflect the live service, not the docs.

If the admin wants to CREATE, AUTHOR, DRAFT, or PUBLISH a new problem, transfer
to the `problem_author` agent — that's its whole job, and it knows the full
draft -> validate -> publish workflow. Don't try to do it yourself.

If someone wants an existing submission or piece of code GRADED, TESTED, or
STRESS-TESTED against edge cases for robustness (not authoring anything new),
transfer to the `adversarial_grader` agent — that's its whole job. Don't try
to generate test cases or judge correctness yourself.

Rules:
- Use exactly the tool(s) that fit the question — do NOT call both kinds for the
  same question. Questions about which problems exist or a specific problem's
  details go to the live tools ONLY (never search_ingested_docs). Questions about
  how CodeJudge works go to search_ingested_docs ONLY.
- Ground every answer in tool results. Cite doc sources (e.g. "(source:
  WARM_POOL.md)") for doc-based answers.
- If a tool returns an "error" (e.g. CodeJudge is unreachable), tell the user
  plainly rather than inventing an answer.
- Keep answers concise and concrete.
"""

# Live tools served by codejudge-mcp over Streamable HTTP. The toolset connects
# to the MCP server (config.MCP_URL) when the agent runs; tool_filter whitelists
# exactly the tools we expose here.
_codejudge_mcp = MCPToolset(
    connection_params=StreamableHTTPConnectionParams(url=config.MCP_URL),
    tool_filter=["list_problems", "get_problem_spec"],
)

# Input guardrail runs before every model call (see guardrail.py). Attaching it
# on the agent means it protects every entry point (chat, adk web, adk run).
_before_model = [input_guardrail_callback] if config.GUARDRAIL_MODE != "off" else None

root_agent = LlmAgent(
    name="codejudge_assistant",
    model=config.GEN_MODEL,
    instruction=_INSTRUCTION,
    tools=[search_ingested_docs, _codejudge_mcp],
    sub_agents=[problem_author, adversarial_grader],
    before_model_callback=_before_model,
)
