"""Configuration for the MCP server (env-driven, same style as codejudge_ai)."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()  # share the repo-root .env; real env vars still win

# Base URL of the running CodeJudge API this server fronts.
CODEJUDGE_BASE_URL = os.getenv("CODEJUDGE_BASE_URL", "http://localhost:8080").rstrip("/")

# Where this MCP server listens (Streamable HTTP). The agent connects to
# http://{MCP_HOST}:{MCP_PORT}{MCP_PATH}.
MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("MCP_PORT", "8081"))
MCP_PATH = os.getenv("MCP_PATH", "/mcp")
