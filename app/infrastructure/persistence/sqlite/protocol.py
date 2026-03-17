"""Protocol for SQLite session managers used by repository adapters."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DatabaseSessionProtocol(Protocol):
    """Minimal interface expected by SqliteBaseRepository from a session manager."""

    @property
    def database(self) -> Any:
        """Peewee Database proxy, used by some repositories for raw SQL."""
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
        """Execute a database operation with timeout and connection protection."""
        ...

    async def async_execute_transaction(
        self,
        operation: Any,
        *args: Any,
        timeout: float | None = None,
        operation_name: str = "repository_transaction",
        **kwargs: Any,
    ) -> Any:
        """Execute a database operation inside a single transaction."""
        ...
