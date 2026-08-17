"""A thin async HTTP client for CodeJudge's public + admin API.

The only thing in codejudge-mcp that knows CodeJudge's wire shape; the tools talk
to CodeJudge exclusively through this client (D1: they never share a module, only
HTTP). Mirrors CodeJudge's envelopes: objects as {data:...}, errors as
{error:{code,message}}.

Admin functions (create_draft_problem onward) wrap the problem-authoring
endpoints added in CodeJudge's draft -> validate -> publish workflow (see
CodeJudge/docs/PROBLEM_AUTHORING.md, read-only reference). They are marked
"admin" on the CodeJudge side but have no real auth yet (single-operator stage).
"""

from __future__ import annotations

import asyncio
import time
from urllib.parse import quote

import httpx

from . import config

_TIMEOUT = httpx.Timeout(15.0)


class CodeJudgeError(Exception):
    """A non-2xx response from CodeJudge (carries its error envelope if present)."""

    def __init__(self, status_code: int, code: str = "", message: str = ""):
        self.status_code = status_code
        self.code = code
        self.message = message
        if message:
            super().__init__(f"codejudge {status_code} {code}: {message}")
        else:
            super().__init__(f"codejudge: unexpected status {status_code}")


class PollTimeout(Exception):
    """A submission (validate or run) didn't finish within the polling budget."""

    def __init__(self, submission_id: str, kind: str, timeout_s: float):
        self.submission_id = submission_id
        super().__init__(
            f"{kind} {submission_id} did not finish within {timeout_s:.0f}s; "
            f"poll GET /submissions/{submission_id} yourself if it's still running"
        )


async def _request(method: str, path: str, *, params: dict | None = None, json: dict | None = None) -> dict:
    """Send one request to CodeJudge; return the unwrapped `data` payload.

    Raises CodeJudgeError (with the parsed error envelope, when present) on a
    non-2xx response. This is the one place every call goes through, so error
    handling stays consistent as more endpoints get wrapped.
    """
    url = f"{config.CODEJUDGE_BASE_URL}{path}"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.request(method, url, params=params, json=json, headers={"Accept": "application/json"})

    if resp.status_code // 100 != 2:
        code = message = ""
        try:
            err = resp.json().get("error", {})
            code, message = err.get("code", ""), err.get("message", "")
        except Exception:
            pass
        raise CodeJudgeError(resp.status_code, code, message)

    if not resp.content:
        return {}
    return resp.json().get("data", {})


async def healthz() -> None:
    """Raise if CodeJudge isn't reachable / healthy (GET /healthz)."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{config.CODEJUDGE_BASE_URL}/healthz")
    if resp.status_code != 200:
        raise CodeJudgeError(resp.status_code)


# --- Public (read) endpoints -------------------------------------------------

async def list_problems(page: int = 1, size: int = 20) -> list[dict]:
    """List published problems (metadata only), paged (GET /problems)."""
    data = await _request("GET", "/problems", params={"page": page, "size": size})
    return data or []


async def get_problem(problem_id: str) -> dict:
    """Fetch one published problem's metadata + sample cases (GET /problems/:id)."""
    return await _request("GET", f"/problems/{quote(problem_id, safe='')}")


async def get_submission(submission_id: str) -> dict:
    """Fetch a submission's current status/verdict/cases (GET /submissions/:id)."""
    return await _request("GET", f"/submissions/{quote(submission_id, safe='')}")


# --- Admin (authoring) endpoints ---------------------------------------------
# DRAFT -> validate (reference solution ACs every case, run for real) -> PUBLISHED.
# See CodeJudge/docs/PROBLEM_AUTHORING.md for the full lifecycle.

async def create_draft_problem(problem: dict) -> dict:
    """Create a new problem in DRAFT status (POST /admin/problems).

    `problem` matches CreateProblemRequest: id, title, description, difficulty,
    tags, mode, signature, entryFunc, limits, cases (optional inline).
    """
    return await _request("POST", "/admin/problems", json=problem)


