import unittest
from typing import Any, cast

from app.adapters.firecrawl_parser import FirecrawlClient, httpx as fc_httpx


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


class TestFirecrawlErrorHandling(unittest.IsolatedAsyncioTestCase):
    """Test Firecrawl error handling scenarios."""

    async def test_firecrawl_200_with_error_in_response_body(self):
        """Test that Firecrawl properly handles 200 status with error in response body."""

        async def handler(url, headers, payload):
            # Simulate Firecrawl returning 200 OK but with error in response body
            return _Resp(
                200,
                {
                    "error": "SCRAPE_ALL_ENGINES_FAILED",
                    "markdown": None,
                    "html": None,
                    "metadata": None,
                },
            )

        original = fc_httpx.AsyncClient
        try:

            def _make_fc_client(timeout=None):
                return _SeqAsyncClient(handler)

            fc_httpx.AsyncClient = cast(Any, _make_fc_client)
            client = FirecrawlClient(
                api_key="fc-test_key",
                timeout_sec=30,
                max_retries=0,  # No retries for this test
                debug_payloads=True,
            )

            result = await client.scrape_markdown("https://example.com")

            # Verify that the result indicates an error
            self.assertEqual(result.status, "error")
            self.assertEqual(result.http_status, 200)
            self.assertEqual(result.error_text, "SCRAPE_ALL_ENGINES_FAILED")
            self.assertIsNone(result.content_markdown)
            self.assertIsNone(result.content_html)

        finally:
            fc_httpx.AsyncClient = cast(Any, original)

    async def test_firecrawl_200_without_error_in_response_body(self):
        """Test that Firecrawl properly handles 200 status without error in response body."""

        async def handler(url, headers, payload):
            # Simulate successful Firecrawl response
            return _Resp(
                200,
                {
                    "markdown": "# Test Content\n\nThis is a test.",
                    "html": "<h1>Test Content</h1><p>This is a test.</p>",
                    "metadata": {"title": "Test Page"},
                    "links": [],
                },
            )

        original = fc_httpx.AsyncClient
        try:

            def _make_fc_client(timeout=None):
                return _SeqAsyncClient(handler)

            fc_httpx.AsyncClient = cast(Any, _make_fc_client)
            client = FirecrawlClient(
                api_key="fc-test_key",
                timeout_sec=30,
                max_retries=0,  # No retries for this test
                debug_payloads=True,
            )

            result = await client.scrape_markdown("https://example.com")

            # Verify that the result indicates success
            self.assertEqual(result.status, "ok")
            self.assertEqual(result.http_status, 200)
            self.assertIsNone(result.error_text)
            self.assertEqual(result.content_markdown, "# Test Content\n\nThis is a test.")
            self.assertEqual(result.content_html, "<h1>Test Content</h1><p>This is a test.</p>")

        finally:
            fc_httpx.AsyncClient = cast(Any, original)

    async def test_firecrawl_200_with_empty_error_field(self):
        """Test that Firecrawl handles 200 status with empty error field (should be treated as success)."""

        async def handler(url, headers, payload):
            # Simulate Firecrawl returning 200 OK with empty error field
            return _Resp(
                200,
                {
                    "error": None,  # Empty error field
                    "markdown": "# Test Content\n\nThis is a test.",
                    "html": "<h1>Test Content</h1><p>This is a test.</p>",
                    "metadata": {"title": "Test Page"},
                },
            )

        original = fc_httpx.AsyncClient
        try:

            def _make_fc_client(timeout=None):
                return _SeqAsyncClient(handler)

            fc_httpx.AsyncClient = cast(Any, _make_fc_client)
            client = FirecrawlClient(
                api_key="fc-test_key",
                timeout_sec=30,
                max_retries=0,  # No retries for this test
                debug_payloads=True,
            )

            result = await client.scrape_markdown("https://example.com")

            # Verify that the result indicates success (empty error should be treated as success)
            self.assertEqual(result.status, "ok")
            self.assertEqual(result.http_status, 200)
            self.assertIsNone(result.error_text)
            self.assertEqual(result.content_markdown, "# Test Content\n\nThis is a test.")

        finally:
            fc_httpx.AsyncClient = cast(Any, original)

    async def test_firecrawl_200_with_empty_string_error(self):
        """Test that Firecrawl handles 200 status with empty string error (should be treated as success)."""

        async def handler(url, headers, payload):
            # Simulate Firecrawl returning 200 OK with empty string error
            return _Resp(
                200,
                {
                    "error": "",  # Empty string error
                    "markdown": "# Test Content\n\nThis is a test.",
                    "html": "<h1>Test Content</h1><p>This is a test.</p>",
                    "metadata": {"title": "Test Page"},
                },
            )

        original = fc_httpx.AsyncClient
        try:

            def _make_fc_client(timeout=None):
                return _SeqAsyncClient(handler)

            fc_httpx.AsyncClient = cast(Any, _make_fc_client)
            client = FirecrawlClient(
                api_key="fc-test_key",
                timeout_sec=30,
                max_retries=0,  # No retries for this test
                debug_payloads=True,
            )

            result = await client.scrape_markdown("https://example.com")

            # Verify that the result indicates success (empty string error should be treated as success)
            self.assertEqual(result.status, "ok")
            self.assertEqual(result.http_status, 200)
            self.assertIsNone(result.error_text)
            self.assertEqual(result.content_markdown, "# Test Content\n\nThis is a test.")

        finally:
            fc_httpx.AsyncClient = cast(Any, original)

    async def test_firecrawl_200_with_whitespace_error(self):
        """Test that Firecrawl handles 200 status with whitespace-only error (should be treated as success)."""

        async def handler(url, headers, payload):
            # Simulate Firecrawl returning 200 OK with whitespace-only error
            return _Resp(
                200,
                {
                    "error": "   \n\t  ",  # Whitespace-only error
                    "markdown": "# Test Content\n\nThis is a test.",
                    "html": "<h1>Test Content</h1><p>This is a test.</p>",
                    "metadata": {"title": "Test Page"},
                },
            )

        original = fc_httpx.AsyncClient
        try:

            def _make_fc_client(timeout=None):
                return _SeqAsyncClient(handler)

            fc_httpx.AsyncClient = cast(Any, _make_fc_client)
            client = FirecrawlClient(
                api_key="fc-test_key",
                timeout_sec=30,
                max_retries=0,  # No retries for this test
                debug_payloads=True,
            )

            result = await client.scrape_markdown("https://example.com")

            # Verify that the result indicates success (whitespace-only error should be treated as success)
            self.assertEqual(result.status, "ok")
            self.assertEqual(result.http_status, 200)
            self.assertIsNone(result.error_text)
            self.assertEqual(result.content_markdown, "# Test Content\n\nThis is a test.")

        finally:
            fc_httpx.AsyncClient = cast(Any, original)

    async def test_firecrawl_200_with_data_array_error(self):
        """Test that Firecrawl handles 200 status with error in data array format."""

        async def handler(url, headers, payload):
            # Simulate Firecrawl returning 200 OK with error in data array
            return _Resp(
                200,
                {
                    "success": True,
                    "data": [
                        {
                            "error": "SCRAPE_ALL_ENGINES_FAILED",
                            "markdown": None,
                            "html": None,
                            "metadata": None,
                        }
                    ],
                },
            )

        original = fc_httpx.AsyncClient
        try:

            def _make_fc_client(timeout=None):
                return _SeqAsyncClient(handler)

            fc_httpx.AsyncClient = cast(Any, _make_fc_client)
            client = FirecrawlClient(
                api_key="fc-test_key",
                timeout_sec=30,
                max_retries=0,  # No retries for this test
                debug_payloads=True,
            )

            result = await client.scrape_markdown("https://example.com")

            # Verify that the result indicates an error
            self.assertEqual(result.status, "error")
            self.assertEqual(result.http_status, 200)
            self.assertEqual(result.error_text, "SCRAPE_ALL_ENGINES_FAILED")
            self.assertIsNone(result.content_markdown)

        finally:
            fc_httpx.AsyncClient = cast(Any, original)

    async def test_firecrawl_200_with_data_array_success(self):
        """Test that Firecrawl handles 200 status with success in data array format."""

        async def handler(url, headers, payload):
            # Simulate Firecrawl returning 200 OK with success in data array
            return _Resp(
                200,
                {
                    "success": True,
                    "data": [
                        {
                            "markdown": "# Test Content\n\nThis is a test.",
                            "html": "<h1>Test Content</h1><p>This is a test.</p>",
                            "metadata": {"title": "Test Page"},
                            "links": [],
                        }
                    ],
                },
            )

        original = fc_httpx.AsyncClient
        try:

            def _make_fc_client(timeout=None):
                return _SeqAsyncClient(handler)

            fc_httpx.AsyncClient = cast(Any, _make_fc_client)
            client = FirecrawlClient(
                api_key="fc-test_key",
                timeout_sec=30,
                max_retries=0,  # No retries for this test
                debug_payloads=True,
            )

            result = await client.scrape_markdown("https://example.com")

            # Verify that the result indicates success
            self.assertEqual(result.status, "ok")
            self.assertEqual(result.http_status, 200)
            self.assertIsNone(result.error_text)
            self.assertEqual(result.content_markdown, "# Test Content\n\nThis is a test.")
            self.assertEqual(result.content_html, "<h1>Test Content</h1><p>This is a test.</p>")

        finally:
            fc_httpx.AsyncClient = cast(Any, original)

    async def test_firecrawl_200_with_data_object_success(self):
        """Test that Firecrawl handles 200 status with success in data object format."""

        async def handler(url, headers, payload):
            # Simulate Firecrawl returning 200 OK with success in data object
            return _Resp(
                200,
                {
                    "success": True,
                    "data": {
                        "markdown": "# Test Content\n\nThis is a test.",
                        "html": "<h1>Test Content</h1><p>This is a test.</p>",
                        "metadata": {"title": "Test Page"},
                        "links": [],
                    },
                },
            )

        original = fc_httpx.AsyncClient
        try:

            def _make_fc_client(timeout=None):
                return _SeqAsyncClient(handler)

            fc_httpx.AsyncClient = cast(Any, _make_fc_client)
            client = FirecrawlClient(
                api_key="fc-test_key",
                timeout_sec=30,
                max_retries=0,  # No retries for this test
                debug_payloads=True,
            )

            result = await client.scrape_markdown("https://example.com")

            # Verify that the result indicates success
            self.assertEqual(result.status, "ok")
            self.assertEqual(result.http_status, 200)
            self.assertIsNone(result.error_text)
            self.assertEqual(result.content_markdown, "# Test Content\n\nThis is a test.")
            self.assertEqual(result.content_html, "<h1>Test Content</h1><p>This is a test.</p>")

        finally:
            fc_httpx.AsyncClient = cast(Any, original)

    async def test_firecrawl_200_with_data_object_error(self):
        """Test that Firecrawl handles 200 status with error in data object format."""

        async def handler(url, headers, payload):
            # Simulate Firecrawl returning 200 OK with error in data object
            return _Resp(
                200,
                {
                    "success": True,
                    "data": {
                        "error": "SCRAPE_ALL_ENGINES_FAILED",
                        "markdown": None,
                        "html": None,
                        "metadata": None,
                    },
                },
            )

        original = fc_httpx.AsyncClient
        try:

            def _make_fc_client(timeout=None):
                return _SeqAsyncClient(handler)

            fc_httpx.AsyncClient = cast(Any, _make_fc_client)
            client = FirecrawlClient(
                api_key="fc-test_key",
                timeout_sec=30,
                max_retries=0,  # No retries for this test
                debug_payloads=True,
            )

            result = await client.scrape_markdown("https://example.com")

            # Verify that the result indicates an error
            self.assertEqual(result.status, "error")
            self.assertEqual(result.http_status, 200)
            self.assertEqual(result.error_text, "SCRAPE_ALL_ENGINES_FAILED")
            self.assertIsNone(result.content_markdown)

        finally:
            fc_httpx.AsyncClient = cast(Any, original)

    async def test_firecrawl_401_unauthorized(self):
        """Test that Firecrawl handles 401 Unauthorized properly."""

        async def handler(url, headers, payload):
            return _Resp(
                401,
                {
                    "error": "Unauthorized",
                    "message": "Invalid API key",
                },
            )

        original = fc_httpx.AsyncClient
        try:

            def _make_fc_client(timeout=None):
                return _SeqAsyncClient(handler)

            fc_httpx.AsyncClient = cast(Any, _make_fc_client)
            client = FirecrawlClient(
                api_key="fc-test_key",
                timeout_sec=30,
                max_retries=0,
                debug_payloads=True,
            )

            result = await client.scrape_markdown("https://example.com")

            # Verify that the result indicates an error
            self.assertEqual(result.status, "error")
            self.assertEqual(result.http_status, 401)
            self.assertIn("Unauthorized", result.error_text)

        finally:
            fc_httpx.AsyncClient = cast(Any, original)

    async def test_firecrawl_402_payment_required(self):
        """Test that Firecrawl handles 402 Payment Required properly."""

        async def handler(url, headers, payload):
            return _Resp(
                402,
                {
                    "error": "Payment Required",
                    "message": "Insufficient credits",
                },
            )

        original = fc_httpx.AsyncClient
        try:

            def _make_fc_client(timeout=None):
                return _SeqAsyncClient(handler)

            fc_httpx.AsyncClient = cast(Any, _make_fc_client)
            client = FirecrawlClient(
                api_key="fc-test_key",
                timeout_sec=30,
                max_retries=0,
                debug_payloads=True,
            )

            result = await client.scrape_markdown("https://example.com")

            # Verify that the result indicates an error
            self.assertEqual(result.status, "error")
            self.assertEqual(result.http_status, 402)
            self.assertIn("Payment Required", result.error_text)

        finally:
            fc_httpx.AsyncClient = cast(Any, original)

    async def test_firecrawl_404_not_found(self):
        """Test that Firecrawl handles 404 Not Found properly."""

        async def handler(url, headers, payload):
            return _Resp(
                404,
                {
                    "error": "Not Found",
                    "message": "Resource not found",
                },
            )

        original = fc_httpx.AsyncClient
        try:

            def _make_fc_client(timeout=None):
                return _SeqAsyncClient(handler)

            fc_httpx.AsyncClient = cast(Any, _make_fc_client)
            client = FirecrawlClient(
                api_key="fc-test_key",
                timeout_sec=30,
                max_retries=0,
                debug_payloads=True,
            )

            result = await client.scrape_markdown("https://example.com")

            # Verify that the result indicates an error
            self.assertEqual(result.status, "error")
            self.assertEqual(result.http_status, 404)
            self.assertIn("Not Found", result.error_text)

        finally:
            fc_httpx.AsyncClient = cast(Any, original)

    async def test_firecrawl_429_rate_limit(self):
        """Test that Firecrawl handles 429 Rate Limit properly."""

        async def handler(url, headers, payload):
            return _Resp(
                429,
                {
                    "error": "Rate Limit Exceeded",
                    "message": "Too many requests",
                    "retry_after": 60,
                },
            )

        original = fc_httpx.AsyncClient
        try:

            def _make_fc_client(timeout=None):
                return _SeqAsyncClient(handler)

            fc_httpx.AsyncClient = cast(Any, _make_fc_client)
            client = FirecrawlClient(
                api_key="fc-test_key",
                timeout_sec=30,
                max_retries=0,  # No retries for this test
                debug_payloads=True,
            )

            result = await client.scrape_markdown("https://example.com")

            # Verify that the result indicates an error
            self.assertEqual(result.status, "error")
            self.assertEqual(result.http_status, 429)
            self.assertIn("Rate Limit", result.error_text)

        finally:
            fc_httpx.AsyncClient = cast(Any, original)


if __name__ == "__main__":
    unittest.main()
