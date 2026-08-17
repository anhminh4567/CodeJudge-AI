"""Launch `adk web`, wiring in persistent session storage if configured.

The `adk` CLI is a separate process from our own code and does not read our
`.env` -- `--session_service_uri` has to be passed on its command line. This
script is that wiring: it reads `config.SESSION_DB_URL` (from
CODEJUDGE_AI_SESSION_DB_URL) and passes it through automatically, so "does this
project use Postgres for sessions" has a real, runnable answer in the codebase
instead of a URL that only lives in `.env` and gets typed into ad-hoc commands.

Usage:
    python -m codejudge_ai.scripts.web                # picks up SESSION_DB_URL if set
    python -m codejudge_ai.scripts.web --port 8010
    python -m codejudge_ai.scripts.web --no-persist    # force in-memory even if SESSION_DB_URL is set
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from .. import config

AGENT_DIR = config.PROJECT_DIR / "adk_app" / "codejudge_assistant"


def _find_adk() -> str:
    """Locate the `adk` console script. Check next to the running interpreter
    first -- that's where pip installs it in a venv, which may not be on PATH
    if the venv wasn't "activated" (e.g. invoked as .venv/Scripts/python.exe
    directly) -- then fall back to PATH."""
    bin_dir = Path(sys.executable).parent
    for name in ("adk.exe", "adk"):
        candidate = bin_dir / name
        if candidate.exists():
            return str(candidate)
    found = shutil.which("adk")
    if not found:
        raise SystemExit("`adk` not found -- is the [agent] extra installed? (pip install -e '.[agent]')")
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--no-persist",
        action="store_true",
        help="ignore CODEJUDGE_AI_SESSION_DB_URL and use ADK's in-memory default",
    )
    args = parser.parse_args()

    cmd = [_find_adk(), "web", str(AGENT_DIR), "--port", str(args.port)]

    if config.SESSION_DB_URL and not args.no_persist:
        cmd.append(f"--session_service_uri={config.SESSION_DB_URL}")
        print(f"Using persistent session storage: {config.SESSION_DB_URL}", flush=True)
    else:
        print("Using ADK's default in-memory session storage (lost on restart). "
              "Set CODEJUDGE_AI_SESSION_DB_URL in .env for persistence -- see docs/RUNNING.md.",
              flush=True)

    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
