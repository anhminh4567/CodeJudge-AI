"""The MCP server: a FastMCP instance plus the tools it exposes.

Each tool is a thin adapter — decode the model's arguments, call the CodeJudge
client, and return a structured result the agent can reason over. Errors are
returned as data (an "error" field) rather than raised, so the model can react
(e.g. try a different id) instead of seeing a transport failure.

Tools split into two groups (see codejudge_ai/agent/problem_author.py — the
"mutating" ones aren't gated at the tool level; that agent's instruction
requires it to ask the admin for a plain "yes" in chat before calling them):

  read-only, public:  list_problems, get_problem_spec
  read-only, admin:   get_problem_status, validate_problem, run_submission
  mutating, admin:    create_draft_problem, add_test_cases,
                      set_reference_solution, publish_problem, unpublish_problem
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

from . import codejudge_client, config
from .codejudge_client import CodeJudgeError, PollTimeout

mcp = FastMCP(
    "codejudge-mcp",
    host=config.MCP_HOST,
    port=config.MCP_PORT,
    streamable_http_path=config.MCP_PATH,
)


# --- Shared nested argument shapes (FastMCP introspects pydantic models to
# build a proper JSON schema for nested tool arguments) ---------------------

class TestCase(BaseModel):
    """One test case for a problem (inline at creation, or added in a batch)."""

    stdin: str = ""
    expected_stdout: str
    sample: bool = False  # visible to end users if True; hidden otherwise


class ProblemLimits(BaseModel):
    """Resource limits for grading. Leave a field at 0 to use CodeJudge's default."""

    wall_time_ms: int = 0
    memory_mb: int = 0
    cpus: float = 0
    pids_max: int = 0

    def to_wire(self) -> dict:
        return {
            "wallTimeMs": self.wall_time_ms,
            "memoryMb": self.memory_mb,
            "cpus": self.cpus,
            "pidsMax": self.pids_max,
        }


# --- Public (read-only) -----------------------------------------------------

@mcp.tool()
async def list_problems(page: int = 1, size: int = 20) -> dict:
    """List the published problems on CodeJudge (id + metadata), paged.

    Use this to see what problems exist — e.g. to answer "what problems are
    there?" or to find a problem id before looking it up in detail. Drafts are
    not included; use get_problem_status for a specific draft.

    Args:
        page: 1-based page number.
        size: page size (max 100).
    """
    try:
        items = await codejudge_client.list_problems(page, size)
    except CodeJudgeError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"could not reach CodeJudge: {exc}"}
    return {"problems": items, "count": len(items)}


@mcp.tool()
async def get_problem_spec(problem_id: str) -> dict:
    """Look up one published CodeJudge problem's public spec.

    Returns its title, description, difficulty, tags, grading mode, function
    signature/entry point, resource limits, and sample (visible) test cases.
    Use this to answer questions about a specific existing problem instead of
    guessing.

    Args:
        problem_id: The id of the problem to look up, e.g. "two-sum".
    """
    if not problem_id:
        return {"error": "problem_id is required"}
    try:
        data = await codejudge_client.get_problem(problem_id)
    except CodeJudgeError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # network/timeout: surface to the model as data
        return {"error": f"could not reach CodeJudge: {exc}"}

    return {
        "id": data.get("id"),
        "title": data.get("title"),
        "description": data.get("description"),
        "difficulty": data.get("difficulty"),
        "tags": data.get("tags", []),
        "mode": data.get("mode"),
        "signature": data.get("signature"),
        "entryFunc": data.get("entryFunc"),
        "limits": data.get("limits"),
        "sampleCases": data.get("sampleCases", []),
    }


# --- Admin: read/verify (no confirmation needed — non-destructive) ---------

@mcp.tool()
async def get_problem_status(problem_id: str) -> dict:
    """Get the full admin view of a problem: status (DRAFT/PUBLISHED), ALL
    cases (including hidden ones), the reference solution if set, and the last
    validation run's id. Works for drafts, unlike get_problem_spec.

    Args:
        problem_id: The id of the problem to inspect.
    """
    try:
        return await codejudge_client.get_admin_problem(problem_id)
    except CodeJudgeError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"could not reach CodeJudge: {exc}"}


@mcp.tool()
async def validate_problem(problem_id: str) -> dict:
    """Run the problem's reference solution against ALL of its cases, for real,
    in CodeJudge's sandbox, and wait for the result (up to ~60s).

    Passing means AC (Accepted) on every case — that's the gate publish_problem
    checks. A failure here means a case is wrong or the reference solution is
    wrong; fix one and validate again. This does not publish or change anything
    public — it's safe to call as many times as needed while iterating.

    Args:
        problem_id: The id of the draft (or published) problem to validate.
    """
    try:
        submission = await codejudge_client.validate_problem(problem_id)
    except PollTimeout as exc:
        return {"error": str(exc)}
    except CodeJudgeError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"could not reach CodeJudge: {exc}"}

    return {
        "verdict": (submission.get("verdict") or {}).get("code"),
        "status": (submission.get("status") or {}).get("code"),
        "cases": submission.get("cases", []),
        "passed": (submission.get("verdict") or {}).get("code") == "AC",
    }


class RunCase(BaseModel):
    """One case for run_submission: an input and an optional expected output."""

    stdin: str = ""
    expected_stdout: str = ""  # empty -> output-only (unscored); non-empty -> scored AC/WA


