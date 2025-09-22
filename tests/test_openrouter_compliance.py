"""Test OpenRouter API compliance according to official documentation."""

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.adapters.openrouter.openrouter_client import OpenRouterClient


class TestOpenRouterCompliance(unittest.TestCase):
    """Test OpenRouter API compliance with official documentation."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.client = OpenRouterClient(
            api_key="sk-or-test-key",
            model="openai/gpt-4o-mini",
            fallback_models=["google/gemini-2.5-pro"],
            http_referer="https://github.com/test-repo",
            x_title="Test Bot",
            timeout_sec=30,
            max_retries=2,
            debug_payloads=True,
        )

    def tearDown(self) -> None:
        """Ensure resources created by the client are closed."""
        asyncio.run(self.client.aclose())

    def test_correct_api_endpoint(self) -> None:
        """Test that the correct API endpoint is used."""

        async def _test() -> None:
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "choices": [{"message": {"content": "Test response"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                }
                mock_client.return_value.post = AsyncMock(return_value=mock_response)

                await self.client.chat([{"role": "user", "content": "Hello"}])

                # Verify the correct endpoint is called
                call_args = mock_client.return_value.post.call_args
                self.assertEqual(call_args[0][0], "/chat/completions")

        asyncio.run(_test())

    def test_authentication_header(self) -> None:
        """Test that Authorization header is correctly formatted."""

        async def _test() -> None:
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "choices": [{"message": {"content": "Test response"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                }
                mock_client.return_value.post = AsyncMock(return_value=mock_response)

                await self.client.chat([{"role": "user", "content": "Hello"}])

                # Verify Authorization header
                call_args = mock_client.return_value.post.call_args
                headers = call_args[1]["headers"]
                self.assertEqual(headers["Authorization"], "Bearer sk-or-test-key")

        asyncio.run(_test())

    def test_request_structure(self) -> None:
        """Test that request body follows OpenAI-compatible format."""

        async def _test() -> None:
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "choices": [{"message": {"content": "Test response"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                }
                mock_client.return_value.post = AsyncMock(return_value=mock_response)

                messages = [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "What is the meaning of life?"},
                ]
                await self.client.chat(messages, temperature=0.7, max_tokens=100)

                # Verify request body structure
                call_args = mock_client.return_value.post.call_args
                body = call_args[1]["json"]
                self.assertEqual(body["model"], "openai/gpt-4o-mini")
                self.assertEqual(body["messages"], messages)
                self.assertEqual(body["temperature"], 0.7)
                self.assertEqual(body["max_tokens"], 100)

        asyncio.run(_test())

    def test_optional_parameters(self) -> None:
        """Test that optional parameters are correctly handled."""

        async def _test() -> None:
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "choices": [{"message": {"content": "Test response"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                }
                mock_client.return_value.post = AsyncMock(return_value=mock_response)

                await self.client.chat(
                    [{"role": "user", "content": "Hello"}],
                    temperature=0.5,
                    max_tokens=50,
                    top_p=0.9,
                    stream=True,
                )

                # Verify optional parameters
                call_args = mock_client.return_value.post.call_args
                body = call_args[1]["json"]
                self.assertEqual(body["temperature"], 0.5)
                self.assertEqual(body["max_tokens"], 50)
                self.assertEqual(body["top_p"], 0.9)
                self.assertTrue(body["stream"])

        asyncio.run(_test())

    def test_http_headers(self) -> None:
        """Test that all required headers are present."""

        async def _test() -> None:
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "choices": [{"message": {"content": "Test response"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                }
                mock_client.return_value.post = AsyncMock(return_value=mock_response)

                await self.client.chat([{"role": "user", "content": "Hello"}])

                # Verify headers
                call_args = mock_client.return_value.post.call_args
                headers = call_args[1]["headers"]
                self.assertEqual(headers["Content-Type"], "application/json")
                self.assertEqual(headers["HTTP-Referer"], "https://github.com/test-repo")
                self.assertEqual(headers["X-Title"], "Test Bot")

        asyncio.run(_test())

    def test_error_handling_400(self) -> None:
        """Test handling of 400 Bad Request error."""

        async def _test() -> None:
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = Mock()
                mock_response.status_code = 400
                mock_response.json.return_value = {
                    "error": {"message": "Invalid request parameters"}
                }
                mock_client.return_value.post = AsyncMock(return_value=mock_response)

                result = await self.client.chat([{"role": "user", "content": "Hello"}])

                self.assertEqual(result.status, "error")
                self.assertIn("Invalid or missing request parameters", result.error_text)

        asyncio.run(_test())

    def test_error_handling_401(self) -> None:
        """Test handling of 401 Unauthorized error."""

        async def _test() -> None:
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = Mock()
                mock_response.status_code = 401
                mock_response.json.return_value = {"error": {"message": "Invalid API key"}}
                mock_client.return_value.post = AsyncMock(return_value=mock_response)

                result = await self.client.chat([{"role": "user", "content": "Hello"}])

                self.assertEqual(result.status, "error")
                self.assertIn("Authentication failed", result.error_text)

        asyncio.run(_test())

    def test_error_handling_402(self) -> None:
        """Test handling of 402 Payment Required error."""

        async def _test() -> None:
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = Mock()
                mock_response.status_code = 402
                mock_response.json.return_value = {"error": {"message": "Insufficient credits"}}
                mock_client.return_value.post = AsyncMock(return_value=mock_response)

                result = await self.client.chat([{"role": "user", "content": "Hello"}])

                self.assertEqual(result.status, "error")
                self.assertIn("Insufficient account balance", result.error_text)

        asyncio.run(_test())

    def test_error_handling_404(self) -> None:
        """Test handling of 404 Not Found error."""

        async def _test() -> None:
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = Mock()
                mock_response.status_code = 404
                mock_response.json.return_value = {"error": {"message": "Model not found"}}
                mock_client.return_value.post = AsyncMock(return_value=mock_response)

                result = await self.client.chat([{"role": "user", "content": "Hello"}])

                self.assertEqual(result.status, "error")
                self.assertIn("Requested resource not found", result.error_text)

        asyncio.run(_test())

    def test_error_handling_429_with_retry_after(self) -> None:
        """Test handling of 429 Rate Limit with retry-after header."""

        async def _test() -> None:
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = Mock()
                mock_response.status_code = 429
                mock_response.headers = {"retry-after": "5"}
                mock_response.json.return_value = {"error": {"message": "Rate limit exceeded"}}
                mock_client.return_value.post = AsyncMock(return_value=mock_response)

                with patch("asyncio.sleep") as mock_sleep:
                    await self.client.chat([{"role": "user", "content": "Hello"}])

                    # Should have called sleep with retry-after value
                    mock_sleep.assert_called_with(5)

        asyncio.run(_test())

    def test_error_handling_500(self) -> None:
        """Test handling of 500 Internal Server Error."""

        async def _test() -> None:
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = Mock()
                mock_response.status_code = 500
                mock_response.json.return_value = {"error": {"message": "Internal server error"}}
                mock_client.return_value.post = AsyncMock(return_value=mock_response)

                with patch("asyncio.sleep") as mock_sleep:
                    await self.client.chat([{"role": "user", "content": "Hello"}])

                    # Should have retried with exponential backoff
                    self.assertGreater(mock_sleep.call_count, 0)

        asyncio.run(_test())

    def test_success_response_parsing(self) -> None:
        """Test parsing of successful response."""

        async def _test() -> None:
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "choices": [{"message": {"content": "Test response"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                    "model": "openai/gpt-4o-mini",
                }
                mock_client.return_value.post = AsyncMock(return_value=mock_response)

                result = await self.client.chat([{"role": "user", "content": "Hello"}])

                self.assertEqual(result.status, "ok")
                self.assertEqual(result.response_text, "Test response")
                self.assertEqual(result.tokens_prompt, 10)
                self.assertEqual(result.tokens_completion, 5)
                self.assertEqual(result.model, "openai/gpt-4o-mini")
                self.assertEqual(result.endpoint, "/api/v1/chat/completions")

        asyncio.run(_test())

    def test_structured_output_content_with_json_part(self) -> None:
        """Ensure content lists containing JSON parts are parsed correctly."""

        async def _test() -> None:
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "id": "test-response",
                    "model": "openai/gpt-5",
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                    },
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": [
                                    {"type": "reasoning", "text": "Planning structured output"},
                                    {
                                        "type": "output_json",
                                        "json": {
                                            "summary_250": "Short summary",
                                            "summary_1000": "Longer summary",
                                        },
                                    },
                                ],
                            },
                            "finish_reason": "stop",
                            "native_finish_reason": "completed",
                        }
                    ],
                }
                mock_client.return_value.post = AsyncMock(return_value=mock_response)
                mock_models_response = Mock()
                mock_models_response.status_code = 200
                mock_models_response.json.return_value = {"data": []}
                mock_models_response.raise_for_status = Mock()
                mock_client.return_value.get = AsyncMock(return_value=mock_models_response)
                mock_client.return_value.__aenter__.return_value = mock_client.return_value
                mock_client.return_value.__aexit__.return_value = AsyncMock(return_value=None)

                response_format = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "summary_schema",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "summary_250": {"type": "string"},
                                "summary_1000": {"type": "string"},
                            },
                            "required": ["summary_250", "summary_1000"],
                        },
                    },
                }

                result = await self.client.chat(
                    [{"role": "user", "content": "Hello"}],
                    response_format=response_format,
                )

                self.assertEqual(result.status, "ok")
                self.assertIsNotNone(result.response_text)
                parsed = json.loads(result.response_text or "{}")
                self.assertEqual(parsed["summary_250"], "Short summary")
                self.assertEqual(parsed["summary_1000"], "Longer summary")

        asyncio.run(_test())

    def test_models_endpoint(self) -> None:
        """Test models endpoint functionality."""

        async def _test() -> None:
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "data": [
                        {"id": "openai/gpt-4o-mini", "name": "GPT-4o Mini"},
                        {"id": "google/gemini-2.5-pro", "name": "Gemini 2.5 Pro"},
                    ]
                }
                mock_response.raise_for_status = Mock()
                mock_client.return_value.get = AsyncMock(return_value=mock_response)
                mock_client.return_value.__aenter__.return_value = mock_client.return_value
                mock_client.return_value.__aexit__.return_value = AsyncMock(return_value=None)

                models = await self.client.get_models()

                # Verify models endpoint is called
                call_args = mock_client.return_value.get.call_args
                self.assertEqual(call_args[0][0], "https://openrouter.ai/api/v1/models")

                # Verify response
                self.assertIn("data", models)
                self.assertEqual(len(models["data"]), 2)

        asyncio.run(_test())

    def test_fallback_models(self) -> None:
        """Test fallback model functionality."""

        async def _test() -> None:
            with patch("httpx.AsyncClient") as mock_client:
                # First call fails, second succeeds
                mock_responses = [
                    Mock(status_code=500, json=Mock(return_value={"error": "Server error"})),
                    Mock(
                        status_code=200,
                        json=Mock(
                            return_value={
                                "choices": [{"message": {"content": "Fallback response"}}],
                                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                                "model": "google/gemini-2.5-pro",
                            }
                        ),
                    ),
                ]
                mock_client.return_value.post = AsyncMock(side_effect=mock_responses)

                with patch("asyncio.sleep"):
                    result = await self.client.chat([{"role": "user", "content": "Hello"}])

                    self.assertEqual(result.status, "ok")
                    self.assertEqual(result.response_text, "Fallback response")
                    self.assertEqual(result.model, "google/gemini-2.5-pro")

        asyncio.run(_test())

    def test_parameter_validation(self) -> None:
        """Test parameter validation."""
        from app.adapters.openrouter.exceptions import ValidationError

        # Test invalid temperature
        with self.assertRaises(ValidationError):
            asyncio.run(self.client.chat([{"role": "user", "content": "Hello"}], temperature=3.0))

        # Test invalid max_tokens
        with self.assertRaises(ValidationError):
            asyncio.run(self.client.chat([{"role": "user", "content": "Hello"}], max_tokens=-1))

        # Test invalid top_p
        with self.assertRaises(ValidationError):
            asyncio.run(self.client.chat([{"role": "user", "content": "Hello"}], top_p=1.5))

        # Test invalid stream
        with self.assertRaises(ValidationError):
            asyncio.run(self.client.chat([{"role": "user", "content": "Hello"}], stream="true"))  # type: ignore[arg-type]

    def test_message_validation(self) -> None:
        """Test message structure validation."""
        from app.adapters.openrouter.exceptions import ValidationError

        # Test empty messages
        with self.assertRaises(ValidationError):
            asyncio.run(self.client.chat([]))

        # Test invalid message structure
        with self.assertRaises(ValidationError):
            asyncio.run(self.client.chat([{"role": "user"}]))

        # Test invalid role
        with self.assertRaises(ValidationError):
            asyncio.run(self.client.chat([{"role": "invalid", "content": "Hello"}]))

        # Test too many messages
        with self.assertRaises(ValidationError):
            asyncio.run(self.client.chat([{"role": "user", "content": "Hello"}] * 51))

    def test_error_message_generation(self) -> None:
        """Test error message generation for different status codes."""
        # Test 400 error
        error_msg = self.client._get_error_message(400, {"error": {"message": "Bad request"}})
        self.assertIn("Invalid or missing request parameters", error_msg)
        self.assertIn("Bad request", error_msg)

        # Test 401 error
        error_msg = self.client._get_error_message(401, {"error": "Unauthorized"})
        self.assertIn("Authentication failed", error_msg)
        self.assertIn("Unauthorized", error_msg)

        # Test 402 error
        error_msg = self.client._get_error_message(402, {})
        self.assertIn("Insufficient account balance", error_msg)

        # Test 404 error
        error_msg = self.client._get_error_message(404, {})
        self.assertIn("Requested resource not found", error_msg)

        # Test 429 error
        error_msg = self.client._get_error_message(429, {})
        self.assertIn("Rate limit exceeded", error_msg)

        # Test 500 error
        error_msg = self.client._get_error_message(500, {})
        self.assertIn("Internal server error", error_msg)

        # Test unknown status code
        error_msg = self.client._get_error_message(999, {})
        self.assertIn("HTTP 999 error", error_msg)


if __name__ == "__main__":
    unittest.main()
