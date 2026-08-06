# How to run CodeJudge-AI

This project has a few moving parts, but **you rarely need all of them at once**.
This doc says what to start, in what order, and — importantly — *when you don't*
need to start something.

> **TL;DR for today (S3, RAG agent):** build the store once, then run the dev UI.
> That's it. You do **not** start the agent separately, and you do **not** need
> the MCP server or CodeJudge yet.

---

## The components (and when each is needed)

| Component | What it is | Needed now (S3)? |
|---|---|---|
| **Python AI** (`codejudge_ai`) | The RAG pipeline + the ADK agent | ✅ yes |
| **The agent** | Loaded *inside* the runner/dev UI — not a separate process | ✅ (auto, see below) |
| **Vector store** (`store.json`) | The searchable form of the docs; built by `ingest` | ✅ must exist first |
| **codejudge-mcp** (Go) | MCP server fronting CodeJudge's API | ❌ not until S4 |
| **CodeJudge** (sibling repo) | The actual online judge | ❌ not until S4 |

**Key point:** "starting the agent" is not a separate step. When you run the dev
UI (`adk web`), our own REPL (`chat`), or `adk run`, that command *is* the agent —
it loads `root_agent` and runs it in-process. There is no agent server to start.

---

## One-time setup

From the repo root (`CodeJudge-AI/`):

```bash
python -m venv .venv
.venv\Scripts\activate                 # Windows;  source .venv/bin/activate on POSIX
pip install -e ".[agent]"              # RAG pipeline + the ADK agent runtime
copy .env.example .env                 # then put your GEMINI_API_KEY in .env
```

(The examples below call the venv directly — `.venv/Scripts/adk`, `.venv/Scripts/python`
— so they work whether or not you've activated the venv.)

---

## Step 1 — Build the knowledge base (do this first, and after docs change)

The agent can't answer until the vector store exists. Two small steps:

```bash
# Copy CodeJudge's Markdown docs into ./corpus  (only READS CodeJudge; safe)
.venv/Scripts/python -m codejudge_ai.scripts.sync_docs

# Extract -> chunk -> embed -> save the store  (needs GEMINI_API_KEY)
.venv/Scripts/python -m codejudge_ai.scripts.ingest
```

Re-run both whenever the source docs change, or when you drop new PDFs/Word files
into `corpus/`. You only need to do this again when the *documents* change — not
every time you start the UI.

---

## Step 2 — Talk to the agent (pick ONE)

All three run the same agent; they differ only in interface.

**A) ADK web UI (what you're using) — richest view**
```bash
.venv/Scripts/adk web adk_app/codejudge_assistant
```
Open http://localhost:8000. The `codejudge_assistant` agent is auto-selected.
The side panel shows the event stream and every tool call, so you can watch the
RAG retrieval happen. **This is the whole thing running — nothing else to start.**

**B) ADK terminal REPL**
```bash
.venv/Scripts/adk run adk_app/codejudge_assistant
```

**C) Our own script (one-shot or interactive)**
```bash
.venv/Scripts/python -m codejudge_ai.scripts.chat "how are verdicts decided?"
.venv/Scripts/python -m codejudge_ai.scripts.chat        # interactive
```

---

## Running as a server (later)

You do **not** need to write FastAPI yourself — ADK *is* a FastAPI app. Three
levels, by how much control you want:

1. **Headless REST API** — same endpoints as the web UI (`/run`, `/run_sse`,
   session management), no browser UI:
   ```bash
   .venv/Scripts/adk api_server adk_app/codejudge_assistant --port 8000
   ```

2. **Customize / embed** — when you want your own routes, auth, CORS, or a
   *persistent* session store instead of in-memory. See [server.py](server.py)
   for a working example: it calls `get_fast_api_app(agents_dir="adk_app",
   web=True)` (all of ADK's endpoints + the dev UI) and adds a custom `/healthz`
   route with a plain FastAPI decorator. Run it and try the custom endpoint:
   ```bash
   .venv/Scripts/python server.py
   # http://localhost:8000/         dev UI
   # http://localhost:8000/healthz  our custom endpoint
   ```
   For a real deployment, pass `session_service_uri="postgresql://..."` for
   persistent sessions and `allow_origins=[...]` for CORS.

3. **Managed hosting** — ADK containerizes and deploys the server for you:
   ```bash
   .venv/Scripts/adk deploy cloud_run adk_app/codejudge_assistant   # or agent_engine / gke
   ```

You'd only hand-write FastAPI from scratch for a fully custom API contract — then
you'd wrap the ADK `Runner` (as `codejudge_ai/scripts/chat.py` does) in your own
endpoints. Usually unnecessary. Note: a real server should use a persistent
session service (via `session_service_uri`) rather than the dev default, and by
then you'll also be running the MCP server + CodeJudge (below).

---

## Later: MCP + CodeJudge (S4 onward — not needed yet)

Once the agent gains the live-lookup tool, you'll also start the MCP server, and
it will need CodeJudge running. Recorded here so it's ready when we get there:

```bash
# terminal 1 - CodeJudge (its own repo; we only ever READ it)
#   run per CodeJudge's own instructions, exposes http://localhost:8080

# terminal 2 - the MCP server (fronts CodeJudge for the agent)
cd mcp/codejudge-mcp
go run ./cmd/server            # listens on :8081, talks to CodeJudge at :8080

# terminal 3 - the agent (as in Step 2); it will call the MCP over HTTP
```

Until S4, skip this whole section.
