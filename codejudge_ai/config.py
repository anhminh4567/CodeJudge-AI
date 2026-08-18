"""Central configuration for codejudge-ai.

Everything tunable lives here and is overridable by environment variables so the
same code runs locally and in a container. `.env` is loaded automatically for
local development (see `.env.example`).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # no-op if there is no .env; real env vars still win

# Repo paths. `PACKAGE_DIR` is .../CodeJudge-AI/codejudge_ai; `PROJECT_DIR` is
# the repo root .../CodeJudge-AI. Data lives under the project dir, not the
# package, so it is easy to gitignore and never shipped inside the package.
PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent

# Where synced/ingested source documents live (S1 copies CodeJudge docs here).
CORPUS_DIR = Path(os.getenv("CODEJUDGE_AI_CORPUS_DIR", PROJECT_DIR / "corpus"))

# Where the flat-file vector store is written (S2 ingest output).
STORE_DIR = Path(os.getenv("CODEJUDGE_AI_STORE_DIR",
                 PACKAGE_DIR / "rag" / "store"))

# Source of CodeJudge markdown docs for the sync script (S1). CodeJudge is a
# sibling of this repo and READ-ONLY to this project; the sync script only ever
# reads from here.
CODEJUDGE_DOCS_DIR = Path(
    os.getenv(
        "CODEJUDGE_DOCS_DIR",
        PROJECT_DIR.parent / "CodeJudge" / "docs",
    )
)

# Gemini / genai.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
EMBED_MODEL = os.getenv("CODEJUDGE_AI_EMBED_MODEL", "gemini-embedding-001")
# Use the "-latest" alias so we track the current Flash model; pinned versions
# like gemini-2.5-flash get retired and start returning 404 for new users.
GEN_MODEL = os.getenv("CODEJUDGE_AI_GEN_MODEL", "gemini-flash-latest")
# Model for the problem_author sub-agent specifically. Defaults to GEN_MODEL
# (no cost change out of the box), but authoring is a longer multi-step
# tool-orchestration task than simple Q&A -- approval for mutating tools is
# enforced only by the instruction (ask, then wait for a "yes"), so a
# cheap/Lite model can skip the ask and call a mutating tool immediately (see
# docs/PROBLEM_AUTHORING.md). Set this to a stronger model if that happens.
AUTHOR_MODEL = os.getenv("CODEJUDGE_AI_AUTHOR_MODEL", GEN_MODEL)

# Model for the adversarial_grader sub-agent. Defaults to GEN_MODEL, same
# convention as AUTHOR_MODEL. Every tool here is read-only, so a weak model's
# failure mode is worse adversarial cases, not an unauthorized write.
ADVERSARIAL_MODEL = os.getenv("CODEJUDGE_AI_ADVERSARIAL_MODEL", GEN_MODEL)

# ADK (google-adk) builds its own genai client from environment variables rather
# than an explicit key. Mirror our key into the name it reads so the agent "just
# works" with the single GEMINI_API_KEY the rest of the project uses. With an API
# key present, google-genai defaults to the AI Studio backend (not Vertex), which
# is what we want, so we don't set any Vertex flag.
if GEMINI_API_KEY and not os.getenv("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = GEMINI_API_KEY

# codejudge-mcp endpoint (Streamable HTTP) for the agent's live tools. FastMCP
# serves at the /mcp path by default.
MCP_URL = os.getenv("CODEJUDGE_MCP_URL", "http://localhost:8081/mcp")

# Chunking parameters (characters, not tokens — a simple, predictable proxy).
CHUNK_SIZE = int(os.getenv("CODEJUDGE_AI_CHUNK_SIZE", "1200"))
CHUNK_OVERLAP = int(os.getenv("CODEJUDGE_AI_CHUNK_OVERLAP", "200"))

# Default number of chunks retrieved per query.
TOP_K = int(os.getenv("CODEJUDGE_AI_TOP_K", "4"))

# Drop retrieved chunks below this cosine score, so weak/irrelevant matches don't
# get fed to the model (it should say "not in the docs" instead of grasping).
# NOTE: gemini-embedding-001 has a high similarity baseline on this corpus —
# unrelated queries still score ~0.50, while on-topic hits are ~0.65+. So the
# threshold sits at 0.6 to separate them. It's a heuristic; tune per corpus/model.
MIN_SCORE = float(os.getenv("CODEJUDGE_AI_MIN_SCORE", "0.6"))


def _envbool(key: str, default: bool) -> bool:
    v = os.getenv(key)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


# Input guardrail: screens each user message before the model runs. Modes:
#   "off"       - no screening
#   "heuristic" - fast, deterministic checks (length + a few obvious patterns);
#                 cheap but limited/bypassable
#   "llm"        - a model classifies each message (more robust, adds one call
#                 per user turn)
# See docs/GUARDRAIL.md for the trade-offs. Legacy 0/1/true/false still map to
# off/heuristic.
_GUARDRAIL_RAW = os.getenv("CODEJUDGE_AI_GUARDRAIL",
                           "heuristic").strip().lower()
GUARDRAIL_MODE = {
    "0": "off", "false": "off", "no": "off", "none": "off", "off": "off",
    "1": "heuristic", "true": "heuristic", "yes": "heuristic", "on": "heuristic", "heuristic": "heuristic",
    "llm": "llm",
}.get(_GUARDRAIL_RAW, "heuristic")

# Verbose observability for the local chat REPL: logs each tool/model call and
# prints OpenTelemetry spans to the console. Off by default (opt-in for learning).
TRACE_ENABLED = _envbool("CODEJUDGE_AI_TRACE", False)

# Persistent ADK session storage (dev/debugging only) -- a SQLAlchemy async URL,
# e.g. postgresql+asyncpg://user:pass@host:port/dbname. Empty means ADK's
# in-memory default (sessions lost on every restart). Needs the "persist" extra
# (pip install -e ".[agent,persist]") for the driver. Used by
# scripts/web.py and server.py; see docs/RUNNING.md.
SESSION_DB_URL = os.getenv("CODEJUDGE_AI_SESSION_DB_URL", "")
