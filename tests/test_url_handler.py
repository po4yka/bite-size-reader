from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.telegram.url_handler import URLHandler

if TYPE_CHECKING:
    from app.adapters.content.url_processor import URLProcessor
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.db.database import Database
else:  # pragma: no cover - runtime fallback for typing-only imports
    URLProcessor = ResponseFormatter = Database = Any  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_handle_awaited_url_rejects_invalid_links() -> None:
    safe_reply_mock = AsyncMock()
    response_formatter = cast(
        "ResponseFormatter",
        SimpleNamespace(
            MAX_BATCH_URLS=5,
            safe_reply=safe_reply_mock,
            _validate_url=MagicMock(return_value=(False, "bad")),
        ),
    )
    handle_url_flow_mock = AsyncMock()
    url_processor = cast(
        "URLProcessor",
        SimpleNamespace(handle_url_flow=handle_url_flow_mock),
    )
    handler = URLHandler(
        db=cast("Database", SimpleNamespace()),
        response_formatter=response_formatter,
        url_processor=url_processor,
    )

    message = SimpleNamespace(chat=None)

    await handler.handle_awaited_url(
        message,
        "https://localhost/resource",
        uid=99,
        correlation_id="cid",
        interaction_id=0,
        start_time=0.0,
    )

    assert safe_reply_mock.await_count == 1
    assert handle_url_flow_mock.await_count == 0


@pytest.mark.asyncio
async def test_handle_awaited_url_filters_invalid_before_processing() -> None:
    safe_reply_mock = AsyncMock()
    response_formatter = cast(
        "ResponseFormatter",
        SimpleNamespace(
            MAX_BATCH_URLS=5,
            safe_reply=safe_reply_mock,
            _validate_url=MagicMock(side_effect=[(True, ""), (False, "bad")]),
        ),
    )
    handle_url_flow_mock = AsyncMock()
    url_processor = cast(
        "URLProcessor",
        SimpleNamespace(handle_url_flow=handle_url_flow_mock),
    )
    handler = URLHandler(
        db=cast("Database", SimpleNamespace()),
        response_formatter=response_formatter,
        url_processor=url_processor,
    )
    multi_link_mock = AsyncMock()
    cast("Any", handler)._request_multi_link_confirmation = multi_link_mock

    message = SimpleNamespace(chat=None)

    await handler.handle_awaited_url(
        message,
        "https://valid.example/path https://localhost/resource",
        uid=42,
        correlation_id="cid",
        interaction_id=0,
        start_time=0.0,
    )

    assert handle_url_flow_mock.await_count == 1
    assert multi_link_mock.await_count == 0
    assert safe_reply_mock.await_count == 0
