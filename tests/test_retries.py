# json: used to craft serialized payloads that mirror OpenRouter responses.
import json
import unittest
from typing import Any, cast

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

            def _make_or_client(*args, **kwargs):
                return _SeqAsyncClient(handler)

            or_httpx.AsyncClient = cast(Any, _make_or_client)
            client = OpenRouterClient(
                api_key="k",
                model="primary/model",
                fallback_models=["fallback/model"],
                timeout_sec=2,
                max_retries=1,
                backoff_base=0.0,
                provider_order=None,
                enable_stats=False,
                log_truncate_length=1000,
            )
            res = await client.chat([{"role": "user", "content": "hi"}])
            self.assertEqual(res.status, "ok")
            self.assertEqual(res.model, "fallback/model")
            self.assertIsNotNone(res.response_text)
        finally:
            or_httpx.AsyncClient = cast(Any, original)

    async def test_structured_output_parse_error_triggers_fallback(self):
        attempts: list[str] = []

        async def handler(url, headers, payload):
            model = payload.get("model")
            attempts.append(model)
            if model == "primary/model":
                return _Resp(
                    200,
                    {
                        "model": model,
                        "choices": [{"message": {"content": "not json"}}],
                        "usage": {"prompt_tokens": 2, "completion_tokens": 3},
                    },
                )
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

            def _make_or_client(*args, **kwargs):
                return _SeqAsyncClient(handler)

            or_httpx.AsyncClient = cast(Any, _make_or_client)
            client = OpenRouterClient(
                api_key="k",
                model="primary/model",
                fallback_models=["fallback/model"],
                timeout_sec=2,
                max_retries=0,
                backoff_base=0.0,
                provider_order=None,
                enable_stats=False,
                log_truncate_length=1000,
            )
            res = await client.chat(
                [{"role": "user", "content": "hi"}],
                response_format={"type": "json_object"},
            )
            self.assertEqual(res.status, "ok")
            self.assertEqual(res.model, "fallback/model")
            self.assertEqual(attempts, ["primary/model", "fallback/model"])
        finally:
            or_httpx.AsyncClient = cast(Any, original)

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

            fc_httpx.AsyncClient = cast(Any, _make_fc_client)
            client = FirecrawlClient(
                api_key="fc-dummy-key", timeout_sec=2, max_retries=2, backoff_base=0.0
            )
            res = await client.scrape_markdown("https://example.com")
            self.assertEqual(res.status, "ok")
            self.assertEqual(res.http_status, 200)
            self.assertEqual(res.content_markdown, "# ok")
        finally:
            fc_httpx.AsyncClient = cast(Any, original)


if __name__ == "__main__":
    unittest.main()
