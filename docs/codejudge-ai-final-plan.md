# CodeJudge AI Layer — Final Plan & PoC Brief

Purpose of this doc: lock in the decisions from our discussion, state my actual recommendation (not just a menu of options), add the RAG requirement, and define a fast PoC. This is meant to be handed to a coding agent next to scaffold the actual repos — so decisions are stated plainly rather than left as trade-off tables.

---

## 1. Recap — the three capabilities

| Capability | Shape |
|---|---|
| Answer visitor questions (site docs + ingested PDFs/Word) | Retrieval + generation, low risk |
| Author problems / generate & validate test cases | Fixed pipeline (draft → validate → persist) with an iterative sub-loop |
| Grade a submission with AI-generated adversarial cases | Real agent loop, grounded by actual sandboxed execution |

---

## 2. Decisions (locked in)

**D1 — Microservices, confirmed.** `codejudge-ai` is a separate repo/binary from CodeJudge. No shared module, no in-process calls. They talk over CodeJudge's API only.

**D2 — Polyglot: Go for the tool layer, Python for the agent + RAG.** This is my actual recommendation, not a coin flip:
- **`codejudge-mcp` (Go).** Thin MCP server, wraps CodeJudge's API (existing public endpoints + a new internal/admin surface). Go because it's a small translation layer sitting right next to a Go codebase — no reason to pay a language tax here.
- **`codejudge-ai` (Python).** The agent brain and the document-RAG pipeline. Python because this is exactly where "best ecosystem and best documented" points one way: **Google ADK's Python SDK is the original, most mature, most documented ADK surface** (the Go port is newer and thinner), and PDF/Word ingestion + embeddings tooling in Python (`pypdf`, `python-docx`, LangChain/LlamaIndex loaders) has no real Go equivalent. MCP is the seam that makes this free — the agent doesn't care what language wrote the tools it calls.

**D3 — Orchestration: workflow where predictable, agent where it needs judgment.** Still applies from before — deterministic pipeline steps for problem-authoring, a genuine tool-using agent loop for grading and for docs Q&A retrieval-then-generation.

**D4 — MCP over Streamable HTTP everywhere.** Every tool boundary (agent ↔ `codejudge-mcp`, agent ↔ its own RAG tool) is a network call, consistent with D1.

**D5 — The LLM never executes code.** All execution goes through CodeJudge's existing judge/sandbox via `run_submission`. Non-negotiable regardless of language choice.

**D6 — RAG stays light: no dedicated vector database.** For a personal-scale document set (some PDFs/Word docs), a managed vector DB is overkill — retrieval is just cosine similarity over a modest number of vectors, which a flat file handles fine. See §5.

---

## 3. Final service map

```
+----------------------+     +-----------------------+     +--------------------------------+
|  CodeJudge (Go)      |     |  codejudge-mcp (Go)    |     |  codejudge-ai (Python)          |
|  - existing -        |<--->|  MCP server            |<--->|  ADK (Python) LlmAgent(s)       |
|  public API +        | API |  search_docs,          | MCP |  + RAG module:                  |
|  NEW internal/admin  |     |  get_problem_spec,     |HTTP |    ingest PDF/DOCX -> embed ->  |
|  API (service-token) |     |  run_submission,       |     |    local store -> retrieve      |
|  DB, judge/sandbox    |     |  propose_test_case,    |     |                                 |
+----------------------+     |  add_problem ...       |     +----------------+----------------+
                              +-----------------------+                       | genai
                                                                    +----------v-----------+
                                                                    |     Gemini API        |
                                                                    +-----------------------+
```

Three independent deployables. Each can be developed, tested, and redeployed on its own. `codejudge-mcp` is the only thing that ever talks to CodeJudge; `codejudge-ai` is the only thing that ever talks to Gemini.

| Service | Language | Depends on |
|---|---|---|
| CodeJudge | Go (unchanged core + new admin endpoints) | its own DB |
| `codejudge-mcp` | Go | CodeJudge's API (service token) |
| `codejudge-ai` | Python (`google-adk`) | `codejudge-mcp` (MCP/HTTP) + Gemini API |

---

## 4. Why this split, plainly

Go stays where you already have it working (CodeJudge) and where the new piece is genuinely thin (translating MCP tool calls into HTTP calls). Python takes over exactly where the job is "parse messy real-world documents and run a well-documented agent loop" — that's a Python-shaped problem in 2026 regardless of which language your backend is in. Forcing the RAG/agent piece into Go would mean hand-rolling PDF/DOCX parsing and embedding plumbing with a much thinner set of libraries and far fewer worked examples to lean on, for zero architectural benefit — `codejudge-ai` never touches CodeJudge's code either way.

