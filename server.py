"""Example custom server for the CodeJudge assistant.

Shows how to run the agent as a real HTTP server AND add your own endpoints.
`get_fast_api_app(...)` hands back a standard FastAPI app with all of ADK's
routes (/run, /run_sse, sessions, and — with web=True — the dev UI), and you
extend it with plain FastAPI route decorators. You are NOT writing the agent
server from scratch; you're adding to ADK's.

Run from the repo root:
    .venv/Scripts/python server.py
    # then: http://localhost:8000/        (dev UI)
    #       http://localhost:8000/healthz  (our custom endpoint)
    #       http://localhost:8000/list-apps

Configure via env: HOST (default 0.0.0.0), PORT (default 8000).
"""

from __future__ import annotations

import os

import uvicorn
from google.adk.cli.fast_api import get_fast_api_app

from codejudge_ai import config

# ADK builds the FastAPI app for us: point it at the agents directory, keep the
# dev UI on, and use a persistent session store when CODEJUDGE_AI_SESSION_DB_URL
# is set (see docs/RUNNING.md) instead of ADK's in-memory default.
# allow_origins wires ADK's CORS middleware -- without it a browser client on a
# different origin (CodeJudge-UI's chat panel) can't call this API at all.
app = get_fast_api_app(
    agents_dir="adk_app",
    web=True,
    session_service_uri=config.SESSION_DB_URL or None,
    allow_origins=config.CORS_ORIGINS,
)


# --- our own endpoints: just standard FastAPI route decorators ---
@app.get("/healthz")
def healthz() -> dict:
    """Liveness probe. Add your own routes the same way."""
    return {"status": "ok", "service": "codejudge-ai"}


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
    )
