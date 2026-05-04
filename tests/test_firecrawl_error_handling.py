import pytest
import pytest_asyncio
import httpx

from app.adapters.external.firecrawl.client import FirecrawlClient, FirecrawlClientConfig

FC_SCRAPE_URL = "https://api.firecrawl.dev/v2/scrape"


@pytest_asyncio.fixture
async def fc_client():
    client = FirecrawlClient(
        api_key="fc-test_key",
        config=FirecrawlClientConfig(timeout_sec=30, max_retries=0, debug_payloads=True),
    )
    yield client
    await client.aclose()


@pytest.mark.asyncio
async def test_firecrawl_200_with_error_in_response_body(respx_mock, fc_client):
    respx_mock.post(FC_SCRAPE_URL).mock(return_value=httpx.Response(
        200,
        json={"error": "SCRAPE_ALL_ENGINES_FAILED", "markdown": None, "html": None,
              "metadata": None, "status_code": 200},
    ))
    result = await fc_client.scrape_markdown("https://example.com")
    assert result.status == "error"
    assert result.http_status == 200
    assert result.error_text == "SCRAPE_ALL_ENGINES_FAILED"
    assert result.content_markdown is None
    assert result.content_html is None


@pytest.mark.asyncio
async def test_firecrawl_200_without_error_in_response_body(respx_mock, fc_client):
    respx_mock.post(FC_SCRAPE_URL).mock(return_value=httpx.Response(
        200,
        json={"markdown": "# Test Content\n\nThis is a test.",
              "html": "<h1>Test Content</h1><p>This is a test.</p>",
              "metadata": {"title": "Test Page"}, "links": [], "status_code": 200},
    ))
    result = await fc_client.scrape_markdown("https://example.com")
    assert result.status == "ok"
    assert result.http_status == 200
    assert result.error_text is None
    assert result.content_markdown == "# Test Content\n\nThis is a test."
    assert result.content_html == "<h1>Test Content</h1><p>This is a test.</p>"


@pytest.mark.asyncio
async def test_firecrawl_200_with_empty_error_field(respx_mock, fc_client):
    respx_mock.post(FC_SCRAPE_URL).mock(return_value=httpx.Response(
        200,
        json={"error": None, "markdown": "# Test Content\n\nThis is a test.",
              "html": "<h1>Test Content</h1><p>This is a test.</p>",
              "metadata": {"title": "Test Page"}, "status_code": 200},
    ))
    result = await fc_client.scrape_markdown("https://example.com")
    assert result.status == "ok"
    assert result.http_status == 200
    assert result.error_text is None
    assert result.content_markdown == "# Test Content\n\nThis is a test."


@pytest.mark.asyncio
async def test_firecrawl_200_with_empty_string_error(respx_mock, fc_client):
    respx_mock.post(FC_SCRAPE_URL).mock(return_value=httpx.Response(
        200,
        json={"error": "", "markdown": "# Test Content\n\nThis is a test.",
              "html": "<h1>Test Content</h1><p>This is a test.</p>",
              "metadata": {"title": "Test Page"}, "status_code": 200},
    ))
    result = await fc_client.scrape_markdown("https://example.com")
    assert result.status == "ok"
    assert result.http_status == 200
    assert result.error_text is None
    assert result.content_markdown == "# Test Content\n\nThis is a test."


@pytest.mark.asyncio
async def test_firecrawl_200_with_whitespace_error(respx_mock, fc_client):
    respx_mock.post(FC_SCRAPE_URL).mock(return_value=httpx.Response(
        200,
        json={"error": "   \n\t  ", "markdown": "# Test Content\n\nThis is a test.",
              "html": "<h1>Test Content</h1><p>This is a test.</p>",
              "metadata": {"title": "Test Page"}, "status_code": 200},
    ))
    result = await fc_client.scrape_markdown("https://example.com")
    assert result.status == "ok"
    assert result.http_status == 200
    assert result.error_text is None
    assert result.content_markdown == "# Test Content\n\nThis is a test."


