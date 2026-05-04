import pytest
import httpx

from app.adapters.external.firecrawl.client import FirecrawlClient, FirecrawlClientConfig
from app.adapters.openrouter.openrouter_client import OpenRouterClient, OpenRouterClientConfig

FC_SCRAPE_URL = "https://api.firecrawl.dev/v2/scrape"
OR_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_firecrawl_scrape_markdown_mocked(respx_mock) -> None:
    respx_mock.post(FC_SCRAPE_URL).mock(return_value=httpx.Response(
        200,
        json={"markdown": "# Title\n\nContent", "html": "<h1>Title</h1>",
              "metadata": {"title": "Title"}, "success": True, "status_code": 200},
    ))
    client = FirecrawlClient(
        api_key="fc-dummy-key",
        config=FirecrawlClientConfig(timeout_sec=5),
    )
    res = await client.scrape_markdown("https://example.com")
    await client.aclose()

    assert res.status == "ok"
    assert res.http_status == 200
    assert "Title" in res.content_markdown


@pytest.mark.integration
@pytest.mark.asyncio
async def test_openrouter_chat_mocked(respx_mock) -> None:
    import json as _json

    respx_mock.post(OR_CHAT_URL).mock(return_value=httpx.Response(
        200,
        json={"model": "qwen/qwen3-max",
              "choices": [{"message": {"content": _json.dumps({"summary_250": "ok"})}}],
              "usage": {"prompt_tokens": 10, "completion_tokens": 20}},
    ))
    client = OpenRouterClient(
        api_key="sk-test-key-123456789",
        config=OpenRouterClientConfig(timeout_sec=5, enable_stats=False, log_truncate_length=1000),
        model="qwen/qwen3-max",
        provider_order=None,
    )
    res = await client.chat([{"role": "user", "content": "hi"}])
    await client.aclose()

    assert res.status == "ok"
    assert res.response_text is not None
    assert res.tokens_prompt == 10
    assert res.tokens_completion == 20
