import json
import unittest
from typing import Any, cast

from app.adapters.external.firecrawl_parser import FirecrawlClient, httpx as firecrawl_httpx
from app.adapters.openrouter.openrouter_client import OpenRouterClient, httpx as or_httpx


class _FakeResponse:
    def __init__(self, status_code: int, data: dict):
        self.status_code = status_code
        self._data = data
        self.headers: dict[str, str] = {}
        self.content = b"{}"

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            msg = f"HTTP {self.status_code}"
            raise Exception(msg)


class _FakeAsyncClient:
    def __init__(self, *, response_map):
        self.response_map = response_map

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None):
        # decide response by URL
        for key, resp in self.response_map.items():
            if key in url:
                return _FakeResponse(resp[0], resp[1])
        msg = f"Unexpected URL: {url}"
        raise AssertionError(msg)

    async def get(self, url, headers=None):
        # Handle models endpoint
        if "/models" in url:
            return _FakeResponse(
                200,
                {
                    "data": [
                        {
                            "id": "qwen/qwen3-max",
                            "object": "model",
                            "supported_parameters": {"structured_outputs": True},
                        },
                    ]
                },
            )
        msg = f"Unexpected URL: {url}"
        raise AssertionError(msg)


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

            def _make_fc_client(*args, **kwargs):
                return fake

            firecrawl_httpx.AsyncClient = cast("Any", _make_fc_client)

            client = FirecrawlClient(api_key="fc-dummy-key", timeout_sec=5)
            res = await client.scrape_markdown("https://example.com")
            assert res.status == "ok"
            assert res.http_status == 200
            assert "Title" in res.content_markdown
        finally:
            firecrawl_httpx.AsyncClient = cast("Any", original)

    async def test_openrouter_chat_mocked(self):
        # Patch httpx.AsyncClient in openrouter module
        original = or_httpx.AsyncClient
        try:
            payload = {
                "model": "qwen/qwen3-max",
                "choices": [{"message": {"content": json.dumps({"summary_250": "ok"})}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            }
            fake = _FakeAsyncClient(response_map={"/chat/completions": (200, payload)})

            def _make_or_client(*args, **kwargs):
                return fake

            or_httpx.AsyncClient = cast("Any", _make_or_client)

            client = OpenRouterClient(
                api_key="sk-test-key-123456789",
                model="qwen/qwen3-max",
                timeout_sec=5,
                provider_order=None,
                enable_stats=False,
                log_truncate_length=1000,
            )
            res = await client.chat([{"role": "user", "content": "hi"}])
            assert res.status == "ok"
            assert res.response_text is not None
            assert res.tokens_prompt == 10
            assert res.tokens_completion == 20
        finally:
            or_httpx.AsyncClient = cast("Any", original)


if __name__ == "__main__":
    unittest.main()