@pytest.mark.asyncio
async def test_firecrawl_200_with_data_array_error(respx_mock, fc_client):
    respx_mock.post(FC_SCRAPE_URL).mock(return_value=httpx.Response(
        200,
        json={"success": True, "data": [{"error": "SCRAPE_ALL_ENGINES_FAILED",
              "markdown": None, "html": None, "metadata": None}], "status_code": 200},
    ))
    result = await fc_client.scrape_markdown("https://example.com")
    assert result.status == "error"
    assert result.http_status == 200
    assert result.error_text == "SCRAPE_ALL_ENGINES_FAILED"
    assert result.content_markdown is None


@pytest.mark.asyncio
async def test_firecrawl_200_with_data_array_success(respx_mock, fc_client):
    respx_mock.post(FC_SCRAPE_URL).mock(return_value=httpx.Response(
        200,
        json={"success": True, "data": [{"markdown": "# Test Content\n\nThis is a test.",
              "html": "<h1>Test Content</h1><p>This is a test.</p>",
              "metadata": {"title": "Test Page"}, "links": []}], "status_code": 200},
    ))
    result = await fc_client.scrape_markdown("https://example.com")
    assert result.status == "ok"
    assert result.http_status == 200
    assert result.error_text is None
    assert result.content_markdown == "# Test Content\n\nThis is a test."
    assert result.content_html == "<h1>Test Content</h1><p>This is a test.</p>"


@pytest.mark.asyncio
async def test_firecrawl_200_with_data_object_success(respx_mock, fc_client):
    respx_mock.post(FC_SCRAPE_URL).mock(return_value=httpx.Response(
        200,
        json={"success": True, "data": {"markdown": "# Test Content\n\nThis is a test.",
              "html": "<h1>Test Content</h1><p>This is a test.</p>",
              "metadata": {"title": "Test Page"}, "links": []}, "status_code": 200},
    ))
    result = await fc_client.scrape_markdown("https://example.com")
    assert result.status == "ok"
    assert result.http_status == 200
    assert result.error_text is None
    assert result.content_markdown == "# Test Content\n\nThis is a test."
    assert result.content_html == "<h1>Test Content</h1><p>This is a test.</p>"


@pytest.mark.asyncio
async def test_firecrawl_200_with_data_object_error(respx_mock, fc_client):
    respx_mock.post(FC_SCRAPE_URL).mock(return_value=httpx.Response(
        200,
        json={"success": True, "data": {"error": "SCRAPE_ALL_ENGINES_FAILED",
              "markdown": None, "html": None, "metadata": None}, "status_code": 200},
    ))
    result = await fc_client.scrape_markdown("https://example.com")
    assert result.status == "error"
    assert result.http_status == 200
    assert result.error_text == "SCRAPE_ALL_ENGINES_FAILED"
    assert result.content_markdown is None


@pytest.mark.asyncio
async def test_firecrawl_401_unauthorized(respx_mock, fc_client):
    respx_mock.post(FC_SCRAPE_URL).mock(return_value=httpx.Response(
        401, json={"error": "Unauthorized", "message": "Invalid API key"},
    ))
    result = await fc_client.scrape_markdown("https://example.com")
    assert result.status == "error"
    assert result.http_status == 401
    assert "Unauthorized" in result.error_text


@pytest.mark.asyncio
async def test_firecrawl_402_payment_required(respx_mock, fc_client):
    respx_mock.post(FC_SCRAPE_URL).mock(return_value=httpx.Response(
        402, json={"error": "Payment Required", "message": "Insufficient credits"},
    ))
    result = await fc_client.scrape_markdown("https://example.com")
    assert result.status == "error"
    assert result.http_status == 402
    assert "Payment Required" in result.error_text


@pytest.mark.asyncio
async def test_firecrawl_404_not_found(respx_mock, fc_client):
    respx_mock.post(FC_SCRAPE_URL).mock(return_value=httpx.Response(
        404, json={"error": "Not Found", "message": "Resource not found"},
    ))
    result = await fc_client.scrape_markdown("https://example.com")
    assert result.status == "error"
    assert result.http_status == 404
    assert "Not Found" in result.error_text


@pytest.mark.asyncio
async def test_firecrawl_429_rate_limit(respx_mock, fc_client):
    respx_mock.post(FC_SCRAPE_URL).mock(return_value=httpx.Response(
        429,
        json={"error": "Rate Limit Exceeded", "message": "Too many requests", "retry_after": 60},
    ))
    result = await fc_client.scrape_markdown("https://example.com")
    assert result.status == "error"
    assert result.http_status == 429
    assert "Rate Limit" in result.error_text
