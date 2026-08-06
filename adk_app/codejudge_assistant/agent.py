"""ADK dev-UI entry point for the CodeJudge assistant.

`adk web`/`adk run` discover an agent by importing an agent folder's `agent.py`
and reading its `root_agent`. Our real agent lives in the `codejudge_ai` package
and uses package-relative imports that only resolve inside that package, so this
thin module re-exports it via an absolute import (works because codejudge_ai is
pip-installed with `-e`).

Run from the repo root:
    adk web adk_app/codejudge_assistant     # web UI at http://localhost:8000
    adk run adk_app/codejudge_assistant      # ADK's own terminal REPL
"""

from codejudge_ai.agent.root_agent import root_agent

__all__ = ["root_agent"]
