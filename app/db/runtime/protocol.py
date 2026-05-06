"""Protocols for database runtime services."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DatabaseExecutorPort(Protocol):
    """Minimal database-execution surface required by repository adapters."""

    @property
    def database(self) -> Any:
        """Underlying SQLAlchemy session factory."""
        ...

    def connection_context(self) -> Any:
        """Legacy connection context; unavailable after the SQLAlchemy cutover."""
        ...

    async def async_execute(
        self,
        operation: Any,
        *args: Any,
        timeout: float | None = None,
        operation_name: str = "repository_operation",
        read_only: bool = False,
        **kwargs: Any,
    ) -> Any:
        """Execute a database operation with timeout and retry protection."""
        ...

    async def async_execute_transaction(
        self,
        operation: Any,
        *args: Any,
        timeout: float | None = None,
        operation_name: str = "repository_transaction",
        **kwargs: Any,
    ) -> Any:
        """Execute a database operation inside a transaction."""
        ...
