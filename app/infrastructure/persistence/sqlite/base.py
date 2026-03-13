import asyncio
from typing import Any

from app.db.session import DatabaseSessionManager


class SqliteBaseRepository:
    """Base repository for SQLite implementations."""

    def __init__(self, session_manager: DatabaseSessionManager | Any) -> None:
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
        if hasattr(self._session, "_safe_db_operation"):
            return await self._session._safe_db_operation(
                operation,
                *args,
                timeout=timeout,
                operation_name=operation_name,
                read_only=read_only,
                **kwargs,
            )

        if hasattr(self._session, "connection_context"):

            def _op_wrapper() -> Any:
                # Use getattr and Any to satisfy MyPy for union types
                session_any: Any = self._session
                ctx_manager: Any = session_any.connection_context()
                with ctx_manager:
                    return operation(*args, **kwargs)

            return await asyncio.to_thread(_op_wrapper)

        msg = "Unsupported session manager type for repository execution"
        raise TypeError(msg)

    async def _execute_transaction(
        self,
        operation: Any,
        *args: Any,
        timeout: float | None = None,
        operation_name: str = "repository_transaction",
        **kwargs: Any,
    ) -> Any:
        """Execute a database operation inside a single transaction."""
        if hasattr(self._session, "_safe_db_transaction"):
            return await self._session._safe_db_transaction(
                operation,
                *args,
                timeout=timeout,
                operation_name=operation_name,
                **kwargs,
            )

        if hasattr(self._session, "connection_context") and hasattr(self._session, "atomic"):

            def _op_wrapper() -> Any:
                session_any: Any = self._session
                ctx_manager: Any = session_any.connection_context()
                atomic_ctx: Any = session_any.atomic()
                with ctx_manager, atomic_ctx:
                    return operation(*args, **kwargs)

            return await asyncio.to_thread(_op_wrapper)

        msg = "Unsupported session manager type for repository transaction"
        raise TypeError(msg)
