"""A thin async HTTP client for CodeJudge's public API.

The only thing in codejudge-mcp that knows CodeJudge's wire shape; the tools talk
to CodeJudge exclusively through this client (D1: they never share a module, only
HTTP). Mirrors CodeJudge's envelopes: objects as {data:...}, errors as
{error:{code,message}}.
"""

from __future__ import annotations

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


async def healthz() -> None:
    """Raise if CodeJudge isn't reachable / healthy (GET /healthz)."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{config.CODEJUDGE_BASE_URL}/healthz")
    if resp.status_code != 200:
        raise CodeJudgeError(resp.status_code)


async def list_problems(page: int = 1, size: int = 20) -> list[dict]:
    """List problems (metadata only), paged (GET /problems).

    Returns the `data` array from CodeJudge's page envelope; raises
    CodeJudgeError on a non-2xx.
    """
    url = f"{config.CODEJUDGE_BASE_URL}/problems"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            url, params={"page": page, "size": size}, headers={"Accept": "application/json"}
        )
    if resp.status_code // 100 != 2:
        raise CodeJudgeError(resp.status_code)
    return resp.json().get("data") or []


async def get_problem(problem_id: str) -> dict:
    """Fetch one problem's metadata + sample cases (GET /problems/:id).

    Returns the unwrapped `data` object; raises CodeJudgeError on a non-2xx.
    """
    url = f"{config.CODEJUDGE_BASE_URL}/problems/{quote(problem_id, safe='')}"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(url, headers={"Accept": "application/json"})

    if resp.status_code // 100 != 2:
        code = message = ""
        try:
            err = resp.json().get("error", {})
            code, message = err.get("code", ""), err.get("message", "")
        except Exception:
            pass
        raise CodeJudgeError(resp.status_code, code, message)

    return resp.json().get("data", {})
