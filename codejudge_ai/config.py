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
STORE_DIR = Path(os.getenv("CODEJUDGE_AI_STORE_DIR", PACKAGE_DIR / "rag" / "store"))

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
GEN_MODEL = os.getenv("CODEJUDGE_AI_GEN_MODEL", "gemini-2.5-flash")

# ADK (google-adk) builds its own genai client from environment variables rather
# than an explicit key. Mirror our key into the name it reads so the agent "just
# works" with the single GEMINI_API_KEY the rest of the project uses. With an API
# key present, google-genai defaults to the AI Studio backend (not Vertex), which
# is what we want, so we don't set any Vertex flag.
if GEMINI_API_KEY and not os.getenv("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = GEMINI_API_KEY

# codejudge-mcp endpoint (Streamable HTTP) for the agent's live tools.
MCP_URL = os.getenv("CODEJUDGE_MCP_URL", "http://localhost:8081/")

# Chunking parameters (characters, not tokens — a simple, predictable proxy).
CHUNK_SIZE = int(os.getenv("CODEJUDGE_AI_CHUNK_SIZE", "1200"))
CHUNK_OVERLAP = int(os.getenv("CODEJUDGE_AI_CHUNK_OVERLAP", "200"))

# Default number of chunks retrieved per query.
TOP_K = int(os.getenv("CODEJUDGE_AI_TOP_K", "4"))
