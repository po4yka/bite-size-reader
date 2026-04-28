from __future__ import annotations

import asyncio
import contextvars
import json
import sys
from types import ModuleType, SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.api.routers.auth.tokens import create_access_token
from app.config import load_config
from app.db.models import User
from app.di.repositories import build_aggregation_session_repository
from app.mcp.aggregation_service import AggregationMcpService
from app.mcp.context import McpServerContext
from app.mcp.http_auth import McpHttpAuthMiddleware
from app.mcp.resource_registrations import register_resources

pytest_plugins = ("tests.mcp_test_support",)

if TYPE_CHECKING:
    from collections.abc import Callable


class RecordingMCP:
    def __init__(self) -> None:
        self.resources: dict[str, Callable[..., Any]] = {}
        self.resource_uris: list[str] = []

    def resource(self, uri: str, *_args: Any, **_kwargs: Any):
        def decorator(fn):
            self.resources[fn.__name__] = fn
            self.resource_uris.append(uri)
            return fn

        return decorator


def _fake_api_runtime(db) -> SimpleNamespace:
    return SimpleNamespace(
        cfg=load_config(allow_stub_telegram=True),
        db=db,
        background_processor=SimpleNamespace(
            url_processor=SimpleNamespace(content_extractor=MagicMock())
        ),
        core=SimpleNamespace(llm_client=MagicMock()),
    )


@pytest.mark.asyncio
async def test_aggregation_detail_resource_returns_session_payload() -> None:
    mcp = RecordingMCP()
    aggregation_service = SimpleNamespace(
        list_aggregation_bundles=AsyncMock(return_value={"sessions": []}),
        get_aggregation_bundle=AsyncMock(return_value={"session": {"id": 42}}),
    )
    article_service = SimpleNamespace(
        list_articles=MagicMock(return_value={"items": []}),
        unread_articles=MagicMock(return_value={"items": []}),
        get_stats=MagicMock(return_value={"total": 1}),
        tag_counts=MagicMock(return_value={"items": []}),
        entity_counts=MagicMock(return_value={"items": []}),
        domain_counts=MagicMock(return_value={"items": []}),
    )
    catalog_service = SimpleNamespace(
        list_collections=MagicMock(return_value={"items": []}),
        list_videos=MagicMock(return_value={"items": []}),
        processing_stats=MagicMock(return_value={"jobs": 0}),
    )
    semantic_service = SimpleNamespace(
        chroma_health=AsyncMock(return_value={"status": "ok"}),
        chroma_index_stats=AsyncMock(return_value={"coverage": 1.0}),
        chroma_sync_gap=AsyncMock(return_value={"gap": 0}),
    )

    register_resources(
        mcp,
        aggregation_service=cast("Any", aggregation_service),
        article_service=cast("Any", article_service),
        catalog_service=cast("Any", catalog_service),
        semantic_service=cast("Any", semantic_service),
    )

    payload = await mcp.resources["aggregation_bundle_resource"]("42")

    assert json.loads(payload)["session"]["id"] == 42
    assert "ratatoskr://aggregations/{session_id}" in mcp.resource_uris


def test_hosted_mcp_resource_uses_request_scoped_identity(mcp_test_db, monkeypatch) -> None:
    user_id = 4101
    User.create(telegram_user_id=user_id, username="resource-user", is_owner=False)

    repo = build_aggregation_session_repository(mcp_test_db)
    session_id = asyncio.run(
        repo.async_create_aggregation_session(
            user_id=user_id,
            correlation_id="cid-resource-scope",
            total_items=1,
            bundle_metadata={"entrypoint": "mcp"},
        )
    )

    context = McpServerContext(user_id=None)
    context.ensure_api_runtime = AsyncMock(return_value=_fake_api_runtime(mcp_test_db))  # type: ignore[method-assign]
    aggregation_service = AggregationMcpService(context)
    mcp = RecordingMCP()

    article_service = SimpleNamespace(
        list_articles=MagicMock(return_value={"items": []}),
        unread_articles=MagicMock(return_value={"items": []}),
        get_stats=MagicMock(return_value={"total": 1}),
        tag_counts=MagicMock(return_value={"items": []}),
        entity_counts=MagicMock(return_value={"items": []}),
        domain_counts=MagicMock(return_value={"items": []}),
    )
    catalog_service = SimpleNamespace(
        list_collections=MagicMock(return_value={"items": []}),
        list_videos=MagicMock(return_value={"items": []}),
        processing_stats=MagicMock(return_value={"jobs": 0}),
    )
    semantic_service = SimpleNamespace(
        chroma_health=AsyncMock(return_value={"status": "ok"}),
        chroma_index_stats=AsyncMock(return_value={"coverage": 1.0}),
        chroma_sync_gap=AsyncMock(return_value={"gap": 0}),
    )

    register_resources(
        mcp,
        aggregation_service=aggregation_service,
        article_service=cast("Any", article_service),
        catalog_service=cast("Any", catalog_service),
        semantic_service=cast("Any", semantic_service),
    )

    lowlevel_module = ModuleType("mcp.server.lowlevel.server")
    request_ctx: contextvars.ContextVar[object] = contextvars.ContextVar("request_ctx")
    lowlevel_any: Any = lowlevel_module
    lowlevel_any.request_ctx = request_ctx
    monkeypatch.setitem(sys.modules, "mcp.server.lowlevel.server", lowlevel_module)
    monkeypatch.setenv("ALLOWED_USER_IDS", str(user_id))
    monkeypatch.setenv("ALLOWED_CLIENT_IDS", "mcp-public-v1")

    async def bundle_resource(request):
        token = request_ctx.set(SimpleNamespace(request=request))
        try:
            payload = await mcp.resources["aggregation_bundle_resource"](str(session_id))
        finally:
            request_ctx.reset(token)
        return JSONResponse(json.loads(payload))

    token = create_access_token(
        user_id=user_id, client_id="mcp-public-v1", username="resource-user"
    )
    app = Starlette(routes=[Route("/resource", bundle_resource)])
    app_asgi = McpHttpAuthMiddleware(
        app,
        forwarded_access_token_header="X-Ratatoskr-Forwarded-Access-Token",
        forwarded_secret_header="X-Ratatoskr-MCP-Forwarding-Secret",
        forwarding_secret=None,
    )

    with TestClient(app_asgi) as client:
        response = client.get("/resource", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["session"]["id"] == session_id
    assert payload["session"]["user"] == user_id
