# How to run CodeJudge-AI

This project has a few moving parts, but **you rarely need all of them at once**.
This doc says what to start, in what order, and — importantly — *when you don't*
need to start something.

> **TL;DR:** build the store once. For doc Q&A, just run the dev UI. For the
> agent's *live problem* tools, also run the MCP server (`python -m codejudge_mcp`)
> — and start CodeJudge too if you want real problem data. The agent still runs
> if the MCP server is down; it just can't answer live-problem questions.

---

## The components (and when each is needed)

| Component | What it is | When needed |
|---|---|---|
| **Python AI** (`codejudge_ai`) | The RAG pipeline + the ADK agent | always |
| **The agent** | Loaded *inside* the runner/dev UI — not a separate process | always (auto, see below) |
| **Vector store** (`store.json`) | The searchable form of the docs; built by `ingest` | always — must exist first |
| **codejudge_mcp** (Python) | MCP server for the agent's live tools (`list_problems`, `get_problem_spec`) | for live-problem questions |
| **CodeJudge** (sibling repo) | The actual online judge | for real problem *data* (else live tools return an error) |

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
.venv/Scripts/python -m codejudge_ai.scripts.web
```
Open http://localhost:8000. The `codejudge_assistant` agent is auto-selected.
The side panel shows the event stream and every tool call, so you can watch the
RAG retrieval happen. **This is the whole thing running — nothing else to start.**

`scripts/web.py` is a thin wrapper around `adk web` (the `adk` CLI is a separate
process and doesn't read our `.env` on its own): it reads
`CODEJUDGE_AI_SESSION_DB_URL` from `config.py` and passes it through as
`--session_service_uri` automatically, so persistence is picked up without
retyping a URL by hand. It prints which storage it picked. `--no-persist`
forces in-memory even if the URL is set; `python -m codejudge_ai.scripts.web
--port 8010` changes the port. (You can still run `adk web
adk_app/codejudge_assistant` directly if you don't want persistence.)

Without `CODEJUDGE_AI_SESSION_DB_URL` set, sessions are **in-memory** — every
restart of the server loses all conversation history, which makes debugging a
multi-turn conversation painful. To set it up:
```bash
pip install -e ".[agent,persist]"   # once: adds sqlalchemy + asyncpg
```
```
# .env
CODEJUDGE_AI_SESSION_DB_URL=postgresql+asyncpg://user:pass@host:port/dbname
```
Use a **dedicated** database for this — not CodeJudge's own — to keep the two
unrelated. SQLite (`sqlite+aiosqlite:///./sessions.db`, needs `aiosqlite`
instead of `asyncpg`) is a zero-infrastructure alternative if you don't have a
Postgres server handy — same benefit, one local file instead of a server.
`server.py` (the custom FastAPI example) also reads this same var.

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
   *persistent* session store instead of in-memory. See [server.py](../server.py)
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

## Step 3 — Live problem tools (S4): the MCP server + CodeJudge

The agent has live tools (`list_problems`, `get_problem_spec`) that reach a
running CodeJudge through the MCP server. To use them, run three processes:

```bash
# terminal 1 - CodeJudge (its own repo; we only ever READ it)
#   run per CodeJudge's own instructions, exposes http://localhost:8080

# terminal 2 - the MCP server (fronts CodeJudge for the agent)
.venv/Scripts/python -m codejudge_mcp    # serves http://127.0.0.1:8081/mcp, talks to CodeJudge :8080

# terminal 3 - the agent (as in Step 2); it calls the MCP server over HTTP
```

Then ask the agent things like *"what problems are available?"* or *"show me the
spec for problem two-sum"* — it routes those to the live tools, and doc questions
("how does the sandbox work?") to RAG.

Notes:
- **MCP server down?** The agent still runs and answers doc (RAG) questions; live
  tools just report they can't connect.
- **CodeJudge down (MCP up)?** Live tools return a clear "CodeJudge unreachable"
  message, which the agent relays — it won't invent problem data.
- The agent finds the MCP server via `CODEJUDGE_MCP_URL` (default
  `http://localhost:8081/mcp`).
