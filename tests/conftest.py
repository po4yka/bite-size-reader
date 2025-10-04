"""Pytest configuration and lightweight stubs for optional dependencies."""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import json
import sys
from types import ModuleType, TracebackType
from typing import Any

import pytest


def _ensure_httpx_stub() -> None:
    """Provide a very small httpx stub when the package is unavailable."""

    if importlib.util.find_spec("httpx") is not None:
        return

    class _Timeout:
        def __init__(
            self,
            timeout: float | None = None,
            *,
            connect: float | None = None,
            read: float | None = None,
            write: float | None = None,
            pool: float | None = None,
        ) -> None:
            self.timeout = timeout
            self.connect_timeout = connect if connect is not None else timeout
            self.read_timeout = read if read is not None else timeout
            self.write_timeout = write if write is not None else timeout
            self.pool_timeout = pool if pool is not None else timeout

    class _Limits:
        def __init__(
            self,
            *,
            max_connections: int | None = None,
            max_keepalive_connections: int | None = None,
            keepalive_expiry: float | None = None,
        ) -> None:
            self.max_connections = max_connections
            self.max_keepalive_connections = max_keepalive_connections
            self.keepalive_expiry = keepalive_expiry

    class _BaseHttpxError(Exception):
        """Base exception matching the httpx hierarchy."""

    class _RequestError(_BaseHttpxError):
        def __init__(self, message: str, *, request: Any | None = None) -> None:
            super().__init__(message)
            self.request = request

    class _TimeoutError(_RequestError):
        pass

    class _ConnectError(_RequestError):
        pass

    class _HTTPStatusError(_RequestError):
        def __init__(
            self,
            message: str,
            *,
            request: Any | None = None,
            response: Any | None = None,
        ) -> None:
            super().__init__(message, request=request)
            self.response = response

    class _Response:
        def __init__(
            self,
            status_code: int,
            *,
            json_data: Any | None = None,
            text: str = "",
            headers: dict[str, str] | None = None,
        ) -> None:
            self.status_code = status_code
            self._json_data = json_data
            self.text = text
            self.headers = headers or {}

        def json(self) -> Any:
            if self._json_data is not None:
                return self._json_data
            if self.text:
                return json.loads(self.text)
            raise ValueError("No JSON content available")

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise _HTTPStatusError(f"HTTP {self.status_code}", response=self)

    class _AsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.args = args
            self.kwargs = kwargs
            self._closed = False

        async def __aenter__(self) -> _AsyncClient:
            return self

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> bool:
            await self.aclose()
            return False

        async def post(self, *args: Any, **kwargs: Any) -> _Response:  # noqa: D401
            raise NotImplementedError("httpx stub client does not perform HTTP calls")

        async def get(self, *args: Any, **kwargs: Any) -> _Response:
            raise NotImplementedError("httpx stub client does not perform HTTP calls")

        async def aclose(self) -> None:
            self._closed = True

    stub = ModuleType("httpx")
    setattr(stub, "AsyncClient", _AsyncClient)
    setattr(stub, "Timeout", _Timeout)
    setattr(stub, "Limits", _Limits)
    setattr(stub, "TimeoutException", _TimeoutError)
    setattr(stub, "ConnectError", _ConnectError)
    setattr(stub, "HTTPStatusError", _HTTPStatusError)
    setattr(stub, "RequestError", _RequestError)
    setattr(stub, "Response", _Response)
    stub.__dict__["__all__"] = [
        "AsyncClient",
        "Timeout",
        "Limits",
        "TimeoutException",
        "ConnectError",
        "HTTPStatusError",
        "RequestError",
        "Response",
    ]
    stub.__dict__["__version__"] = "0.0-stub"

    sys.modules["httpx"] = stub


_ensure_httpx_stub()


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers used throughout the suite."""

    config.addinivalue_line("markers", "asyncio: mark test to run in an event loop")


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    """Execute ``async def`` tests without requiring pytest-asyncio."""

    test_func = pyfuncitem.obj
    if asyncio.iscoroutinefunction(test_func):
        signature = inspect.signature(test_func)
        has_var_kwargs = any(
            param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()
        )
        if has_var_kwargs:
            call_args = pyfuncitem.funcargs
        else:
            allowed = set(signature.parameters)
            call_args = {k: v for k, v in pyfuncitem.funcargs.items() if k in allowed}

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(test_func(**call_args))
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
        return True
    return None
