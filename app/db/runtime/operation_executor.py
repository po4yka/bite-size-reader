"""Database execution primitives with retry, locking, and transactions."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import peewee

from app.core.logging_utils import get_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.db.rw_lock import AsyncRWLock


class DatabaseOperationExecutor:
    """Execute database operations with retries and application-level locking."""

    def __init__(
        self,
        *,
        database: peewee.SqliteDatabase,
        rw_lock: AsyncRWLock,
        operation_timeout: float,
        max_retries: int,
        logger: Any | None = None,
    ) -> None:
        self._database = database
        self._rw_lock = rw_lock
        self._operation_timeout = operation_timeout
        self._max_retries = max_retries
        self._logger = logger or get_logger(__name__)

    @property
    def database(self) -> peewee.SqliteDatabase:
        return self._database

    def connection_context(self) -> Any:
        return self._database.connection_context()

    async def async_execute(
        self,
        operation: Any,
        *args: Any,
        timeout: float | None = None,
        operation_name: str = "repository_operation",
        read_only: bool = False,
        **kwargs: Any,
    ) -> Any:
        return await self._safe_db_operation(
            operation,
            *args,
            timeout=timeout,
            operation_name=operation_name,
            read_only=read_only,
            **kwargs,
        )

    async def async_execute_transaction(
        self,
        operation: Any,
        *args: Any,
        timeout: float | None = None,
        operation_name: str = "repository_transaction",
        **kwargs: Any,
    ) -> Any:
        return await self._safe_db_transaction(
            operation,
            *args,
            timeout=timeout,
            operation_name=operation_name,
            **kwargs,
        )

    async def _retry_with_backoff(
        self,
        run_fn: Callable[[], Awaitable[Any]],
        *,
        timeout: float,
        operation_name: str,
        log_prefix: str,
    ) -> Any:
        retries = 0
        last_error: peewee.OperationalError | None = None

        while retries <= self._max_retries:
            try:
                return await asyncio.wait_for(run_fn(), timeout=timeout)
            except TimeoutError:
                self._logger.exception(
                    f"{log_prefix}_timeout",
                    extra={"operation": operation_name, "timeout": timeout, "retries": retries},
                )
                raise
            except peewee.OperationalError as exc:
                last_error = exc
                error_msg = str(exc).lower()
                if ("locked" in error_msg or "busy" in error_msg) and retries < self._max_retries:
                    retries += 1
                    wait_time = 0.1 * (2**retries)
                    self._logger.warning(
                        f"{log_prefix}_locked_retrying",
                        extra={
                            "operation": operation_name,
                            "retry": retries,
                            "max_retries": self._max_retries,
                            "wait_time": wait_time,
                            "error": str(exc),
                        },
                    )
                    await asyncio.sleep(wait_time)
                    continue
                self._logger.exception(
                    f"{log_prefix}_operational_error",
                    extra={"operation": operation_name, "retries": retries, "error": str(exc)},
                )
                raise
            except peewee.IntegrityError as exc:
                self._logger.exception(
                    f"{log_prefix}_integrity_error",
                    extra={"operation": operation_name, "error": str(exc)},
                )
                raise
            except Exception as exc:
                self._logger.exception(
                    f"{log_prefix}_unexpected_error",
                    extra={
                        "operation": operation_name,
                        "retries": retries,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    },
                )
                raise

        if last_error is not None:
            raise last_error
        msg = f"Database {log_prefix} {operation_name} failed after {self._max_retries} retries"
        raise RuntimeError(msg)

    async def _safe_db_operation(
        self,
        operation: Any,
        *args: Any,
        timeout: float | None = None,
        operation_name: str = "database_operation",
        read_only: bool = False,
        **kwargs: Any,
    ) -> Any:
        effective_timeout = timeout if timeout is not None else self._operation_timeout

        async def _run_with_lock() -> Any:
            def _op_wrapper() -> Any:
                with self._database.connection_context():
                    return operation(*args, **kwargs)

            if read_only:
                return await asyncio.shield(asyncio.to_thread(_op_wrapper))

            async with self._rw_lock.write_lock():
                return await asyncio.shield(asyncio.to_thread(_op_wrapper))

        return await self._retry_with_backoff(
            _run_with_lock,
            timeout=effective_timeout,
            operation_name=operation_name,
            log_prefix="db_operation",
        )

    async def _safe_db_transaction(
        self,
        operation: Any,
        *args: Any,
        timeout: float | None = None,
        operation_name: str = "database_transaction",
        **kwargs: Any,
    ) -> Any:
        effective_timeout = timeout if timeout is not None else self._operation_timeout

        async def _run_transaction() -> Any:
            async with self._rw_lock.write_lock():

                def _execute_in_transaction() -> Any:
                    with self._database.atomic() as txn:
                        try:
                            return operation(*args, **kwargs)
                        except BaseException:
                            txn.rollback()
                            raise

                return await asyncio.shield(asyncio.to_thread(_execute_in_transaction))

        return await self._retry_with_backoff(
            _run_transaction,
            timeout=effective_timeout,
            operation_name=operation_name,
            log_prefix="db_transaction",
        )
