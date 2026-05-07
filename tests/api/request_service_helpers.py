"""Helper for constructing a RequestService bound to the test Database."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.api.dependencies.database import (
    get_crawl_result_repository,
    get_llm_repository,
    get_request_repository,
    get_summary_repository,
)
from app.application.services.request_service import RequestService

if TYPE_CHECKING:
    from app.db.session import Database


def build_request_service(db: Database) -> RequestService:
    """Build a RequestService backed by the supplied async Database.

    Repositories created here resolve their session via the Database's
    async_execute interface; no adapter wrapping is needed.
    """
    return RequestService(
        db=db,
        request_repository=get_request_repository(db),
        summary_repository=get_summary_repository(db),
        crawl_result_repository=get_crawl_result_repository(db),
        llm_repository=get_llm_repository(db),
    )
