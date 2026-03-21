from __future__ import annotations

import asyncio
from typing import Any

from app.api.dependencies.database import (
    get_crawl_result_repository,
    get_llm_repository,
    get_request_repository,
    get_summary_repository,
)
from app.application.services.request_service import RequestService


class _RawDatabaseSessionAdapter:
    def __init__(self, db) -> None:
        self._db = db

    async def async_execute(
        self,
        operation,
        *args,
        timeout=None,
        operation_name: str = "repository_operation",
        read_only: bool = False,
        **kwargs,
    ):
        del timeout, operation_name, read_only

        def _run():
            with self._db.connection_context():
                return operation(*args, **kwargs)

        return await asyncio.to_thread(_run)

    async def async_execute_transaction(
        self,
        operation,
        *args,
        timeout=None,
        operation_name: str = "repository_transaction",
        **kwargs,
    ):
        del timeout, operation_name

        def _run():
            with self._db.connection_context():
                with self._db.atomic():
                    return operation(*args, **kwargs)

        return await asyncio.to_thread(_run)


def build_request_service(db: Any) -> RequestService:
    session: Any = db if hasattr(db, "async_execute") else _RawDatabaseSessionAdapter(db)
    return RequestService(
        db=db,
        request_repository=get_request_repository(session),
        summary_repository=get_summary_repository(session),
        crawl_result_repository=get_crawl_result_repository(session),
        llm_repository=get_llm_repository(session),
    )
