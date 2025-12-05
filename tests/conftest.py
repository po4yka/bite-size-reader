"""Pytest configuration and shared fixtures.

This module provides common fixtures for all tests.
"""

import os
import sys
import types
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pydantic.fields as pydantic_fields
import pytest

# Provide a lightweight FastAPI stub for environments without a compatible installation.
fastapi_stub = types.ModuleType("fastapi")


class _StubHTTPException(Exception):
    def __init__(self, status_code: int, detail: str | None = None):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail or "")


class _StubAPIRouter:
    def __init__(self, *args, **kwargs):
        pass

    def _noop(self, *args, **kwargs):
        def decorator(fn):
            return fn

        return decorator

    get = post = patch = delete = _noop


def _stub_depends(dep=None):
    return dep


class _StubRequest:
    def __init__(self):
        self.state = types.SimpleNamespace()
        self.url = types.SimpleNamespace(path="")


class _StubQuery:
    def __init__(self, default=None, **kwargs):
        self.default = default


class _StubBackgroundTasks:
    def add_task(self, *args, **kwargs):
        return None


status = types.SimpleNamespace(
    HTTP_400_BAD_REQUEST=400,
    HTTP_401_UNAUTHORIZED=401,
    HTTP_403_FORBIDDEN=403,
    HTTP_404_NOT_FOUND=404,
    HTTP_422_UNPROCESSABLE_ENTITY=422,
    HTTP_500_INTERNAL_SERVER_ERROR=500,
)


class _StubFastAPI:
    def __init__(self, *args, **kwargs):
        self.user_middleware = []

    def add_middleware(self, middleware_class, *args, **kwargs):
        class _Entry:
            def __init__(self, cls, kw):
                self.cls = cls
                self.kwargs = kw

            def __str__(self):
                return getattr(self.cls, "__name__", str(self.cls))

        self.user_middleware.append(_Entry(middleware_class, kwargs))

    def middleware(self, *args, **kwargs):
        def decorator(fn):
            return fn

        return decorator

    def include_router(self, *args, **kwargs):
        return None

    def add_exception_handler(self, *args, **kwargs):
        return None

    def get(self, *args, **kwargs):
        def decorator(fn):
            return fn

        return decorator


class _StubCORSMiddleware:
    def __init__(self, *args, **kwargs):
        pass


class _StubHTTPBearer:
    def __init__(self, *args, **kwargs):
        pass


class _StubHTTPAuthorizationCredentials: ...


fastapi_stub.APIRouter = _StubAPIRouter  # type: ignore
fastapi_stub.Depends = _stub_depends  # type: ignore
fastapi_stub.HTTPException = _StubHTTPException  # type: ignore
fastapi_stub.Request = _StubRequest  # type: ignore
fastapi_stub.status = status  # type: ignore
fastapi_stub.BackgroundTasks = _StubBackgroundTasks  # type: ignore
fastapi_stub.Query = _StubQuery  # type: ignore
fastapi_stub.FastAPI = _StubFastAPI  # type: ignore

security_module = types.ModuleType("fastapi.security")
security_module.HTTPBearer = _StubHTTPBearer  # type: ignore
security_module.HTTPAuthorizationCredentials = _StubHTTPAuthorizationCredentials  # type: ignore

middleware_module = types.ModuleType("fastapi.middleware")
cors_module = types.ModuleType("fastapi.middleware.cors")
cors_module.CORSMiddleware = _StubCORSMiddleware  # type: ignore
middleware_module.cors = cors_module  # type: ignore

responses_module = types.ModuleType("fastapi.responses")


class _StubResponse:
    def __init__(self, *args, **kwargs):
        self.content = kwargs.get("content")
        self.status_code = kwargs.get("status_code")


class _StubJSONResponse(_StubResponse): ...


responses_module.Response = _StubResponse  # type: ignore
responses_module.JSONResponse = _StubJSONResponse  # type: ignore

# Register stubs before importing application modules.
fastapi_stub.responses = responses_module  # type: ignore
sys.modules.setdefault("fastapi", fastapi_stub)
sys.modules.setdefault("fastapi.security", security_module)
sys.modules.setdefault("fastapi.middleware", middleware_module)
sys.modules.setdefault("fastapi.middleware.cors", cors_module)
sys.modules.setdefault("fastapi.responses", responses_module)

# FastAPI depends on pydantic.fields.Undefined (removed in pydantic v2); provide a shim.
if not hasattr(pydantic_fields, "Undefined"):
    pydantic_fields.Undefined = object()  # type: ignore[attr-defined, unused-ignore]

# Provide sane defaults for integration/API tests that expect these env vars.
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-32-characters-long-123456")
os.environ.setdefault("BOT_TOKEN", "test_token")
os.environ.setdefault("ALLOWED_USER_IDS", "123456789")


@pytest.fixture(autouse=True)
def mock_chroma_client():
    """Mock ChromaDB client to prevent connection attempts."""
    # Avoid importing the real chromadb package (pydantic v1 dependency) during tests.
    chroma_stub = MagicMock()
    chroma_stub.HttpClient = MagicMock()
    sys.modules["chromadb"] = chroma_stub

    with patch("app.infrastructure.vector.chroma_store.chromadb.HttpClient") as mock_client:
        mock_instance = MagicMock()
        mock_client.return_value = mock_instance
        yield mock_instance


class MockSummaryRepository:
    """Mock summary repository for testing."""

    def __init__(self):
        """Initialize mock repository."""
        self.summaries: dict[int, dict[str, Any]] = {}
        self.next_id = 1

    async def async_upsert_summary(
        self,
        request_id: int,
        lang: str,
        json_payload: dict[str, Any],
        insights_json: dict[str, Any] | None = None,
        is_read: bool = False,
    ) -> int:
        """Mock upsert summary."""
        self.summaries[request_id] = {
            "id": self.next_id,
            "request_id": request_id,
            "lang": lang,
            "json_payload": json_payload,
            "insights_json": insights_json,
            "is_read": is_read,
            "version": 1,
            "created_at": datetime.utcnow(),
        }
        summary_id = self.next_id
        self.next_id += 1
        return summary_id

    async def async_get_summary_by_request(self, request_id: int) -> dict[str, Any] | None:
        """Mock get summary by request."""
        return self.summaries.get(request_id)

    async def async_get_unread_summaries(
        self,
        uid: int | None,
        cid: int | None,
        limit: int = 10,
        topic: str | None = None,
    ) -> list[dict[str, Any]]:
        """Mock get unread summaries."""
        unread = [
            summary for summary in self.summaries.values() if not summary.get("is_read", False)
        ]
        if topic:
            topic_lower = topic.casefold()
            unread = [
                summary
                for summary in unread
                if topic_lower in str(summary["json_payload"]).casefold()
            ]
        return unread[:limit]

    async def async_mark_summary_as_read(self, summary_id: int) -> None:
        """Mock mark summary as read."""
        for summary in self.summaries.values():
            if summary.get("id") == summary_id:
                summary["is_read"] = True
                break

    def to_domain_model(self, db_summary: dict[str, Any]) -> Any:
        """Mock conversion to domain model."""
        from app.domain.models.summary import Summary

        return Summary(
            id=db_summary.get("id"),
            request_id=db_summary["request_id"],
            content=db_summary["json_payload"],
            language=db_summary["lang"],
            version=db_summary.get("version", 1),
            is_read=db_summary.get("is_read", False),
            insights=db_summary.get("insights_json"),
            created_at=db_summary.get("created_at", datetime.utcnow()),
        )


@pytest.fixture
def mock_summary_repository():
    """Provide a mock summary repository."""
    return MockSummaryRepository()
