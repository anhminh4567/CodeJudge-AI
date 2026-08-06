"""Run the MCP server over Streamable HTTP.

    python -m codejudge_mcp

Listens on http://{MCP_HOST}:{MCP_PORT}{MCP_PATH} (default
http://127.0.0.1:8081/mcp). It starts even if CodeJudge is down; tools report
per-call errors until CodeJudge is reachable.
"""

from __future__ import annotations

from .server import mcp


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
