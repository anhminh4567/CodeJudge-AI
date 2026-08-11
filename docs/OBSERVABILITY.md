# Observability

How to see — and extend — what the agent is doing. Code:
[`codejudge_ai/agent/observability.py`](../codejudge_ai/agent/observability.py).

## What ADK gives you for free

The **Runner** drives the agent loop (model call → tool calls → model call → …)
and emits an **`Event`** for every step. Everything the dev UI shows is built on
that:

- **Streaming** — `run_async` yields Events as they happen; the web UI subscribes
  over SSE, and our `chat.py` prints tool calls/answers from the same stream.
- **Tracing** — ADK instruments itself with **OpenTelemetry** (`google.adk.
  telemetry`), emitting spans for the run, each LLM call, and each tool call.
  The dev UI's Trace tab renders those spans.
- **Logging** — plain Python logging on the `google_adk.*` loggers.

So the framework already handles streaming/tracing/logging. What you add are your
own hooks at four seams.

## The four seams (easiest → deepest)

1. **Per-agent callbacks** — `before/after_model_callback`, `before/after_tool_callback`,
   error callbacks on the `LlmAgent`. Fire around one agent's steps; a `before_*`
   can return a value to *override/short-circuit* the step. The
   [guardrail](GUARDRAIL.md) is a `before_model_callback`.
2. **Plugins** — a `BasePlugin` with the same hooks, registered on the **Runner**,
   so they apply across *all* agents/tools. Our `LoggingPlugin` logs run/model/
   tool lifecycles with timings and token counts. This is the global seam.
3. **OpenTelemetry exporters** — ADK already emits spans; attach your own exporter
   to send them anywhere. `enable_console_tracing()` adds a `ConsoleSpanExporter`
   so the same spans the dashboard shows also print in your terminal. Swap in an
   OTLP exporter to ship them to Jaeger/Tempo/Cloud Trace.
4. **Plain logging** — set levels / add handlers on any logger, or wrap a tool.

## Turning it on

Both the plugin and the console tracer are opt-in, so normal runs stay quiet:

```bash
CODEJUDGE_AI_TRACE=1 python -m codejudge_ai.scripts.chat "how are verdicts classified?"
```

You'll see the plugin's lifecycle logs (e.g. `← model reply (3616 ms) tokens=960`,
per-tool timings) interleaved with OpenTelemetry spans (`execute_tool …`,
`generate_content …`, `call_llm`). In `adk web`, the dashboard already renders all
of this, so the flag mainly helps the terminal REPL.

## Notes

- `LoggingPlugin` only *observes* — every hook returns `None`. Returning a value
  from a plugin hook is how you'd override a request/response/result; we don't.
- Timings work by recording a start time in a `before_*` hook and reading it back
  in the matching `after_*` hook (they're separate calls).

## How `enable_console_tracing()` actually captures ADK's spans

If you've used OpenTelemetry in C#/Java, the mental model transfers directly:
**one global `TracerProvider` singleton**, and you attach exporters/processors to
it (`Sdk.CreateTracerProviderBuilder()` in .NET, `GlobalOpenTelemetry.set(...)` in
Java — same shape in Python). `enable_console_tracing()` builds a `TracerProvider`,
attaches a `ConsoleSpanExporter`, and calls `trace.set_tracer_provider(...)` to
register it globally.

**Is this overriding ADK's own exporter?** No — in the codepath we use (`chat.py`),
ADK never registers a provider in the first place. Looking at ADK's source,
`google/adk/telemetry/tracing.py` only calls `trace.get_tracer(...)` — it's a span
*producer*, not a provider *owner*. The only place ADK itself calls
`set_tracer_provider(...)` is `cli/api_server.py` (wiring spans into the dev UI's
Trace tab / OTLP env vars when you run `adk web`), which is a different process
from our `chat.py`. So we're not overriding anything — we're filling an otherwise
empty slot.

**Then how does it capture ADK's spans, when ADK created its tracer *before* we
call `enable_console_tracing()`?** Because `trace.get_tracer(...)` doesn't return a
tracer bound to a concrete provider — it returns a **lazy proxy**. Every time code
calls `tracer.start_as_current_span(...)`, that proxy looks up *whichever provider
is currently globally registered at that exact moment*, not whatever was
registered when the tracer object was created. Proven directly:

```python
# 1. simulate ADK's import-time behavior: get a tracer before any provider exists
early_tracer = trace.get_tracer("simulated.adk.module")

# 2. register a real provider LATER (what enable_console_tracing() does)
trace.set_tracer_provider(provider_with_console_exporter)

# 3. use the OLD tracer object
with early_tracer.start_as_current_span("proves-the-proxy-mechanism"):
    pass
# -> the console exporter DOES print this span
```

ADK's `tracer` module-level variable is created at import time, but real spans
only fire later, when a request actually runs — and `enable_console_tracing()`
runs in between (inside `chat.py`'s `_build_runner()`), so by the time any span
starts, our provider is already the registered one.

**The gotcha:** calling `set_tracer_provider(...)` a *second time in the same
process* is a silent no-op that logs a warning
(`"Overriding of current TracerProvider is not allowed"`) — first-registered-wins,
for the lifetime of that process. This doesn't bite us today (`enable_console_tracing()`
is only called from `chat.py`, never from `server.py`/`adk web`, which are separate
processes with their own provider setup) — but if you ever call it *inside*
`server.py` (which uses `get_fast_api_app`, and ADK's own api-server code sets a
provider there for the dashboard), your console exporter would silently lose that
race. Whoever calls `set_tracer_provider()` first in a process wins, full stop.

Related: [GUARDRAIL.md](GUARDRAIL.md), [ARCHITECTURE.md](ARCHITECTURE.md).
