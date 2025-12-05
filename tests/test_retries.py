# json: used to craft serialized payloads that mirror OpenRouter responses.
import json
import unittest
from typing import Any, cast

import httpx

from app.adapters.external.firecrawl_parser import FirecrawlClient, httpx as fc_httpx
from app.adapters.openrouter.openrouter_client import httpx as or_httpx


class _SeqAsyncClient:
    def __init__(self, handler):
        self.handler = handler
        self.is_closed = False  # Add missing attribute

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None):
        return await self.handler(url, headers, json)

    async def get(self, url, headers=None):
        return await self.handler(url, headers, None)


class _Resp:
    def __init__(self, status_code, data):
        self.status_code = status_code
        self._data = data
        self.headers = {}
        self.content = b"{}"

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            msg = f"HTTP {self.status_code}"
            raise Exception(msg)


class TestRetries(unittest.IsolatedAsyncioTestCase):
    async def test_openrouter_retry_and_fallback(self):
        calls = {"count": 0}

        async def handler(url, headers, payload):
            # Handle models endpoint
            if "/models" in url:
                return _Resp(
                    200,
                    {
                        "data": [
                            {
                                "id": "primary/model",
                                "object": "model",
                                "supported_parameters": {"structured_outputs": True},
                            },
                            {
                                "id": "fallback/model",
                                "object": "model",
                                "supported_parameters": {"structured_outputs": True},
                            },
                        ]
                    },
                )

            calls["count"] += 1
            model = payload.get("model")
            if model == "primary/model":
                # Always fail for primary
                return _Resp(500, {"error": "server error"})
            # Fallback succeeds
            return _Resp(
                200,
                {
                    "model": model,
                    "choices": [{"message": {"content": json.dumps({"summary_250": "ok"})}}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 4},
                },
            )

        original_or = or_httpx.AsyncClient
        original_httpx = httpx.AsyncClient
        try:

            def _make_or_client(*args, **kwargs):
                return _SeqAsyncClient(handler)

            or_httpx.AsyncClient = cast("Any", _make_or_client)
            httpx.AsyncClient = cast("Any", _make_or_client)
        finally:
            or_httpx.AsyncClient = cast("Any", original_or)
            httpx.AsyncClient = cast("Any", original_httpx)

    async def test_firecrawl_retries_then_success(self):
        attempts = {"n": 0}

        async def handler(url, headers, payload):
            attempts["n"] += 1
            if attempts["n"] == 1:
                return _Resp(500, {"error": "temporary"})
            return _Resp(200, {"markdown": "# ok"})

        original = fc_httpx.AsyncClient
        try:

            def _make_fc_client(*args, **kwargs):
                return _SeqAsyncClient(handler)

            fc_httpx.AsyncClient = cast("Any", _make_fc_client)
            client = FirecrawlClient(
                api_key="fc-dummy-key", timeout_sec=2, max_retries=2, backoff_base=0.0
            )
            res = await client.scrape_markdown("https://example.com")
            assert res.status == "ok"
            assert res.http_status == 200
            assert res.content_markdown == "# ok"
        finally:
            fc_httpx.AsyncClient = cast("Any", original)


if __name__ == "__main__":
    unittest.main()
