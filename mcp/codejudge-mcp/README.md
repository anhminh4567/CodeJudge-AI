# codejudge-mcp

A thin **MCP server** (Streamable HTTP transport) that wraps CodeJudge's public
HTTP API as tools an AI agent can call. It is a separate deployable from CodeJudge
and from `codejudge-ai` — the only component that talks to CodeJudge, and it does
so purely over HTTP (see the architecture decisions in the repo's `CLAUDE.md`).

## Layout

```
cmd/server/main.go        # wires the MCP server + tools, serves Streamable HTTP
internal/codejudge/       # HTTP client for CodeJudge (client.go) + wire types (types.go)
internal/tools/           # one file per MCP tool
```

## Tools

| Tool | Wraps | Purpose |
|------|-------|---------|
| `get_problem_spec(problemId)` | `GET /problems/:id` | Fetch a problem's public spec (mode, signature, limits, sample cases). |

More tools (`list_problems`, `run_submission`, `add_problem`, `commit_test_case`)
are planned as the agent grows; each is one file under `internal/tools/`.

## Configuration (env)

| Var | Default | Meaning |
|-----|---------|---------|
| `CODEJUDGE_BASE_URL` | `http://localhost:8080` | Base URL of the running CodeJudge API. |
| `MCP_LISTEN_ADDR` | `:8081` | Address the MCP server listens on. |

## Run

```bash
go run ./cmd/server
```

The server starts even if CodeJudge is down (it logs a warning); tools report
per-call errors until CodeJudge is reachable.

## Smoke test the transport

```bash
curl -s -X POST http://localhost:8081/ \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}'
```

A `serverInfo` result with `tools` capability confirms it's up.
