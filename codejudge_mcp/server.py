"""The MCP server: a FastMCP instance plus the tools it exposes.

Each tool is a thin adapter — decode the model's arguments, call the CodeJudge
client, and return a structured result the agent can reason over. Errors are
returned as data (an "error" field) rather than raised, so the model can react
(e.g. try a different id) instead of seeing a transport failure.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import config
from .codejudge_client import CodeJudgeError, get_problem

mcp = FastMCP(
    "codejudge-mcp",
    host=config.MCP_HOST,
    port=config.MCP_PORT,
    streamable_http_path=config.MCP_PATH,
)


@mcp.tool()
async def get_problem_spec(problem_id: str) -> dict:
    """Look up one CodeJudge problem's public spec.

    Returns its grading mode, function signature/entry point, resource limits,
    and sample (visible) test cases. Use this to answer questions about a
    specific existing problem instead of guessing.

    Args:
        problem_id: The id of the problem to look up, e.g. "two-sum".
    """
    if not problem_id:
        return {"error": "problem_id is required"}
    try:
        data = await get_problem(problem_id)
    except CodeJudgeError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # network/timeout: surface to the model as data
        return {"error": f"could not reach CodeJudge: {exc}"}

    return {
        "id": data.get("id"),
        "mode": data.get("mode"),
        "signature": data.get("signature"),
        "entryFunc": data.get("entryFunc"),
        "limits": data.get("limits"),
        "sampleCases": data.get("sampleCases", []),
    }
