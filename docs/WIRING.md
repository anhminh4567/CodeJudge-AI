# How it all wires together

ADK hides a lot, which makes it unclear *what runs when* and *how the agent gets
found*. This doc demystifies it. There are two separate mechanisms — keep them
apart and it stops feeling magic.

## 1. Our own code: plain Python imports (no magic)

`config.py` is a normal module. It is **not** auto-discovered or injected — it
runs because other modules **import** it, and importing a module executes its
top-level code exactly once (Python then caches it in `sys.modules`).

- `codejudge_ai/agent/root_agent.py` really does reference it:
  ```python
  from .. import config           # runs config.py's top level (incl. load_dotenv())
  ...
  model=config.GEN_MODEL, instruction=_INSTRUCTION, tools=[...]
  ```
  You don't "call" config — reading `config.GEN_MODEL` is just attribute access on
  the imported module. `.env` is loaded as a **side effect** of that first import
  (config.py calls `load_dotenv()` at module top level).

- One import at the entry point pulls the whole graph. For the chat REPL:
  ```
  scripts/chat.py
    └─ import agent.root_agent
         ├─ import config            → load_dotenv(), read env → module constants
         ├─ import agent.guardrail   → (its own imports)
         └─ import agent.tools
              └─ import rag.search → rag.store → rag.embed → config (cached)
  ```
  Each module's top-level code runs once, in import order. That's the entire
  "how does config load" story — no framework involved.

## 2. How the agent gets found: two paths

**a) Explicit (no magic).** `scripts/chat.py` and `server.py` name the agent
directly:
```python
from ..agent.root_agent import root_agent
runner = InMemoryRunner(agent=root_agent, app_name="codejudge_ai")
```
Nothing is discovered; we hand ADK the object.

**b) Convention (this is the "magic").** `adk web` / `adk run <path>` are given a
*folder*, not an object. ADK looks inside for an agent **by convention**:

- a submodule `agent.py`, or an `__init__.py`, or a `root_agent.yaml`, that
- exposes a module-level variable named exactly **`root_agent`**.

That's why `adk_app/codejudge_assistant/` exists and is tiny:
```python
# adk_app/codejudge_assistant/agent.py
from codejudge_ai.agent.root_agent import root_agent   # re-export under the name ADK expects
```
ADK imports that folder as a module and reads `root_agent` from it. The folder
name becomes the app name in the dev UI. So the "magic" is just: **scan a folder,
import it, read a variable of a fixed name.** (`agent.py` and `root_agent` are the
convention — see the `adk web --help` text and `AgentLoader`.)

## 3. What runs at request time (control flow)

Once a Runner has the agent, a turn flows like this (callbacks/plugins in *italics*):

```
user message
  → Runner.run_async(...)
     → *before_model_callback*  (our input guardrail — may short-circuit here)
     → model call (Gemini)
          ↳ returns text  ────────────────► final answer
          ↳ or returns function_call(s):
               → *before_tool_callback*
               → tool runs (search_ingested_docs / MCP tool)
               → *after_tool_callback*
               → model call again, now with the tool results
                 (loop until the model returns a final text answer)
  → Event stream (partial text, function calls/responses, final) ──► chat REPL / dev UI
```

- The agent's `model`, `instruction`, `tools`, and `before_model_callback`
  (guardrail) were fixed when `root_agent` was **constructed** (import time,
  step 1). At request time the Runner just drives the loop and fires the hooks.
- **Plugins** (e.g. `LoggingPlugin`) are registered on the *Runner* and fire the
  same hook points globally. See [OBSERVABILITY.md](OBSERVABILITY.md).
- The **guardrail** is a per-agent `before_model_callback`. See [GUARDRAIL.md](GUARDRAIL.md).

## TL;DR

- `config` loads because `root_agent` imports it; module top-level code runs on
  first import. No auto-magic.
- `adk web`/`adk run` find the agent by **convention** (`agent.py` exposing
  `root_agent`); `chat.py`/`server.py` reference it **explicitly**.
- At runtime the Runner drives model↔tool loops and fires callbacks/plugins at
  fixed points.
