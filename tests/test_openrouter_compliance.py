"""Test OpenRouter API compliance according to official documentation."""

import asyncio
import json
import unittest
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from app.adapters.openrouter.openrouter_client import OpenRouterClient


class FakeResponse:
    def __init__(self, status_code, json_data, headers=None, content=None, text=None, history=None):
        self.status_code = status_code
        self._json_data = json_data
        self.headers = headers or {}
        self.content = content if content is not None else json.dumps(json_data).encode("utf-8")
        self.text = text if text is not None else json.dumps(json_data)
        self.elapsed = timedelta(seconds=0.001)
        self.request = MagicMock()  # Mock the request object
        self.history = history if history is not None else []  # Ensure history is present

    def json(self):
        return self._json_data

    async def __aiter__(self):
        yield self.content

    async def aclose(self):
        pass

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP Error: {self.status_code}")


class TestOpenRouterCompliance(unittest.TestCase):
    """Test OpenRouter API compliance with official documentation."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        from app.adapters.openrouter.model_capabilities import ModelCapabilities

        ModelCapabilities._structured_models = None  # Ensure cache is empty for fresh mock

        # Patch _fetch_structured_models to control reported structured-output capable models
        self.patcher_fetch_structured_models = patch(
            "app.adapters.openrouter.model_capabilities.ModelCapabilities._fetch_structured_models",
            new_callable=AsyncMock,
        )
        self.mock_fetch_structured_models = self.patcher_fetch_structured_models.start()
        self.mock_fetch_structured_models.return_value = {"qwen/qwen3-max"}
        self.addCleanup(self.patcher_fetch_structured_models.stop)

        self.client = OpenRouterClient(
            api_key="sk-or-test-key",
            model="qwen/qwen3-max",
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
                mock_response = FakeResponse(
                    status_code=200,
                    json_data={
                        "choices": [{"message": {"content": "Test response"}}],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                    },
                )
                mock_client.return_value.post = AsyncMock(return_value=mock_response)

                await self.client.chat([{"role": "user", "content": "Hello"}])

                # Verify the correct endpoint is called
                call_args = mock_client.return_value.post.call_args
                assert call_args[0][0] == "/chat/completions"

        asyncio.run(_test())

    def test_authentication_header(self) -> None:
        """Test that Authorization header is correctly formatted."""

        async def _test() -> None:
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = FakeResponse(
                    status_code=200,
                    json_data={
                        "choices": [{"message": {"content": "Test response"}}],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                    },
                )
                mock_client.return_value.post = AsyncMock(return_value=mock_response)

                await self.client.chat([{"role": "user", "content": "Hello"}])

                # Verify Authorization header
                call_args = mock_client.return_value.post.call_args
                headers = call_args[1]["headers"]
                assert headers["Authorization"] == "Bearer sk-or-test-key"

        asyncio.run(_test())

    def test_request_structure(self) -> None:
        """Test that request body follows OpenAI-compatible format."""

        async def _test() -> None:
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = FakeResponse(
                    status_code=200,
                    json_data={
                        "choices": [{"message": {"content": "Test response"}}],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                    },
                )
                mock_client.return_value.post = AsyncMock(return_value=mock_response)

                messages = [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "What is the meaning of life?"},
                ]
                await self.client.chat(messages, temperature=0.7, max_tokens=100)

                # Verify request body structure
                call_args = mock_client.return_value.post.call_args
                body = call_args[1]["json"]
                assert body["model"] == "qwen/qwen3-max"
                assert body["messages"] == messages
                assert body["temperature"] == 0.7
                assert body["max_tokens"] == 100

        asyncio.run(_test())

    def test_optional_parameters(self) -> None:
        """Test that optional parameters are correctly handled."""

        async def _test() -> None:
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = FakeResponse(
                    status_code=200,
                    json_data={
                        "choices": [{"message": {"content": "Test response"}}],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                    },
                )
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
                assert body["temperature"] == 0.5
                assert body["max_tokens"] == 50
                assert body["top_p"] == 0.9
                assert body["stream"]

        asyncio.run(_test())

    def test_http_headers(self) -> None:
        """Test that all required headers are present."""

        async def _test() -> None:
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = FakeResponse(
                    status_code=200,
                    json_data={
                        "choices": [{"message": {"content": "Test response"}}],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                    },
                )
                mock_client.return_value.post = AsyncMock(return_value=mock_response)

                await self.client.chat([{"role": "user", "content": "Hello"}])

                # Verify headers
                call_args = mock_client.return_value.post.call_args
                headers = call_args[1]["headers"]
                assert headers["Content-Type"] == "application/json"
                assert headers["HTTP-Referer"] == "https://github.com/test-repo"
                assert headers["X-Title"] == "Test Bot"

        asyncio.run(_test())

    def test_error_handling_400(self) -> None:
        """Test handling of 400 Bad Request error."""

        async def _test() -> None:
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = FakeResponse(
                    status_code=400, json_data={"error": {"message": "Invalid request parameters"}}
                )
                mock_client.return_value.post = AsyncMock(return_value=mock_response)

                result = await self.client.chat([{"role": "user", "content": "Hello"}])

                assert result.status == "error"
                assert "Invalid or missing request parameters" in result.error_text

        asyncio.run(_test())

    def test_error_handling_401(self) -> None:
        """Test handling of 401 Unauthorized error."""

        async def _test() -> None:
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = FakeResponse(
                    status_code=401, json_data={"error": {"message": "Invalid API key"}}
                )
                mock_client.return_value.post = AsyncMock(return_value=mock_response)

                result = await self.client.chat([{"role": "user", "content": "Hello"}])

                assert result.status == "error"
                assert "Authentication failed" in result.error_text

        asyncio.run(_test())

    def test_error_handling_402(self) -> None:
        """Test handling of 402 Payment Required error."""

        async def _test() -> None:
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = FakeResponse(
                    status_code=402, json_data={"error": {"message": "Insufficient credits"}}
                )
                mock_client.return_value.post = AsyncMock(return_value=mock_response)

                result = await self.client.chat([{"role": "user", "content": "Hello"}])

                assert result.status == "error"
                assert "Insufficient account balance" in result.error_text

        asyncio.run(_test())

    def test_error_handling_404(self) -> None:
        """Test handling of 404 Not Found error."""

        async def _test() -> None:
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = FakeResponse(
                    status_code=404, json_data={"error": {"message": "Model not found"}}
                )
                mock_client.return_value.post = AsyncMock(return_value=mock_response)

                result = await self.client.chat([{"role": "user", "content": "Hello"}])

                assert result.status == "error"
                assert "Requested resource not found" in result.error_text

        asyncio.run(_test())

    def test_error_handling_429_with_retry_after(self) -> None:
        """Test handling of 429 Rate Limit with retry-after header."""

        async def _test() -> None:
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = FakeResponse(
                    status_code=429,
                    json_data={"error": {"message": "Rate limit exceeded"}},
                    headers={"retry-after": "5"},
                )
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
                mock_response = FakeResponse(
                    status_code=500, json_data={"error": {"message": "Internal server error"}}
                )
                mock_client.return_value.post = AsyncMock(return_value=mock_response)

                with patch("asyncio.sleep") as mock_sleep:
                    await self.client.chat([{"role": "user", "content": "Hello"}])

                    # Should have retried with exponential backoff
                    assert mock_sleep.call_count > 0

        asyncio.run(_test())

    def test_success_response_parsing(self) -> None:
        """Test parsing of successful response."""

        async def _test() -> None:
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = FakeResponse(
                    status_code=200,
                    json_data={
                        "choices": [{"message": {"content": "Test response"}}],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                        "model": "deepseek/deepseek-v3.2",
                    },
                )
                mock_client.return_value.post = AsyncMock(return_value=mock_response)

                result = await self.client.chat([{"role": "user", "content": "Hello"}])

                assert result.status == "ok"
                assert result.response_text == "Test response"
                assert result.tokens_prompt == 10
                assert result.tokens_completion == 5
                assert result.model == "deepseek/deepseek-v3.2"
                assert result.endpoint == "/api/v1/chat/completions"

        asyncio.run(_test())

    def test_structured_output_content_with_json_part(self) -> None:
        """Ensure content lists containing JSON parts are parsed correctly."""

        async def _test() -> None:
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = FakeResponse(
                    status_code=200,
                    json_data={
                        "id": "test-response",
                        "model": "qwen/qwen3-max",
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
                                                "summary_1000": "Medium summary",
                                                "tldr": "Longer summary",
                                            },
                                        },
                                    ],
                                },
                                "finish_reason": "stop",
                                "native_finish_reason": "completed",
                            }
                        ],
                    },
                )
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
                                "tldr": {"type": "string"},
                            },
                            "required": ["summary_250", "summary_1000", "tldr"],
                        },
                    },
                }

                result = await self.client.chat(
                    [{"role": "user", "content": "Hello"}],
                    response_format=response_format,
                )

                assert result.status == "ok"
                assert result.response_text is not None
                parsed = json.loads(result.response_text or "{}")
                assert parsed["summary_250"] == "Short summary"
                assert parsed["summary_1000"] == "Medium summary"
                assert parsed["tldr"] == "Longer summary"

        asyncio.run(_test())

    def test_models_endpoint(self) -> None:
        """Test models endpoint functionality."""

        async def _test() -> None:
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = FakeResponse(
                    status_code=200,
                    json_data={
                        "data": [
                            {"id": "deepseek/deepseek-v3.2", "name": "DeepSeek V3"},
                            {"id": "google/gemini-2.5-pro", "name": "Gemini 2.5 Pro"},
                        ]
                    },
                )
                mock_response.raise_for_status = Mock()  # type: ignore[method-assign]
                mock_client.return_value.get = AsyncMock(return_value=mock_response)
                mock_client.return_value.__aenter__.return_value = mock_client.return_value
                mock_client.return_value.__aexit__.return_value = AsyncMock(return_value=None)

                models = await self.client.get_models()

                # Verify models endpoint is called
                call_args = mock_client.return_value.get.call_args
                assert call_args[0][0] == "https://openrouter.ai/api/v1/models"

                # Verify response
                assert "data" in models
                assert len(models["data"]) == 2

        asyncio.run(_test())

    def test_fallback_models(self) -> None:
        """Test fallback model functionality."""

        async def _test() -> None:
            with patch("httpx.AsyncClient") as mock_client:
                # First call fails, second succeeds
                mock_responses = [
                    FakeResponse(status_code=500, json_data={"error": "Server error"}),
                    FakeResponse(
                        status_code=200,
                        json_data={
                            "choices": [{"message": {"content": "Fallback response"}}],
                            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                            "model": "google/gemini-2.5-pro",
                        },
                    ),
                ]
                mock_client.return_value.post = AsyncMock(side_effect=mock_responses)

                with patch("asyncio.sleep"):
                    result = await self.client.chat([{"role": "user", "content": "Hello"}])

                    assert result.status == "ok"
                    assert result.response_text == "Fallback response"
                    assert result.model == "google/gemini-2.5-pro"

        asyncio.run(_test())

    def test_parameter_validation(self) -> None:
        """Test parameter validation."""
        from pydantic_core import ValidationError as PydanticValidationError

        from app.adapters.openrouter.exceptions import ValidationError

        # Test invalid temperature
        with pytest.raises(ValidationError):
            asyncio.run(self.client.chat([{"role": "user", "content": "Hello"}], temperature=3.0))

        # Test invalid max_tokens
        with pytest.raises(ValidationError):
            asyncio.run(self.client.chat([{"role": "user", "content": "Hello"}], max_tokens=-1))

        # Test invalid top_p
        with pytest.raises(ValidationError):
            asyncio.run(self.client.chat([{"role": "user", "content": "Hello"}], top_p=1.5))

        # Test invalid stream - Pydantic catches this before our custom validation
        with pytest.raises(PydanticValidationError):
            asyncio.run(self.client.chat([{"role": "user", "content": "Hello"}], stream="true"))  # type: ignore[arg-type]

    def test_message_validation(self) -> None:
        """Test message structure validation."""
        from app.adapters.openrouter.exceptions import ValidationError

        # Test empty messages
        with pytest.raises(ValidationError):
            asyncio.run(self.client.chat([]))

        # Test invalid message structure
        with pytest.raises(ValidationError):
            asyncio.run(self.client.chat([{"role": "user"}]))

        # Test invalid role
        with pytest.raises(ValidationError):
            asyncio.run(self.client.chat([{"role": "invalid", "content": "Hello"}]))

        # Test too many messages
        with pytest.raises(ValidationError):
            asyncio.run(self.client.chat([{"role": "user", "content": "Hello"}] * 51))

    def test_error_message_generation(self) -> None:
        """Test error message generation for different status codes."""
        # Test 400 error
        error_msg = self.client._get_error_message(400, {"error": {"message": "Bad request"}})
        assert "Invalid or missing request parameters" in error_msg
        assert "Bad request" in error_msg

        # Test 401 error
        error_msg = self.client._get_error_message(401, {"error": "Unauthorized"})
        assert "Authentication failed" in error_msg
        assert "Unauthorized" in error_msg

        # Test 402 error
        error_msg = self.client._get_error_message(402, {})
        assert "Insufficient account balance" in error_msg

        # Test 404 error
        error_msg = self.client._get_error_message(404, {})
        assert "Requested resource not found" in error_msg

        # Test 429 error
        error_msg = self.client._get_error_message(429, {})
        assert "Rate limit exceeded" in error_msg

        # Test 500 error
        error_msg = self.client._get_error_message(500, {})
        assert "Internal server error" in error_msg

        # Test unknown status code
        error_msg = self.client._get_error_message(999, {})
        assert "HTTP 999 error" in error_msg


if __name__ == "__main__":
    unittest.main()
