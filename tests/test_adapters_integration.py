import json
import unittest
from typing import Any, cast

from app.adapters.firecrawl_parser import FirecrawlClient, httpx as firecrawl_httpx
from app.adapters.openrouter_client import OpenRouterClient, httpx as or_httpx


class _FakeResponse:
    def __init__(self, status_code: int, data: dict):
        self.status_code = status_code
        self._data = data

    def json(self):
        return self._data


class _FakeAsyncClient:
    def __init__(self, *, response_map):
        self.response_map = response_map

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None):  # noqa: A002 - shadowing 'json'
        # decide response by URL
        for key, resp in self.response_map.items():
            if key in url:
                return _FakeResponse(resp[0], resp[1])
        raise AssertionError(f"Unexpected URL: {url}")


class TestAdaptersIntegration(unittest.IsolatedAsyncioTestCase):
    async def test_firecrawl_scrape_markdown_mocked(self):
        # Patch httpx.AsyncClient in firecrawl module
        original = firecrawl_httpx.AsyncClient
        try:
            fake = _FakeAsyncClient(
                response_map={
                    "api.firecrawl.dev": (
                        200,
                        {
                            "markdown": "# Title\n\nContent",
                            "html": "<h1>Title</h1>",
                            "metadata": {"title": "Title"},
                        },
                    )
                }
            )

            def _make_fc_client(timeout=None):
                return fake

            firecrawl_httpx.AsyncClient = cast(Any, _make_fc_client)

            client = FirecrawlClient(api_key="x", timeout_sec=5)
            res = await client.scrape_markdown("https://example.com")
            self.assertEqual(res.status, "ok")
            self.assertEqual(res.http_status, 200)
            self.assertIn("Title", res.content_markdown)
        finally:
            firecrawl_httpx.AsyncClient = cast(Any, original)

    async def test_openrouter_chat_mocked(self):
        # Patch httpx.AsyncClient in openrouter module
        original = or_httpx.AsyncClient
        try:
            payload = {
                "model": "openai/gpt-5",
                "choices": [{"message": {"content": json.dumps({"summary_250": "ok"})}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            }
            fake = _FakeAsyncClient(response_map={"openrouter.ai": (200, payload)})

            def _make_or_client(timeout=None):
                return fake

            or_httpx.AsyncClient = cast(Any, _make_or_client)

            client = OpenRouterClient(api_key="y", model="openai/gpt-5", timeout_sec=5)
            res = await client.chat([{"role": "user", "content": "hi"}])
            self.assertEqual(res.status, "ok")
            self.assertIsNotNone(res.response_text)
            self.assertEqual(res.tokens_prompt, 10)
            self.assertEqual(res.tokens_completion, 20)
        finally:
            or_httpx.AsyncClient = cast(Any, original)


if __name__ == "__main__":
    unittest.main()
