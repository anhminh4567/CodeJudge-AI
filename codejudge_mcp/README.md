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

Public (read-only):

| Tool | Wraps | Purpose |
|------|-------|---------|
| `list_problems(page, size)` | `GET /problems` | List published problems (id + metadata), paged. |
| `get_problem_spec(problem_id)` | `GET /problems/:id` | Fetch a published problem's public spec. |
| `get_submission(submission_id)` | `GET /submissions/:id` | Look up a submission/run's problem, language, source code, and verdict — used by adversarial grading to resolve a submission id ([../docs/ADVERSARIAL_GRADING.md](../docs/ADVERSARIAL_GRADING.md)). |

Admin (problem authoring — see [../docs/PROBLEM_AUTHORING.md](../docs/PROBLEM_AUTHORING.md)):

| Tool | Wraps | Purpose |
|------|-------|---------|
| `get_problem_status(problem_id)` | `GET /admin/problems/:id` | Admin view: status, all cases, reference solution. |
| `validate_problem(problem_id)` | `POST .../validate`, polled internally | Run the reference solution for real; pass/fail. |
| `run_submission(problem_id, language, source_code, cases)` | `POST /submissions/run`, polled internally | Trial-run code against ad-hoc cases; nothing persisted. Dry-run cases/a solution before committing them. |
| `create_draft_problem(...)` | `POST /admin/problems` | Create a new DRAFT problem. |
| `add_test_cases(problem_id, cases)` | `POST .../testcases`, looped | Add a batch of cases in one call. |
| `set_reference_solution(problem_id, language, source_code)` | `PUT .../reference` | Set the answer-key solution. |
| `publish_problem(problem_id)` | `POST .../publish` | DRAFT → PUBLISHED (gated on a passing validation). |
| `unpublish_problem(problem_id)` | `POST .../unpublish` | PUBLISHED → DRAFT. |

More tools are added as the agent grows; each is a `@mcp.tool()` in `server.py`.

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