**Sources:** [ADK Python reaches production-ready milestone](https://codelabs.developers.google.com/codelabs/currency-agent) · [ADK Python MCPToolset + Streamable HTTP](https://github.com/google/adk-docs/issues/407)

---

## 5. Light RAG for PDF/Word ingestion

Pipeline, deliberately minimal:

| Step | Tool | Note |
|---|---|---|
| Extract text | `pypdf` (PDF) / `python-docx` (Word) | Plain, no-frills extraction. `unstructured` is a heavier alternative if layout/tables matter later. |
| Chunk | Simple recursive character splitter (LangChain's `RecursiveCharacterTextSplitter` works standalone without pulling in the rest of LangChain) | ~500-1000 tokens per chunk, some overlap |
| Embed | Gemini `gemini-embedding-001` via `client.models.embed_content()` | Text-only, stable, GA. Keeps everything on one provider (same API key as generation). |
| Store | **Flat file** (JSON/`npy` of vectors + text, cosine similarity in a few lines of numpy) for the PoC | A dedicated vector DB (Chroma, Qdrant) is a fine upgrade later, but for a personal doc set it's added ops for no accuracy gain right now. |
| Retrieve | Top-k cosine similarity -> feed chunks into the agent's context | Exposed to the agent as a plain Python function tool, e.g. `search_ingested_docs(query: str) -> list[Chunk]` |

Worth knowing: Google shipped `gemini-embedding-2` (multimodal — text, image, PDF pages, audio in one embedding space) very recently. It can embed short PDFs directly without you extracting text at all, up to 6 pages per call. It's new enough that I'd treat it as a later upgrade path rather than the PoC default — start with the boring, well-understood `gemini-embedding-001` + manual extraction, since your docs are likely longer than 6 pages anyway and you want predictable chunking now.

This RAG module lives inside `codejudge-ai` as a plain Python tool for the PoC — no need to wrap it in its own MCP server yet. Split it out into a separate `docs-rag-mcp` service later only if you want other MCP clients (Claude Code, Gemini CLI) to query the same ingested docs directly.

**Sources:** [Gemini Embedding 001 - GA](https://developers.googleblog.com/gemini-embedding-available-gemini-api/) · [Gemini Embedding 2 - multimodal](https://developers.googleblog.com/building-with-gemini-embedding-2/) · [Gemini embeddings docs](https://ai.google.dev/gemini-api/docs/embeddings) · [you probably don't need a vector database yet](https://towardsdatascience.com/you-probably-dont-need-a-vector-database-for-your-rag-yet/)

---

## 6. Quick PoC — definition

The point of a PoC is proving real tool-use, not shipping a chatbot. A single-tool RAG demo doesn't prove that; a task that forces the agent to *choose* between tools does.

**PoC task:** the agent receives a visitor question and must decide, per question, whether to (a) retrieve from the ingested PDFs/Word docs, or (b) call `get_problem_spec` on `codejudge-mcp` for a live problem lookup, then answer — sometimes using both in one turn. That decision is the "real agent capability" you're after: it's model-driven tool selection grounded in two genuinely different sources, not a scripted call.

**Minimal stack for the PoC:**
- `codejudge-mcp` (Go): just `search_docs` (if CodeJudge already exposes something) + `get_problem_spec`.
- `codejudge-ai` (Python): one `LlmAgent` (`google-adk`), `tools=[MCPToolset(...), search_ingested_docs]`, run via ADK's `InMemoryRunner` for fast local iteration (no deployment needed to see it work).
- A one-off ingestion script that runs the extract->chunk->embed pipeline over a handful of PDFs/docs into the flat-file store.

```python
from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import MCPToolset, StreamableHTTPConnectionParams

root_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="codejudge_assistant",
    instruction="Answer visitor questions. Use search_ingested_docs for general help "
                "content, and get_problem_spec when the question is about a specific problem.",
    tools=[
        MCPToolset(connection_params=StreamableHTTPConnectionParams(url="http://localhost:8080/mcp")),
        search_ingested_docs,
    ],
)
```

That's the whole PoC surface — small enough to build in a sitting, but it genuinely exercises tool selection, MCP, and RAG together, which is the "prove agentic workflow can be simple" goal from the start of this conversation.

---

## 7. Handoff notes (for scaffolding)

Three repos to stand up:
1. **`codejudge-mcp`** (Go) — MCP server, `go-sdk`, Streamable HTTP, thin HTTP client to CodeJudge.
2. **`codejudge-ai`** (Python) — `google-adk`, the RAG ingestion module, agent definition(s).
3. **CodeJudge** (existing repo) — add the internal/admin endpoints `codejudge-mcp` needs (`run_submission` ad-hoc, `add_problem`, `commit_test_case`), gated by a service token, separate from the public API.

Everything in §5-6 is enough detail to start `codejudge-ai`'s structure; §3's tool list is enough to start `codejudge-mcp`'s.
