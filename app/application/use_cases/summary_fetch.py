"""Shared helpers for summary-focused use cases."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.logging_utils import get_logger
from app.domain.exceptions.domain_exceptions import ResourceNotFoundError

if TYPE_CHECKING:
    from app.application.ports import SummaryRepositoryPort

logger = get_logger(__name__)


async def fetch_summary_or_raise(
    summary_repository: SummaryRepositoryPort, summary_id: int
) -> dict[str, Any]:
    """Fetch summary by ID or raise ResourceNotFoundError."""
    logger.debug("fetch_summary", extra={"summary_id": summary_id})
    summary_data = await summary_repository.async_get_summary_by_id(summary_id)
    if not summary_data:
        msg = f"Summary with ID {summary_id} not found"
        raise ResourceNotFoundError(msg, details={"summary_id": summary_id})
    return summary_data
