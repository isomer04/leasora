"""Legacy eval endpoint.

The previous implementation was a placeholder that returned a static
"evaluation integration" message without ever performing any evaluation.
That was a dead contract: nothing in the codebase reads from this
endpoint, and the real eval work happens in the CLI
(``leasora-eval``) and CI workflow (``.github/workflows/ci.yml``).

We replace the response with a 501 so a stale client/cron hitting
``POST /eval`` learns that the endpoint is intentionally unimplemented
instead of receiving fake success data. Removing the route entirely
would return a 404 from Starlette, which is also acceptable but loses
the explicit "this used to exist" signal.
"""

from fastapi import APIRouter

router = APIRouter()


@router.post(
    "/",
    summary="Deprecated eval endpoint (returns 501)",
    description=(
        "Intentionally unimplemented. The eval suite lives in "
        "``leasora-eval`` (CLI) and the nightly ``evals`` CI job."
    ),
    status_code=501,
    responses={501: {"description": "Not implemented; use the eval CLI/CI instead"}},
)
async def run_eval() -> dict[str, str]:
    """Return 501 — see module docstring for context."""
    return {
        "status": "not_implemented",
        "message": (
            "Eval integration endpoint has been removed. "
            "Run the eval suite via `leasora-eval` (CLI) or the nightly "
            "CI workflow instead."
        ),
    }