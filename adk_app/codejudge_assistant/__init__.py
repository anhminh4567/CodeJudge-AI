"""ADK dev-UI launcher package for the CodeJudge assistant.

Follows ADK's convention: `__init__.py` imports the `agent` submodule so the
loader can find `root_agent`. The actual agent is defined in `codejudge_ai`;
`agent.py` here just re-exports it. See agent.py for run commands.
"""

from . import agent
from .agent import root_agent

__all__ = ["agent", "root_agent"]
