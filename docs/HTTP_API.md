# Talking to the agent over HTTP

What a client (CodeJudge-UI's chat panel, or anything else) needs to call the
agent and stream answers back. The server is [`server.py`](../server.py) —
ADK's own FastAPI app plus our `/healthz`. Everything below was verified
against the installed ADK version by running it, not read off a spec.

Base URL: `http://localhost:8000` in dev, your domain in production
(see [DEPLOYMENT.md](DEPLOYMENT.md)).

## CORS

`server.py` passes `allow_origins=config.CORS_ORIGINS` into
`get_fast_api_app(...)`. Default is `*` — any origin. There's no auth on this
service yet, so restricting origins would be theater rather than protection;
tighten `CODEJUDGE_AI_CORS_ORIGINS` (comma-separated) once auth exists.

Verified: a preflight `OPTIONS /run_sse` from `https://ui.example.com` comes
back with `access-control-allow-origin`, `-methods`, `-headers`, and
`-credentials: true`.

## The three calls a chat client needs

### 1. Discover the app name

```
GET /list-apps   ->   ["codejudge_assistant"]
```

`codejudge_assistant` is the folder name under `adk_app/`. It's stable — you
can hardcode it and skip this call.

### 2. Create a session (once per conversation)

```
POST /apps/codejudge_assistant/users/{user_id}/sessions
Content-Type: application/json
{}
```

Returns the session, whose `id` you keep for every later message:

```json
{"id":"8e437932-...","appName":"codejudge_assistant","userId":"u1",
 "state":{},"events":[],"lastUpdateTime":1788789661.86}
```

`user_id` is yours to choose — until auth exists, a uuid in `localStorage` is
fine. Sessions survive restarts only if `CODEJUDGE_AI_SESSION_DB_URL` is set
(it is, in production).

Related: `GET .../sessions` lists them, `GET .../sessions/{id}` returns full
history (use it to rehydrate a conversation after a refresh), `DELETE
.../sessions/{id}` removes one.

### 3. Send a message and stream the answer

```
POST /run_sse
Content-Type: application/json
{
  "appName": "codejudge_assistant",
  "userId": "u1",
  "sessionId": "<from step 2>",
  "streaming": true,
  "newMessage": { "role": "user", "parts": [{ "text": "how are verdicts decided?" }] }
}
```

Response is `text/event-stream` — one `data: {...}` line per event. There's
also `POST /run` with the same body, which returns the whole event list as
JSON once the turn finishes; use it only if you don't want streaming.

**`streaming: true` vs `false`** — both return SSE, but they differ in
granularity:
- `true` → token-level deltas as the model writes (`"partial": true`), so
  text appears live.
- `false` → one event per *completed* step. Simpler, but the user stares at
  nothing until the whole answer lands.

## The event shape

A real `streaming: true` capture, trimmed:

```json
{"content": {"parts": [{"text": "An online"}], "role": "model"},
 "partial": true,
 "author": "codejudge_assistant",
 "id": "710a1bd5-...", "invocationId": "e-d0685293-...",
 "usageMetadata": {"candidatesTokenCount": 2, "promptTokenCount": 1068},
 "timestamp": 1788789678.04}
```

What matters for rendering:

| Field | Use |
|---|---|
| `content.parts[].text` | Append to the current bubble. Consecutive `partial: true` events with the **same `id`** are deltas of one message — concatenate them, don't render each as a new bubble. |
| `partial` | `true` = more coming for this `id`; absent/false = that message is complete. |
| `author` | Which agent spoke — `codejudge_assistant`, `problem_author`, or `adversarial_grader`. Worth surfacing: it's how a user sees the hand-off happen. |
| `content.parts[].functionCall` | A tool call — `{name, args}`. Render as a status line ("looking up problem two-sum…"). |
| `content.parts[].functionResponse` | That tool's result. |
| `invocationId` | Groups every event from one user turn. |
| `usageMetadata` | Token counts, if you want to show cost. |

Parts also carry `thoughtSignature` on some events (model reasoning
metadata) — ignore it, and ignore any field you don't recognize; the shape
grows across ADK versions.

**Sanitize before rendering.** `text` is model-generated and its content is
partly derived from retrieved docs and problem statements — render as
Markdown, never as raw HTML.

## Agent hand-offs are visible

When the model transfers to a sub-agent you'll see a `functionCall` named
`transfer_to_agent` with `{"agent_name": "problem_author"}`, and every event
after it carries that agent as `author`. Showing this is honest and it's the
most interesting part of the demo — the user can see *why* the assistant
switched modes.

## Approval steps are just conversation

`problem_author` asks for a plain "yes" in chat before any mutating step
(create/publish a problem) and waits for the next message — there's no
special protocol to implement. See
[PROBLEM_AUTHORING.md](PROBLEM_AUTHORING.md#how-approval-works).

If you'd rather have a real Accept/Reject **button** than a typed "yes", ADK
has a stronger mechanism we deliberately switched off: tool-level
confirmation, which pauses the run and emits a confirmation request the
client answers. `RunAgentRequest` already carries the fields for resuming it
(`function_call_event_id`, `invocation_id`). Turning it back on is a small
change here plus real work client-side — worth doing when the UI is ready to
render the buttons, not before.

## Other routes

`GET /health` (ADK's) and `GET /healthz` (ours) for liveness; `GET /docs` for
the generated OpenAPI page — the fastest way to see the full surface.

Related: [DEPLOYMENT.md](DEPLOYMENT.md), [ARCHITECTURE.md](ARCHITECTURE.md),
[RUNNING.md](RUNNING.md).
