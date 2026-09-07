# Startup

Quick command reference. The *why* and *when* live in
[docs/RUNNING.md](docs/RUNNING.md); deployment is
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

**Prereq (once):**
```
python -m venv .venv
.venv\Scripts\activate                  # POSIX: source .venv/bin/activate
pip install -e ".[agent,persist]"       # drop ,persist if you don't want Postgres sessions
copy .env.example .env                  # then set GEMINI_API_KEY in .env
```

**Build the knowledge base (once, and again whenever CodeJudge's docs change):**
```
python -m codejudge_ai.scripts.sync_docs   # copies ../CodeJudge/docs -> ./corpus (READ-only on CodeJudge)
python -m codejudge_ai.scripts.ingest      # extract -> chunk -> embed -> store.json (needs GEMINI_API_KEY)
```
The agent can't answer doc questions until this exists. Not needed again on
every start — only when the documents change.

**Persistent sessions (optional, recommended for multi-turn debugging):** set
`CODEJUDGE_AI_SESSION_DB_URL` in `.env` (e.g.
`postgresql+asyncpg://postgres:12345@localhost:5433/codejudge_ai_sessions`).
Without it, sessions are in-memory and every restart loses the conversation.

### 1. Doc Q&A only — one process (normal case)
```
python -m codejudge_ai.scripts.web
```
Dev UI on <http://localhost:8000>, `codejudge_assistant` auto-selected. This
*is* the agent — there's no separate agent server to start. RAG questions work;
live-problem/authoring/grading tools report they can't connect.

`--no-persist` forces in-memory sessions; `--port 8010` moves the port.

### 2. Everything — live problems, authoring, grading (3 processes)
```
# terminal 1 - CodeJudge (its own repo; see ../CodeJudge/startup.md)
docker compose up --scale worker=2        # run there, exposes http://localhost:8888

# terminal 2 - the MCP server (fronts CodeJudge for the agent)
python -m codejudge_mcp                   # serves http://127.0.0.1:8081/mcp

# terminal 3 - the agent
python -m codejudge_ai.scripts.web
```
Needed for: `list_problems` / `get_problem_spec`, the whole `problem_author`
workflow (draft → validate → publish), and `adversarial_grader` (which runs
real code in CodeJudge's sandbox).

### 3. Terminal instead of the web UI
```
python -m codejudge_ai.scripts.chat "how are verdicts decided?"   # one-shot
python -m codejudge_ai.scripts.chat                                # interactive
adk run adk_app/codejudge_assistant                                # ADK's own REPL
```
Same agent, different interface. Note the authoring/grading flows expect a
multi-turn conversation (they ask for your "yes" before mutating anything), so
the web UI or the interactive REPL is easier than one-shot mode.

### 4. Headless HTTP server (what a UI would talk to)
```
python server.py                          # http://localhost:8000 + custom /healthz
adk api_server adk_app/codejudge_assistant --port 8000   # plain, no dev UI
```
`server.py` is the entrypoint the Docker image uses in production.

**Ports:** agent/dev UI `8000` · MCP server `8081` · CodeJudge `8888` ·
Postgres (sessions) wherever you point `CODEJUDGE_AI_SESSION_DB_URL`.

**Stop:** Ctrl+C in each terminal. On Windows, if a port stays held:
```
Get-NetTCPConnection -LocalPort 8000 -State Listen | Select-Object -ExpandProperty OwningProcess
Stop-Process -Id <pid> -Force
```
(Git Bash's `kill` often fails to signal real Win32 processes — use the
PowerShell form above.)
