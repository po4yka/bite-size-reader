"""Test OpenRouter API compliance according to official documentation."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.adapters.openrouter_client import OpenRouterClient


class TestOpenRouterCompliance:
    """Test OpenRouter API compliance with official documentation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.client = OpenRouterClient(
            api_key="sk-or-test-key",
            model="openai/gpt-4o-mini",
            fallback_models=["anthropic/claude-3.5-sonnet"],
            http_referer="https://github.com/test-repo",
            x_title="Test Bot",
            timeout_sec=30,
            max_retries=2,
            debug_payloads=True,
        )

    @pytest.mark.asyncio
    async def test_correct_api_endpoint(self):
        """Test that the correct API endpoint is used."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "Test response"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            await self.client.chat([{"role": "user", "content": "Hello"}])

            # Verify the correct endpoint is called
            call_args = mock_client.return_value.__aenter__.return_value.post.call_args
            assert call_args[0][0] == "https://openrouter.co/v1/chat/completions"

    @pytest.mark.asyncio
    async def test_authentication_header(self):
        """Test that Authorization header is correctly formatted."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "Test response"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            await self.client.chat([{"role": "user", "content": "Hello"}])

            # Verify Authorization header
            call_args = mock_client.return_value.__aenter__.return_value.post.call_args
            headers = call_args[1]["headers"]
            assert headers["Authorization"] == "Bearer sk-or-test-key"

    @pytest.mark.asyncio
    async def test_request_structure(self):
        """Test that request body follows OpenAI-compatible format."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "Test response"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "What is the meaning of life?"},
            ]
            await self.client.chat(messages, temperature=0.7, max_tokens=100)

            # Verify request body structure
            call_args = mock_client.return_value.__aenter__.return_value.post.call_args
            body = call_args[1]["json"]
            assert body["model"] == "openai/gpt-4o-mini"
            assert body["messages"] == messages
            assert body["temperature"] == 0.7
            assert body["max_tokens"] == 100

    @pytest.mark.asyncio
    async def test_optional_parameters(self):
        """Test that optional parameters are correctly handled."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "Test response"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            await self.client.chat(
                [{"role": "user", "content": "Hello"}],
                temperature=0.5,
                max_tokens=50,
                top_p=0.9,
                stream=True,
            )

            # Verify optional parameters
            call_args = mock_client.return_value.__aenter__.return_value.post.call_args
            body = call_args[1]["json"]
            assert body["temperature"] == 0.5
            assert body["max_tokens"] == 50
            assert body["top_p"] == 0.9
            assert body["stream"] is True

    @pytest.mark.asyncio
    async def test_http_headers(self):
        """Test that all required headers are present."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "Test response"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            await self.client.chat([{"role": "user", "content": "Hello"}])

            # Verify headers
            call_args = mock_client.return_value.__aenter__.return_value.post.call_args
            headers = call_args[1]["headers"]
            assert headers["Content-Type"] == "application/json"
            assert headers["HTTP-Referer"] == "https://github.com/test-repo"
            assert headers["X-Title"] == "Test Bot"

    @pytest.mark.asyncio
    async def test_error_handling_400(self):
        """Test handling of 400 Bad Request error."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 400
            mock_response.json.return_value = {"error": {"message": "Invalid request parameters"}}
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await self.client.chat([{"role": "user", "content": "Hello"}])

            assert result.status == "error"
            assert "Invalid or missing request parameters" in result.error_text
            assert "Invalid request parameters" in result.error_text

    @pytest.mark.asyncio
    async def test_error_handling_401(self):
        """Test handling of 401 Unauthorized error."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 401
            mock_response.json.return_value = {"error": {"message": "Invalid API key"}}
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await self.client.chat([{"role": "user", "content": "Hello"}])

            assert result.status == "error"
            assert "Authentication failed" in result.error_text
            assert "Invalid API key" in result.error_text

    @pytest.mark.asyncio
    async def test_error_handling_402(self):
        """Test handling of 402 Payment Required error."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 402
            mock_response.json.return_value = {"error": {"message": "Insufficient credits"}}
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await self.client.chat([{"role": "user", "content": "Hello"}])

            assert result.status == "error"
            assert "Insufficient account balance" in result.error_text
            assert "Insufficient credits" in result.error_text

    @pytest.mark.asyncio
    async def test_error_handling_404(self):
        """Test handling of 404 Not Found error."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 404
            mock_response.json.return_value = {"error": {"message": "Model not found"}}
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await self.client.chat([{"role": "user", "content": "Hello"}])

            assert result.status == "error"
            assert "Requested resource not found" in result.error_text
            assert "Model not found" in result.error_text

    @pytest.mark.asyncio
    async def test_error_handling_429_with_retry_after(self):
        """Test handling of 429 Rate Limit with retry-after header."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 429
            mock_response.headers = {"retry-after": "5"}
            mock_response.json.return_value = {"error": {"message": "Rate limit exceeded"}}
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            with patch("asyncio.sleep") as mock_sleep:
                await self.client.chat([{"role": "user", "content": "Hello"}])

                # Should have called sleep with retry-after value
                mock_sleep.assert_called_with(5)

    @pytest.mark.asyncio
    async def test_error_handling_500(self):
        """Test handling of 500 Internal Server Error."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.json.return_value = {"error": {"message": "Internal server error"}}
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            with patch("asyncio.sleep") as mock_sleep:
                await self.client.chat([{"role": "user", "content": "Hello"}])

                # Should have retried with exponential backoff
                assert mock_sleep.call_count > 0

    @pytest.mark.asyncio
    async def test_success_response_parsing(self):
        """Test parsing of successful response."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "Test response"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                "model": "openai/gpt-4o-mini",
            }
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await self.client.chat([{"role": "user", "content": "Hello"}])

            assert result.status == "ok"
            assert result.response_text == "Test response"
            assert result.tokens_prompt == 10
            assert result.tokens_completion == 5
            assert result.model == "openai/gpt-4o-mini"
            assert result.endpoint == "/v1/chat/completions"

    @pytest.mark.asyncio
    async def test_models_endpoint(self):
        """Test models endpoint functionality."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "data": [
                    {"id": "openai/gpt-4o-mini", "name": "GPT-4o Mini"},
                    {"id": "anthropic/claude-3.5-sonnet", "name": "Claude 3.5 Sonnet"},
                ]
            }
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            models = await self.client.get_models()

            # Verify models endpoint is called
            call_args = mock_client.return_value.__aenter__.return_value.get.call_args
            assert call_args[0][0] == "https://openrouter.co/v1/models"

            # Verify response
            assert "data" in models
            assert len(models["data"]) == 2

    @pytest.mark.asyncio
    async def test_fallback_models(self):
        """Test fallback model functionality."""
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
                            "model": "anthropic/claude-3.5-sonnet",
                        }
                    ),
                ),
            ]
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=mock_responses
            )

            with patch("asyncio.sleep"):
                result = await self.client.chat([{"role": "user", "content": "Hello"}])

                assert result.status == "ok"
                assert result.response_text == "Fallback response"
                assert result.model == "anthropic/claude-3.5-sonnet"

    def test_parameter_validation(self):
        """Test parameter validation."""
        # Test invalid temperature
        with pytest.raises(ValueError, match="Temperature must be between 0 and 2"):
            asyncio.run(self.client.chat([{"role": "user", "content": "Hello"}], temperature=3.0))

        # Test invalid max_tokens
        with pytest.raises(ValueError, match="Max tokens must be a positive integer"):
            asyncio.run(self.client.chat([{"role": "user", "content": "Hello"}], max_tokens=-1))

        # Test invalid top_p
        with pytest.raises(ValueError, match="Top_p must be between 0 and 1"):
            asyncio.run(self.client.chat([{"role": "user", "content": "Hello"}], top_p=1.5))

        # Test invalid stream
        with pytest.raises(ValueError, match="Stream must be boolean"):
            asyncio.run(self.client.chat([{"role": "user", "content": "Hello"}], stream="true"))

    def test_message_validation(self):
        """Test message structure validation."""
        # Test empty messages
        with pytest.raises(ValueError, match="Messages list is required"):
            asyncio.run(self.client.chat([]))

        # Test invalid message structure
        with pytest.raises(ValueError, match="Message 0 missing required fields"):
            asyncio.run(self.client.chat([{"role": "user"}]))

        # Test invalid role
        with pytest.raises(ValueError, match="Message 0 has invalid role"):
            asyncio.run(self.client.chat([{"role": "invalid", "content": "Hello"}]))

        # Test too many messages
        with pytest.raises(ValueError, match="Too many messages"):
            asyncio.run(self.client.chat([{"role": "user", "content": "Hello"}] * 51))

    def test_error_message_generation(self):
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
