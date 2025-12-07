from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from app.adapters.external.firecrawl_parser import (
    FIRECRAWL_CRAWL_URL,
    FIRECRAWL_SCRAPE_ENDPOINT,
    FirecrawlClient,
)


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.headers: dict[str, str] = {}

    def json(self) -> dict:
        return self._payload


@pytest.mark.asyncio
async def test_scrape_builds_formats_and_options(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FirecrawlClient(
        api_key="fc-test",
        include_links_format=True,
        include_summary_format=True,
        include_images_format=True,
        enable_screenshot_format=True,
        screenshot_full_page=False,
        screenshot_quality=90,
        screenshot_viewport_width=1200,
        screenshot_viewport_height=800,
        json_prompt="Extract",
        max_age_seconds=100,
        remove_base64_images=False,
        block_ads=False,
        skip_tls_verification=False,
    )

    payload = {
        "markdown": "md",
        "html": "<p>h</p>",
        "summary": "short summary",
        "links": ["https://example.com/other"],
        "screenshots": [{"url": "s1.png"}],
        "metadata": {"foo": "bar"},
        "success": True,
    }
    fake_resp = _FakeResponse(payload)
    post = AsyncMock(return_value=fake_resp)
    cast("Any", client._client).post = post

    result = await client.scrape_markdown("https://example.com", request_id=123)

    called_payload = post.call_args.kwargs["json"]
    assert called_payload["maxAge"] == 100
    assert called_payload["removeBase64Images"] is False
    assert called_payload["blockAds"] is False
    assert called_payload["skipTlsVerification"] is False
    formats = called_payload["formats"]
    assert "markdown" in formats
    assert "html" in formats
    assert "links" in formats
    assert "summary" in formats
    assert any(f for f in formats if isinstance(f, dict) and f.get("type") == "json")
    screenshot_fmt = next(
        f for f in formats if isinstance(f, dict) and f.get("type") == "screenshot"
    )
    assert screenshot_fmt["quality"] == 90
    assert screenshot_fmt["fullPage"] is False
    assert screenshot_fmt["viewport"] == {"width": 1200, "height": 800}

    assert result.endpoint == FIRECRAWL_SCRAPE_ENDPOINT
    assert result.metadata_json is not None
    assert result.metadata_json.get("summary_text") == "short summary"
    assert isinstance(result.metadata_json.get("screenshots"), list)


@pytest.mark.asyncio
async def test_crawl_waiter_returns_completed(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FirecrawlClient(api_key="fc-test")

    start_resp = _FakeResponse({"jobId": "abc123"})
    poll_pending = _FakeResponse({"status": "pending"})
    poll_done = _FakeResponse({"status": "completed", "result": {"ok": True}})

    post = AsyncMock(side_effect=[start_resp])
    get = AsyncMock(side_effect=[poll_pending, poll_done])
    cast("Any", client._client).post = post
    cast("Any", client._client).get = get

    result = await client.crawl("https://example.com", poll_interval=0.01, timeout_sec=2)

    assert result["status"] == "completed"
    assert post.call_args.args[0] == FIRECRAWL_CRAWL_URL
    payload = post.call_args.kwargs["json"]
    assert "formats" in payload
    assert "markdown" in payload["formats"]
    assert get.call_count >= 1
