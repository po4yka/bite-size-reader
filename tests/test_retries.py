import pytest
import httpx

from app.adapters.external.firecrawl.client import FirecrawlClient, FirecrawlClientConfig

FC_SCRAPE_URL = "https://api.firecrawl.dev/v2/scrape"


@pytest.mark.asyncio
async def test_firecrawl_retries_then_success(respx_mock) -> None:
    respx_mock.post(FC_SCRAPE_URL).mock(side_effect=[
        httpx.Response(500, json={"error": "temporary"}),
        httpx.Response(200, json={"markdown": "# ok", "success": True, "status_code": 200}),
    ])
    client = FirecrawlClient(
        api_key="fc-dummy-key",
        config=FirecrawlClientConfig(timeout_sec=2, max_retries=2, backoff_base=0.0),
    )
    res = await client.scrape_markdown("https://example.com")
    await client.aclose()

    assert res.status == "ok"
    assert res.http_status == 200
    assert res.content_markdown == "# ok"
