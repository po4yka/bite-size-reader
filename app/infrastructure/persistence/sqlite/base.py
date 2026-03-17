from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.infrastructure.persistence.sqlite.protocol import DatabaseSessionProtocol


class SqliteBaseRepository:
    """Base repository for SQLite implementations."""

    def __init__(self, session_manager: DatabaseSessionProtocol) -> None:
        self._session = session_manager

    async def _execute(
        self,
        operation: Any,
        *args: Any,
        timeout: float | None = None,
        operation_name: str = "repository_operation",
        read_only: bool = False,
        **kwargs: Any,
    ) -> Any:
        """Execute a database operation safely using the session manager."""
        return await self._session.async_execute(
            operation,
            *args,
            timeout=timeout,
            operation_name=operation_name,
            read_only=read_only,
            **kwargs,
        )

    async def _execute_transaction(
        self,
        operation: Any,
        *args: Any,
        timeout: float | None = None,
        operation_name: str = "repository_transaction",
        **kwargs: Any,
    ) -> Any:
        """Execute a database operation inside a single transaction."""
        return await self._session.async_execute_transaction(
            operation,
            *args,
            timeout=timeout,
            operation_name=operation_name,
            **kwargs,
        )
