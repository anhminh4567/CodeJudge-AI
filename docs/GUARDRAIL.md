# Input guardrail

How CodeJudge-AI screens user input before the model runs, why it's built this
way, and how to configure it. Code: [`codejudge_ai/agent/guardrail.py`](../codejudge_ai/agent/guardrail.py).

## What it is

A **guardrail** is a check that runs *around* the model to enforce a policy —
here, on the way in: screen the user's message and refuse the unacceptable ones
before they reach the LLM.

We implement it as an ADK **`before_model_callback`** on the agent. That hook
fires just before each model call and may return an `LlmResponse`; when it does,
ADK uses that as the answer and **skips the real model call**. So a rejected
message is short-circuited into a refusal. Because the callback lives on the
agent (not a runner), it protects every entry point — `chat`, `adk web`, `adk run`.

It screens **once per user turn**: the hook fires on every model call in the
agent loop, but we only screen when the newest turn is the human's message (the
intermediate tool-result iterations carry no new user text), so we never re-screen
or waste a call mid-loop.

## Why not "just regex"?

Regex/keyword matching is the classic first attempt, and it's genuinely weak as a
*sole* defense:

- **Bypassable.** Trivial paraphrase, spacing, unicode look-alikes, or base64
  slip past fixed patterns.
- **False positives.** Broad patterns block legitimate questions. In this domain
  that bites immediately: "how does CodeJudge **run code** in the sandbox?" is a
  normal question and must not be blocked.
- **Unbounded maintenance.** Every new phrasing is a new pattern; the list never
  ends and gives false confidence.

So we treat pattern matching as a **cheap floor, not the wall**, and offer a
model-based screen for real robustness.

## The two strategies (configurable)

Set the mode with `CODEJUDGE_AI_GUARDRAIL` (`off` | `heuristic` | `llm`). All modes
first apply a hard length cap (a cheap abuse/cost guard).

| Mode | How | Strengths | Costs |
|------|-----|-----------|-------|
| `off` | no screening | zero overhead | no protection |
| `heuristic` | length cap + a few **high-precision** patterns for blatant prompt-injection / prompt-leak | fast, free, deterministic | limited, bypassable — a floor only |
| `llm` | a model classifies each message as `ALLOW`/`BLOCK` with a strict instruction | robust to paraphrase & novel phrasings; understands context (won't block "run code" questions) | one extra model call per user turn (latency + cost); the classifier itself must be prompt-hardened |

The `llm` mode is the "a safety model screens the request" pattern. Both
strategies return the same `Verdict`, so the callback is identical either way —
swapping strategies is one env var.

**Fail-open:** if the `llm` screen errors (network, quota), it logs a warning and
**allows** the message, so a guardrail hiccup never takes the assistant down. If
your threat model prefers fail-closed (block on error), flip that in `_screen_llm`.

**Gotcha (token budget):** these Gemini models "think" before answering, and
thinking tokens count against `max_output_tokens`. Too small a budget and the
one-word verdict gets truncated to *empty* (`finish_reason=MAX_TOKENS`) — which,
combined with fail-open, would silently allow everything. We set 128 so thinking
plus the `ALLOW`/`BLOCK` word both fit.

## Recommendation

- Local/dev demos: `heuristic` is fine and keeps things snappy and free.
- Anything user-facing: `llm` (or a dedicated moderation API), ideally *with* the
  heuristic as a cheap pre-filter, and consider screening **outputs** too.

## Extending it

- **Swap the check:** replace `screen_input` / `_screen_llm` — a moderation API
  (e.g. a content-safety endpoint) drops in the same way.
- **Screen outputs:** add an `after_model_callback` that inspects the response and
  redacts/refuses. Same idea, other direction.
- **Per-tool guards:** a `before_tool_callback` returning a dict short-circuits a
  specific tool (e.g. validate/limit arguments) without touching the model.

## Configuration

| Var | Values | Default | Meaning |
|-----|--------|---------|---------|
| `CODEJUDGE_AI_GUARDRAIL` | `off` / `heuristic` / `llm` (also `0`/`1`) | `heuristic` | screening strategy |

Related: [OBSERVABILITY.md](OBSERVABILITY.md) (the other callback/plugin seams),
[ARCHITECTURE.md](ARCHITECTURE.md).
