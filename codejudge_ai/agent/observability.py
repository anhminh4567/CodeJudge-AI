"""Observability playground — make ADK's hidden machinery visible.

ADK already handles streaming, tracing (OpenTelemetry) and logging natively; the
dev UI is built on that. This module shows the two seams for adding your *own*:

1. `LoggingPlugin` — a `BasePlugin` whose hooks fire around every run / model
   call / tool call, across all agents. Register it on the Runner. This is the
   global, cross-cutting seam.
2. `enable_console_tracing()` — installs an OpenTelemetry ConsoleSpanExporter so
   the same spans the dashboard shows also print to your terminal. This is the
   tracing seam: ADK emits the spans, you choose where they go.

(The third seam, per-agent callbacks, is used in `guardrail.py`.)

Both are opt-in (CODEJUDGE_AI_TRACE=1) so normal runs stay quiet.
"""

from __future__ import annotations

import logging
import time

from google.adk.plugins.base_plugin import BasePlugin

logger = logging.getLogger("codejudge_ai.observability")

_TRACING_INSTALLED = False


class LoggingPlugin(BasePlugin):
    """Logs the lifecycle of every run, model call, and tool call, with timings.

    A "plugin" is ADK's *global* observability seam: the Runner calls these hooks
    around each step of every agent it runs. The `before_*` hook of a step and
    its `after_*` hook are separate calls, so to time a step we record its start
    time in `_step_start_times` (keyed per step) and read it back in the `after_*`
    hook. Every hook returns None — this plugin only *observes*; it never alters
    the request, response, or result (returning a value from these hooks is how a
    plugin would override them, which we intentionally don't do here).
    """

    def __init__(self) -> None:
        super().__init__(name="logging")
        # Start timestamps for in-flight steps, so an after_* hook can compute a
        # duration. Keyed "model" for the single in-flight model call, and by the
        # tool-call context id for concurrent tool calls.
        self._step_start_times: dict[object, float] = {}

    # --- run: one top-level agent invocation (a whole user turn) ---
    async def before_run_callback(self, *, invocation_context):
        logger.info("run start (agent=%s)", invocation_context.agent.name)
        return None

    async def after_run_callback(self, *, invocation_context):
        logger.info("run end")
        return None

    # --- model: one LLM request/response (there can be several per run) ---
    async def before_model_callback(self, *, callback_context, llm_request):
        self._step_start_times["model"] = time.perf_counter()
        logger.info("→ model call")
        return None

    async def after_model_callback(self, *, callback_context, llm_response):
        started = self._step_start_times.pop("model", time.perf_counter())
        elapsed_ms = (time.perf_counter() - started) * 1000
        usage = getattr(llm_response, "usage_metadata", None)
        token_note = f" tokens={usage.total_token_count}" if usage else ""
        logger.info("← model reply (%.0f ms)%s", elapsed_ms, token_note)
        return None

    # --- tool: one tool invocation the model requested ---
    async def before_tool_callback(self, *, tool, tool_args, tool_context):
        self._step_start_times[id(tool_context)] = time.perf_counter()
        logger.info("→ tool %s args=%s", tool.name, tool_args)
        return None

    async def after_tool_callback(self, *, tool, tool_args, tool_context, result):
        started = self._step_start_times.pop(id(tool_context), time.perf_counter())
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info("← tool %s done (%.0f ms)", tool.name, elapsed_ms)
        return None

    async def on_tool_error_callback(self, *, tool, tool_args, tool_context, error):
        self._step_start_times.pop(id(tool_context), None)
        logger.warning("tool %s errored: %s", tool.name, error)
        return None

    # --- event: every Event the runner emits (partial text, function calls,
    # function responses, final answer). This is the raw stream the dev UI and
    # our chat REPL both consume; logged at debug so it doesn't drown the rest. ---
    async def on_event_callback(self, *, invocation_context, event):
        logger.debug("event author=%s final=%s", event.author, event.is_final_response())
        return None


def enable_console_tracing() -> None:
    """Route ADK's OpenTelemetry spans to the console (idempotent).

    ADK emits spans for the agent run, each LLM call and each tool call. We just
    attach a ConsoleSpanExporter so they print locally — the same data the dev
    UI's Trace tab renders, in your terminal.
    """
    global _TRACING_INSTALLED
    if _TRACING_INSTALLED:
        return
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    _TRACING_INSTALLED = True
    logger.info("console OpenTelemetry tracing enabled")