@mcp.tool()
async def run_submission(problem_id: str, language: str, source_code: str, cases: list[RunCase]) -> dict:
    """Trial-run code against a set of cases WITHOUT persisting anything —
    a sandbox scratchpad. Use this to sanity-check a candidate reference
    solution against candidate test cases BEFORE committing them with
    add_test_cases / set_reference_solution, since cases can't be edited or
    removed once added. Iterate freely here; nothing here is saved or counted.

    Needs an existing problem_id (a draft is fine) — the run borrows that
    problem's mode/signature/limits so it compiles and runs identically to a
    real submission; only the cases differ. A case with a non-empty
    expected_stdout is scored (AC/WA); one left empty just runs and reports
    what it printed, for you to eyeball.

    Args:
        problem_id: An existing problem's id (the draft you're building, typically).
        language: The language id to run the code as, e.g. "python".
        source_code: The candidate source to trial-run.
        cases: Cases to try it against.
    """
    try:
        wire_cases = [{"stdin": c.stdin, "expectedStdout": c.expected_stdout} for c in cases]
        submission = await codejudge_client.run_submission(problem_id, language, source_code, wire_cases)
    except PollTimeout as exc:
        return {"error": str(exc)}
    except CodeJudgeError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"could not reach CodeJudge: {exc}"}

    return {
        "verdict": (submission.get("verdict") or {}).get("code"),
        "status": (submission.get("status") or {}).get("code"),
        "cases": submission.get("cases", []),  # includes stdout per case
    }


# --- Admin: mutating (gated by problem_author's instruction, not a tool-level
# mechanism — see codejudge_ai/agent/problem_author.py) ----------------------

@mcp.tool()
async def create_draft_problem(
    problem_id: str,
    title: str,
    description: str,
    mode: str,
    signature: str = "",
    entry_func: str = "",
    difficulty: str = "",
    tags: list[str] | None = None,
    limits: ProblemLimits | None = None,
    cases: list[TestCase] | None = None,
) -> dict:
    """Create a new problem in DRAFT status. Not visible to end users yet —
    drafts only appear through get_problem_status, never in list_problems.

    Args:
        problem_id: A short, unique, url-safe id, e.g. "two-sum".
        title: Human-readable problem title.
        description: The problem statement (Markdown is fine).
        mode: "stdio" (reads stdin, writes stdout) or "function" (implements a
            function with the given signature/entry_func).
        signature: Function signature, required if mode="function".
        entry_func: Entry function name, required if mode="function".
        difficulty: "EASY" | "MEDIUM" | "HARD" (optional).
        tags: Topic tags, e.g. ["arrays", "hash-table"] (optional).
        limits: Resource limits (optional; CodeJudge defaults anything left at 0).
        cases: Leave this empty. Cases can't be edited or removed once added, so
            add them afterward with add_test_cases -- and only after using
            run_submission to prove each one against a candidate solution first.
            This param exists for the rare case where you're deliberately
            skipping the dry-run (e.g. copying already-verified cases).
    """
    payload = {
        "id": problem_id,
        "title": title,
        "description": description,
        "mode": mode,
        "signature": signature,
        "entryFunc": entry_func,
        "difficulty": difficulty,
        "tags": tags or [],
        "limits": (limits or ProblemLimits()).to_wire(),
        "cases": [
            {"stdin": c.stdin, "expectedStdout": c.expected_stdout, "sample": c.sample}
            for c in (cases or [])
        ],
    }
    try:
        return await codejudge_client.create_draft_problem(payload)
    except CodeJudgeError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"could not reach CodeJudge: {exc}"}


@mcp.tool()
async def add_test_cases(problem_id: str, cases: list[TestCase]) -> dict:
    """Add a batch of test cases to a draft in one call — one approval covers
    the whole batch, rather than approving each case individually.

    Stops at the first failure so a partially-added, mismatched batch can't
    silently happen; already-added cases before the failure stay added.

    Args:
        problem_id: The draft's id.
        cases: The test cases to add.
    """
    added_ids: list[str] = []
    try:
        for case in cases:
            case_id = await codejudge_client.add_test_case(
                problem_id, case.stdin, case.expected_stdout, case.sample
            )
            added_ids.append(case_id)
    except CodeJudgeError as exc:
        return {"error": str(exc), "added": added_ids}
    except Exception as exc:
        return {"error": f"could not reach CodeJudge: {exc}", "added": added_ids}
    return {"added": added_ids, "count": len(added_ids)}


@mcp.tool()
async def set_reference_solution(problem_id: str, language: str, source_code: str) -> dict:
    """Set/replace the problem's reference (answer-key) solution. This is what
    validate_problem runs to prove the cases are correct — set this before
    calling validate_problem.

    Args:
        problem_id: The draft's id.
        language: The language id (see the languages tool/endpoint), e.g. "python".
        source_code: The full source of a solution you believe is correct.
    """
    try:
        await codejudge_client.set_reference_solution(problem_id, language, source_code)
    except CodeJudgeError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"could not reach CodeJudge: {exc}"}
    return {"status": "ok"}


@mcp.tool()
async def publish_problem(problem_id: str) -> dict:
    """Make a problem live: DRAFT -> PUBLISHED. Refused unless validate_problem
    last passed (AC on every case) — call validate_problem first.

    Args:
        problem_id: The draft's id.
    """
    try:
        return await codejudge_client.publish_problem(problem_id)
    except CodeJudgeError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"could not reach CodeJudge: {exc}"}


@mcp.tool()
async def unpublish_problem(problem_id: str) -> dict:
    """Take a problem back offline: PUBLISHED -> DRAFT (e.g. to fix something
    after it went live). It stops appearing in list_problems immediately.

    Args:
        problem_id: The problem's id.
    """
    try:
        return await codejudge_client.unpublish_problem(problem_id)
    except CodeJudgeError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"could not reach CodeJudge: {exc}"}
