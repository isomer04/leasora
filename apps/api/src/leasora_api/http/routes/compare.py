"""Compare leases endpoint.

Clean code design:
- Route focuses on HTTP interface only
- Delegates comparison logic to the comparison service
- Uses domain exceptions (caught by middleware)

Route ordering note: FastAPI matches routes in registration order, and
``/history``/``/count`` are literal path segments while ``POST ""`` is a
different method entirely, so none of the three routes below can shadow
each other.
"""

import logging

from fastapi import APIRouter, Depends, Query

from leasora_api.http.deps import enforce_rate_limit
from leasora_api.schemas.request import CompareRequest
from leasora_api.schemas.response import (
    ComparisonCountResponse,
    ComparisonHistoryItem,
    ComparisonHistoryResponse,
    CompareResponse,
)
from leasora_api.services.compare.comparison_service import comparison_service
from leasora_api.services.compare.comparison_store import MAX_PAGE_SIZE, comparison_store

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "",
    response_model=CompareResponse,
    summary="Compare multiple leases",
    description="Identify differences and similarities between two leases",
    dependencies=[Depends(enforce_rate_limit)],
    responses={
        200: {"description": "Comparison complete with differences"},
        400: {"description": "Invalid lease IDs"},
        404: {"description": "One or more leases not found"},
        429: {"description": "Rate limit exceeded"},
    },
)
async def compare(request: CompareRequest) -> CompareResponse:
    """Compare exactly two leases and identify differences.

    Loads each lease's indexed chunks, groups them by clause type, and uses
    the LLM to identify meaningful differences for clause types shared by
    both leases. Clause types present in only one lease produce a
    deterministic "present/missing" difference without an LLM call.

    Args:
        request: Exactly two distinct lease IDs to compare (enforced by
            ``CompareRequest`` validation).

    Returns:
        Comparison results with differences and insights.

    Raises:
        ValidationError: If lease_ids are invalid (wrong count/duplicates).
        NotFoundError: If either lease has no indexed chunks.
    """
    response = await comparison_service.compare(request.lease_ids)
    # Persisting the comparison history is best-effort: a storage failure
    # (disk full, permission denied, etc.) must not replace the successful
    # comparison response. Log and continue.
    try:
        comparison_store.add(lease_ids=request.lease_ids)
    except OSError:
        logger.exception(
            "Failed to persist comparison history for leases %s",
            request.lease_ids,
        )
    return response


@router.get(
    "/count",
    response_model=ComparisonCountResponse,
    summary="Get total comparison count",
    description="Total number of comparisons ever run, for dashboard stats",
    responses={200: {"description": "Comparison count"}},
)
async def get_comparison_count() -> ComparisonCountResponse:
    """Return the total number of recorded comparisons.

    No rate limiting: the dashboard polls this on mount and it's a cheap
    read of local JSON, not an LLM call.
    """
    return ComparisonCountResponse(count=comparison_store.count())


@router.get(
    "/history",
    response_model=ComparisonHistoryResponse,
    summary="Get comparison history",
    description="Bounded, paginated page of past comparisons, most recent first",
    responses={200: {"description": "Comparison history page"}},
)
async def get_comparison_history(
    page: int = Query(default=1, ge=1, description="1-indexed page number"),
    page_size: int = Query(
        default=20, ge=1, le=MAX_PAGE_SIZE, description=f"Records per page (max {MAX_PAGE_SIZE})"
    ),
) -> ComparisonHistoryResponse:
    """Return a bounded page of comparison history.

    Args:
        page: 1-indexed page number.
        page_size: Records per page, capped at 100 regardless of request.

    Returns:
        The requested page of comparison records plus the total count.
    """
    items, total = comparison_store.list_page(page=page, page_size=page_size)
    return ComparisonHistoryResponse(
        items=[ComparisonHistoryItem.model_validate(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )
