"""The root agent (S4): the PoC assistant.

One LlmAgent with two kinds of tools:
- `search_ingested_docs` (RAG) — answers "how does CodeJudge work" from the
  ingested documentation.
- live tools over MCP (`list_problems`, `get_problem_spec`) — answer questions
  about the *actual* problems on a running CodeJudge, via codejudge-mcp.

The point of the PoC is that the model *chooses* per question which source to
use — that's real, model-driven tool selection across two genuinely different
sources (local docs vs. a live service), tied together by MCP and RAG.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import StreamableHTTPConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset

from .. import config
from .guardrail import input_guardrail_callback
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
    before_model_callback=_before_model,
)
