import json
import unittest

from app.adapters.firecrawl_parser import FirecrawlClient, httpx as fc_httpx
from app.adapters.openrouter_client import OpenRouterClient, httpx as or_httpx


class _SeqAsyncClient:
    def __init__(self, handler):
        self.handler = handler

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None):  # noqa: A002
        return await self.handler(url, headers, json)


class _Resp:
    def __init__(self, status_code, data):
        self.status_code = status_code
        self._data = data

    def json(self):
        return self._data


class TestRetries(unittest.IsolatedAsyncioTestCase):
    async def test_openrouter_retry_and_fallback(self):
        calls = {"count": 0}

        async def handler(url, headers, payload):
            calls["count"] += 1
            model = payload.get("model")
            if model == "primary/model":
                # Always fail for primary
                return _Resp(500, {"error": "server error"})
            else:
                # Fallback succeeds
                return _Resp(
                    200,
                    {
                        "model": model,
                        "choices": [{"message": {"content": json.dumps({"summary_250": "ok"})}}],
                        "usage": {"prompt_tokens": 3, "completion_tokens": 4},
                    },
                )

        original = or_httpx.AsyncClient
        try:
            or_httpx.AsyncClient = lambda timeout=None: _SeqAsyncClient(handler)  # type: ignore[assignment]
            client = OpenRouterClient(
                api_key="k",
                model="primary/model",
                fallback_models=["fallback/model"],
                timeout_sec=2,
                max_retries=1,
                backoff_base=0.0,
            )
            res = await client.chat([{"role": "user", "content": "hi"}])
            self.assertEqual(res.status, "ok")
            self.assertEqual(res.model, "fallback/model")
            self.assertIsNotNone(res.response_text)
        finally:
            or_httpx.AsyncClient = original  # type: ignore[assignment]

    async def test_firecrawl_retries_then_success(self):
        attempts = {"n": 0}

        async def handler(url, headers, payload):
            attempts["n"] += 1
            if attempts["n"] == 1:
                return _Resp(500, {"error": "temporary"})
            return _Resp(200, {"markdown": "# ok"})

        original = fc_httpx.AsyncClient
        try:
            fc_httpx.AsyncClient = lambda timeout=None: _SeqAsyncClient(handler)  # type: ignore[assignment]
            client = FirecrawlClient(api_key="x", timeout_sec=2, max_retries=2, backoff_base=0.0)
            res = await client.scrape_markdown("https://example.com")
            self.assertEqual(res.status, "ok")
            self.assertEqual(res.http_status, 200)
            self.assertEqual(res.content_markdown, "# ok")
        finally:
            fc_httpx.AsyncClient = original  # type: ignore[assignment]


if __name__ == "__main__":
    unittest.main()
