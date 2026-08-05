# codejudge-ai — Overview (start here)

A plain-language tour of the Python project: what it is, what each piece does,
which libraries we use and why, and how to run it. Read top to bottom once and
the folder will stop looking mysterious.

---

## 1. What this project is, in one paragraph

`codejudge-ai` is the "brain" that will answer questions and help author coding
problems for CodeJudge. Right now it contains **only the first capability's
foundation: RAG** (see below). The AI agent itself is the *next* step and is not
wired up yet. So today this project can: take a pile of documents, understand
them, and let you search them by meaning. That's it — and that's on purpose, so
each layer is small enough to review.

---

## 2. The two big words: RAG and ADK

**RAG = Retrieval-Augmented Generation.** The idea: before the AI answers a
question, we *retrieve* the most relevant snippets from our own documents and
hand them to the model as context. That way the answer is grounded in *our* docs
(CodeJudge's guides, your PDFs) instead of the model guessing. RAG has two halves:

1. **Ingest (offline, done once per doc set):** read documents → cut them into
   small pieces → turn each piece into a vector (a list of numbers that captures
   its meaning) → save those vectors. **This half is what we built.**
2. **Retrieve (at question time):** turn the question into a vector too, find the
   pieces whose vectors are closest, return them. **Also built** (`rag/search.py`),
   ready for the agent to call.

**ADK = Google's Agent Development Kit** (`google-adk`). It's the framework we'll
use to build the actual *agent* — the thing that decides which tool to call and
talks to the user. **We are NOT using it yet.** It's listed as an *optional*
dependency (`pip install -e ".[agent]"`) and only comes into play in the next
step. So don't look for it in the current code — it isn't there on purpose.

---

## 3. Which libraries we use, and for what

| Library | Role here | Why this one |
|---|---|---|
| `google-genai` | Calls Gemini to make **embeddings** (vectors) | Same provider/API key we'll use for generation; the embedding model `gemini-embedding-001` is stable and GA. |
| `langchain-text-splitters` | **Chunks** long text into overlapping pieces | The standard, well-tested recursive splitter — no reason to hand-roll one. |
| `langchain-core` | The in-memory **vector store** (`InMemoryVectorStore`) | Library-backed similarity search that lives in RAM and saves to one JSON file — no database service to run. |
| `pypdf` | Reads text out of **PDF** files | Standard, lightweight PDF text extraction. |
| `python-docx` | Reads text out of **Word** (.docx) files | Standard Word reader. |
| `python-dotenv` | Loads your `.env` so secrets aren't hardcoded | Convenience for local runs. |
| `google-adk` *(optional, later)* | The **agent** framework | Most mature ADK SDK; not used yet. |

**What we deliberately did NOT use:** no vector database *service* (Chroma server,
Qdrant, etc.). For a personal-scale doc set, an in-memory store that persists to a
single JSON file is simpler, has nothing extra to run, and loses no accuracy. We
can swap in a real vector DB later by rewriting just one file (`rag/store.py`) —
everything above it talks to a small `VectorStore` API, not to LangChain directly.

---

## 4. What "corpus" and "store" mean

- **`corpus/`** — the **raw source documents** we want the AI to know about. Think
  of it as the inbox. Today the sync script copies CodeJudge's Markdown guides in
  here; you can also drop your own PDFs or Word docs in. It's just files on disk.
  *(Gitignored — it's data, not code.)*
- **`store/`** (`codejudge_ai/rag/store/`) — the **processed, searchable form** of
  the corpus: `store.json`, holding the text pieces and their vectors together
  (dumped by the in-memory vector store). Produced by the ingest step. *(Also gitignored.)*

Flow: `corpus/` (raw docs) → **ingest** → `store/` (searchable vectors) →
**search** returns the best pieces.

---

## 5. Folder structure (what each file is)

```
codejudge-ai/                     <- the Python project root
├── pyproject.toml                <- project metadata + dependency list
├── .env.example                  <- template for your secrets; copy to .env
├── README.md                     <- quick command reference
├── OVERVIEW.md                   <- this file
│
├── corpus/                       <- raw source docs (gitignored, created by sync)
│
└── codejudge_ai/                 <- the importable Python package (note underscore)
    ├── config.py                 <- ALL settings in one place (paths, model names, knobs)
    │
    ├── rag/                      <- the Retrieval half of RAG
    │   ├── extract.py            <- file (md/pdf/docx) -> plain text
    │   ├── chunk.py              <- long text -> small overlapping pieces (LangChain splitter)
    │   ├── embed.py              <- text pieces -> vectors (calls Gemini) + LangChain adapter
    │   ├── store.py              <- InMemoryVectorStore wrapper: build/save/load + search
    │   ├── search.py             <- search("question") -> best pieces  [agent will call this]
    │   └── store/                <- the saved store.json lives here (gitignored)
    │
    └── scripts/                  <- the things you actually RUN
        ├── sync_docs.py          <- copy CodeJudge's docs into corpus/
        └── ingest.py             <- build the store from corpus/
```

The dashed name `codejudge-ai` (the folder) can't be imported in Python because
of the dash, so the actual package inside uses an underscore: `codejudge_ai`.
That's why there are two similar names.

---

## 6. Entry points — what you run

There is no long-running server here yet. You run **scripts**, each with
`python -m` (that's how you run a module inside a package):

```bash
# 1) Pull CodeJudge's Markdown docs into corpus/  (safe: only READS CodeJudge)
python -m codejudge_ai.scripts.sync_docs

# 2) Build the searchable store from corpus/  (needs GEMINI_API_KEY)
python -m codejudge_ai.scripts.ingest
python -m codejudge_ai.scripts.ingest --dry-run   # preview chunking, no API calls
```

`rag/search.py` is not run directly — it's the function the **agent** will call
once we build it. You can think of it as the finished "search tool" waiting to be
plugged in.

---

## 7. Environment / secrets

Settings come from environment variables, loaded from a local `.env` file
(copied from `.env.example`). The only required one:

- **`GEMINI_API_KEY`** — your Gemini key. Needed to make embeddings (ingest) and,
  later, to generate answers (the agent). `.env` is gitignored, so your key never
  gets committed.

Everything else has a sensible default and is optional (which models to use,
chunk sizes, how many pieces to retrieve, where CodeJudge's docs live). All of
them are listed in `config.py` and `.env.example`.

---

## 8. Where this fits in the bigger picture

```
        (this project: codejudge-ai)
  corpus/ --ingest--> store/ --search--> [ FUTURE: the ADK agent ]
                                               |         |
                          asks Gemini to answer|         | calls tools over MCP
                                               v         v
                                          Gemini API   codejudge-mcp --> CodeJudge
```

Today we've built the left half (corpus → store → search). The next step adds the
agent that *uses* search plus the `codejudge-mcp` tools — that's the PoC milestone.