async def add_test_case(problem_id: str, stdin: str, expected_stdout: str, sample: bool = False) -> str:
    """Add one case to a draft (POST /admin/problems/:id/testcases). Returns its caseId."""
    data = await _request(
        "POST",
        f"/admin/problems/{quote(problem_id, safe='')}/testcases",
        json={"stdin": stdin, "expectedStdout": expected_stdout, "sample": sample},
    )
    return data.get("caseId", "")


async def set_reference_solution(problem_id: str, language: str, source_code: str) -> None:
    """Set/replace the answer-key solution (PUT /admin/problems/:id/reference)."""
    await _request(
        "PUT",
        f"/admin/problems/{quote(problem_id, safe='')}/reference",
        json={"language": language, "sourceCode": source_code},
    )


async def get_admin_problem(problem_id: str) -> dict:
    """Admin view: status, ALL cases, reference solution (GET /admin/problems/:id)."""
    return await _request("GET", f"/admin/problems/{quote(problem_id, safe='')}")


async def _poll_submission(submission_id: str, kind: str, timeout_s: float, poll_interval_s: float) -> dict:
    """Poll GET /submissions/:id until FINISHED/ERROR or timeout_s elapses.

    Shared by validate_problem and run_submission -- both endpoints just enqueue
    a submission and return an id; this is the deterministic wait-for-it half
    (D3), so the agent gets one clean result instead of hand-polling itself.
    """
    deadline = time.monotonic() + timeout_s
    while True:
        sub = await get_submission(submission_id)
        status_code = (sub.get("status") or {}).get("code")
        if status_code in ("FINISHED", "ERROR"):
            return sub
        if time.monotonic() >= deadline:
            raise PollTimeout(submission_id, kind, timeout_s)
        await asyncio.sleep(poll_interval_s)


async def validate_problem(problem_id: str, *, timeout_s: float = 60.0, poll_interval_s: float = 1.5) -> dict:
    """Run the reference solution against every STORED case, for real, and wait.

    This is the authoritative, final gate: it grades the persisted reference
    solution against the problem's persisted cases exactly as publish will
    check it. Raises PollTimeout if the run doesn't finish in time.
    """
    started = await _request("POST", f"/admin/problems/{quote(problem_id, safe='')}/validate")
    return await _poll_submission(started["validationSubmissionId"], "validation", timeout_s, poll_interval_s)


async def run_submission(
    problem_id: str,
    language: str,
    source_code: str,
    cases: list[dict],
    *,
    timeout_s: float = 60.0,
    poll_interval_s: float = 1.5,
) -> dict:
    """Run arbitrary code against arbitrary cases, unscored-if-uncompared
    (POST /submissions/run) -- a sandbox trial run that touches nothing
    persisted. Requires an existing problem_id (even a draft): the run borrows
    that problem's mode/signature/limits so it compiles/wraps/bounds identically
    to a real submission, only the cases differ.

    `cases` is a list of {"stdin": str, "expectedStdout": str} -- a case with a
    non-empty expectedStdout is scored (AC/WA); one without is output-only (runs
    but isn't scored). Never appears in submission history. Raises PollTimeout
    if the run doesn't finish in time.
    """
    started = await _request(
        "POST",
        "/submissions/run",
        json={"problemId": problem_id, "language": language, "sourceCode": source_code, "cases": cases},
    )
    return await _poll_submission(started["id"], "run", timeout_s, poll_interval_s)


async def publish_problem(problem_id: str) -> dict:
    """DRAFT -> PUBLISHED (POST /admin/problems/:id/publish). Requires a passing validation."""
    return await _request("POST", f"/admin/problems/{quote(problem_id, safe='')}/publish")


async def unpublish_problem(problem_id: str) -> dict:
    """PUBLISHED -> DRAFT (POST /admin/problems/:id/unpublish)."""
    return await _request("POST", f"/admin/problems/{quote(problem_id, safe='')}/unpublish")
