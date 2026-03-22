from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.content.cached_summary_responder import CachedSummaryResponder


def _make_responder(
    *,
    request_row: dict[str, Any] | None,
    cached_row: dict[str, Any] | None,
) -> tuple[CachedSummaryResponder, Any, Any, Any]:
    cfg = SimpleNamespace(openrouter=SimpleNamespace(model="test", structured_output_mode="json"))
    response_formatter = SimpleNamespace(
        send_cached_summary_notification=AsyncMock(),
        send_structured_summary_response=AsyncMock(),
    )
    request_repo = SimpleNamespace(
        async_get_request_by_dedupe_hash=AsyncMock(return_value=request_row),
        async_update_request_correlation_id=AsyncMock(),
    )
    summary_repo = SimpleNamespace(async_get_summary_by_request=AsyncMock(return_value=cached_row))
    responder = CachedSummaryResponder(
        cfg=cfg,
        db=MagicMock(),
        response_formatter=response_formatter,  # type: ignore[arg-type]
        request_repo=request_repo,
        summary_repo=summary_repo,
    )
    return responder, response_formatter, request_repo, summary_repo


@pytest.mark.asyncio
async def test_dict_payload_replies_and_updates_correlation() -> None:
    responder, formatter, request_repo, _summary_repo = _make_responder(
        request_row={"id": 5},
        cached_row={"json_payload": {"summary_250": "Cached", "tldr": "Cached"}},
    )

    result = await responder.maybe_reply(
        SimpleNamespace(),
        "https://example.com",
        correlation_id="cid-1",
    )

    assert result is not None
    assert result.cached is True
    formatter.send_cached_summary_notification.assert_awaited_once()
    formatter.send_structured_summary_response.assert_awaited_once()
    request_repo.async_update_request_correlation_id.assert_awaited_once_with(5, "cid-1")


@pytest.mark.asyncio
async def test_string_payload_is_decoded() -> None:
    responder, formatter, _request_repo, _summary_repo = _make_responder(
        request_row={"id": 7},
        cached_row={"json_payload": '{"summary_250": "Decoded", "tldr": "Decoded"}'},
    )

    result = await responder.maybe_reply(SimpleNamespace(), "https://example.com/decoded")

    assert result is not None
    assert result.summary_json is not None
    assert result.summary_json["summary_250"] == "Decoded"
    formatter.send_structured_summary_response.assert_awaited_once()


@pytest.mark.asyncio
async def test_bad_json_payload_falls_through() -> None:
    responder, formatter, _request_repo, _summary_repo = _make_responder(
        request_row={"id": 9},
        cached_row={"json_payload": "{not-json"},
    )

    result = await responder.maybe_reply(SimpleNamespace(), "https://example.com/bad")

    assert result is None
    formatter.send_cached_summary_notification.assert_not_called()
    formatter.send_structured_summary_response.assert_not_called()


@pytest.mark.asyncio
async def test_silent_cache_hit_skips_notifications_and_updates_interaction() -> None:
    responder, formatter, _request_repo, _summary_repo = _make_responder(
        request_row={"id": 11},
        cached_row={"json_payload": {"summary_250": "Silent", "tldr": "Silent"}},
    )

    with patch(
        "app.adapters.content.cached_summary_responder.async_safe_update_user_interaction",
        new=AsyncMock(),
    ) as update_interaction:
        result = await responder.maybe_reply(
            SimpleNamespace(),
            "https://example.com/silent",
            interaction_id=99,
            silent=True,
        )

    assert result is not None
    assert result.request_id == 11
    formatter.send_cached_summary_notification.assert_not_called()
    formatter.send_structured_summary_response.assert_not_called()
    update_interaction.assert_awaited_once()
