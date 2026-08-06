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

# ADK builds the FastAPI app for us: point it at the agents directory, keep the
# dev UI on, and (for a real deployment) swap in a persistent session store via
# session_service_uri instead of the in-memory default.
app = get_fast_api_app(
    agents_dir="adk_app",
    web=True,
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
