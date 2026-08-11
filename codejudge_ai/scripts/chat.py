"""S3 - Chat with the RAG assistant locally via ADK's InMemoryRunner.

No server or deployment needed: this spins up the agent in-process and gives you
a terminal REPL. It shows when the agent calls a tool, so you can see the RAG
retrieval happening.

Usage:
    python -m codejudge_ai.scripts.chat                 # interactive REPL
    python -m codejudge_ai.scripts.chat "your question" # one-shot, then exit
"""

from __future__ import annotations

import asyncio
import logging
import sys
import warnings

# Keep the REPL readable: hide library-internal deprecation/experimental warnings
# and the google-genai "both keys set" info line. This only affects this
# user-facing entry point, not the library code.
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)
logging.getLogger("google_genai").setLevel(logging.ERROR)
# ADK logs a spurious mTLS/ADC warning on every MCP connection (we use API-key
# auth, so mTLS never applies). Silence ADK warnings; real errors still show.
logging.getLogger("google_adk").setLevel(logging.ERROR)

from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

from .. import config  # noqa: E402
from ..agent.observability import LoggingPlugin, enable_console_tracing  # noqa: E402
from ..agent.root_agent import root_agent  # noqa: E402

APP_NAME = "codejudge_ai"
USER_ID = "local"


def _build_runner() -> InMemoryRunner:
    """InMemoryRunner, with the observability plugin + console tracing when
    CODEJUDGE_AI_TRACE=1 (see agent/observability.py)."""
    if not config.TRACE_ENABLED:
        return InMemoryRunner(agent=root_agent, app_name=APP_NAME)
    logging.getLogger("codejudge_ai").setLevel(logging.INFO)
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    enable_console_tracing()
    return InMemoryRunner(agent=root_agent, app_name=APP_NAME, plugins=[LoggingPlugin()])


async def ask(runner: InMemoryRunner, session_id: str, query: str) -> None:
    """Send one message and stream the agent's tool calls + final answer."""
    message = types.Content(role="user", parts=[types.Part(text=query)])
    async for event in runner.run_async(
        user_id=USER_ID, session_id=session_id, new_message=message
    ):
        for part in (event.content.parts if event.content and event.content.parts else []):
            if part.function_call:
                args = dict(part.function_call.args or {})
                print(f"  [tool call] {part.function_call.name}({args})")
            elif part.function_response:
                results = (part.function_response.response or {}).get("results", [])
                print(f"  [tool result] {len(results)} passage(s)")
        if event.is_final_response() and event.content and event.content.parts:
            text = "".join(p.text or "" for p in event.content.parts)
            print(f"\nbot> {text}")


async def main() -> None:
    runner = _build_runner()
    session = await runner.session_service.create_session(app_name=APP_NAME, user_id=USER_ID)

    one_shot = " ".join(sys.argv[1:]).strip()
    if one_shot:
        print(f"you> {one_shot}")
        await ask(runner, session.id, one_shot)
        return

    print("CodeJudge assistant (RAG only). Type 'exit' or 'quit' to leave.")
    while True:
        try:
            query = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if query.lower() in {"exit", "quit"}:
            break
        if query:
            await ask(runner, session.id, query)


if __name__ == "__main__":
    asyncio.run(main())
