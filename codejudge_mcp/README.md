# codejudge_mcp

An **MCP server** (Streamable HTTP) that wraps CodeJudge's public HTTP API as
tools an AI agent can call. Built on the official Python `mcp` SDK (FastMCP), so
the whole repo is one language.

It is a separate deployable from the agent: the only component that talks to
CodeJudge, and it does so purely over HTTP (see the repo root `CLAUDE.md`).

## Layout

```
codejudge_mcp/
├── __main__.py         # `python -m codejudge_mcp` -> serves Streamable HTTP
├── server.py           # the FastMCP instance + tool definitions
├── codejudge_client.py # async httpx client for CodeJudge (+ error mapping)
└── config.py           # env-driven config
```

## Tools

| Tool | Wraps | Purpose |
|------|-------|---------|
| `list_problems(page, size)` | `GET /problems` | List available problems (id + metadata), paged. |
| `get_problem_spec(problem_id)` | `GET /problems/:id` | Fetch a problem's public spec (mode, signature, limits, sample cases). |

More tools (`run_submission`, `add_problem`, …) are added as the agent grows;
each is a `@mcp.tool()` in `server.py`.

## Configuration (env, shared repo-root `.env`)

| Var | Default | Meaning |
|-----|---------|---------|
| `CODEJUDGE_BASE_URL` | `http://localhost:8080` | Base URL of the running CodeJudge API. |
| `MCP_HOST` | `127.0.0.1` | Address the MCP server binds. |
| `MCP_PORT` | `8081` | Port the MCP server listens on. |
| `MCP_PATH` | `/mcp` | Streamable HTTP mount path. |

## Run

```bash
python -m codejudge_mcp
```

The agent connects to `http://127.0.0.1:8081/mcp`. The server starts even if
CodeJudge is down; tools return an `error` field until CodeJudge is reachable.
