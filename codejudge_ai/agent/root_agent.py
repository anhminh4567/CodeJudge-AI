"""The root agent (S3): a RAG-only CodeJudge assistant.

One LlmAgent with a single tool, `search_ingested_docs`. The model decides when
to call it; the instruction keeps it grounded — answer from retrieved passages,
cite sources, and admit when the docs don't cover something. In S4 a second tool
(live problem lookup via codejudge-mcp) joins it so the model must *choose*
between sources — that's the PoC milestone.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

from .. import config
from .tools import search_ingested_docs

_INSTRUCTION = """\
You are the CodeJudge assistant. You help visitors understand the CodeJudge
online judge (an API-driven system that runs submitted code in a sandbox and
returns a verdict).

How to answer:
- For any factual question about how CodeJudge works, FIRST call
  `search_ingested_docs` with a focused query, then answer from what it returns.
  Do not answer such questions from prior knowledge.
- Ground every claim in the retrieved passages. Cite the source document(s) you
  used, e.g. "(source: WARM_POOL.md)".
- If the retrieved passages don't contain the answer, say so plainly instead of
  guessing. You may suggest what to search for instead.
- Keep answers concise and concrete. Prefer specifics from the docs over
  generalities.
"""

root_agent = LlmAgent(
    name="codejudge_assistant",
    model=config.GEN_MODEL,
    instruction=_INSTRUCTION,
    tools=[search_ingested_docs],
)
