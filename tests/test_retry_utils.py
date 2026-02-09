"""Tests for retry utilities with exponential backoff."""

import asyncio
import unittest
from unittest.mock import AsyncMock

from app.utils.retry_utils import is_transient_error, retry_telegram_operation, retry_with_backoff


class MockHTTPResponse:
    """Mock HTTP response object with status_code attribute."""

    def __init__(self, status_code: int, message: str = ""):
        self.status_code = status_code
        self.message = message


class MockHTTPExceptionWithResponse(Exception):
    """Mock HTTP exception with response attribute."""

    def __init__(self, response: MockHTTPResponse, message: str = ""):
        super().__init__(message)
        self.response = response


class MockHTTPExceptionWithStatus(Exception):
    """Mock HTTP exception with direct status_code attribute."""

    def __init__(self, status_code: int, message: str = ""):
        super().__init__(message)
        self.status_code = status_code


class TestIsTransientError(unittest.TestCase):
    """Test suite for transient error detection."""

    def test_timeout_error_is_transient(self):
        """Test that timeout errors are detected as transient."""
        error = TimeoutError("Connection timeout")
        assert is_transient_error(error)

    def test_connection_error_in_message(self):
        """Test that connection errors in message are transient."""
        error = Exception("Connection reset by peer")
        assert is_transient_error(error)

    def test_network_error_in_message(self):
        """Test that network errors in message are transient."""
        error = Exception("Network is unreachable")
        assert is_transient_error(error)

    def test_rate_limit_error_is_transient(self):
        """Test that rate limit errors are transient."""
        error = Exception("Rate limit exceeded, try again later")
        assert is_transient_error(error)

    def test_too_many_requests_is_transient(self):
        """Test that 'too many requests' errors are transient."""
        error = Exception("Too many requests")
        assert is_transient_error(error)

    def test_temporary_error_is_transient(self):
        """Test that temporary errors are transient."""
        error = Exception("Temporary failure in name resolution")
        assert is_transient_error(error)

    def test_service_unavailable_is_transient(self):
        """Test that service unavailable errors are transient."""
        error = Exception("503 Service Unavailable")
        assert is_transient_error(error)

    def test_gateway_errors_are_transient(self):
        """Test that gateway errors are transient."""
        error1 = Exception("502 Bad Gateway")
        error2 = Exception("504 Gateway Timeout")
        assert is_transient_error(error1)
        assert is_transient_error(error2)

    def test_message_not_modified_is_not_transient(self):
        """Test that 'message is not modified' is NOT treated as transient."""
        error = Exception("Message is not modified")
        assert not is_transient_error(error)

    def test_permanent_error_is_not_transient(self):
        """Test that permanent errors are not transient."""
        error = Exception("Invalid chat_id specified")
        assert not is_transient_error(error)

    def test_validation_error_is_not_transient(self):
        """Test that validation errors are not transient."""
        error = ValueError("Invalid parameter")
        assert not is_transient_error(error)

    def test_auth_error_is_not_transient(self):
        """Test that authentication errors are not transient."""
        error = Exception("401 Unauthorized")
        assert not is_transient_error(error)

    def test_not_found_error_is_not_transient(self):
        """Test that 404 errors are not transient."""
        error = Exception("404 Not Found")
        assert not is_transient_error(error)

    def test_http_error_with_429_status_is_transient(self):
        """Test HTTP error with 429 status code via response.status_code."""
        response = MockHTTPResponse(429, "Too Many Requests")
        error = MockHTTPExceptionWithResponse(response, "Rate limit exceeded")
        assert is_transient_error(error)

    def test_http_error_with_408_status_is_transient(self):
        """Test HTTP error with 408 Request Timeout via response.status_code."""
        response = MockHTTPResponse(408, "Request Timeout")
        error = MockHTTPExceptionWithResponse(response)
        assert is_transient_error(error)

    def test_http_error_with_500_status_is_transient(self):
        """Test HTTP error with 500 Internal Server Error via response.status_code."""
        response = MockHTTPResponse(500, "Internal Server Error")
        error = MockHTTPExceptionWithResponse(response)
        assert is_transient_error(error)

    def test_http_error_with_502_status_is_transient(self):
        """Test HTTP error with 502 Bad Gateway via response.status_code."""
        response = MockHTTPResponse(502)
        error = MockHTTPExceptionWithResponse(response, "Bad Gateway")
        assert is_transient_error(error)

    def test_http_error_with_503_status_is_transient(self):
        """Test HTTP error with 503 Service Unavailable via response.status_code."""
        response = MockHTTPResponse(503)
        error = MockHTTPExceptionWithResponse(response)
        assert is_transient_error(error)

    def test_http_error_with_504_status_is_transient(self):
        """Test HTTP error with 504 Gateway Timeout via response.status_code."""
        response = MockHTTPResponse(504)
        error = MockHTTPExceptionWithResponse(response)
        assert is_transient_error(error)

    def test_http_error_with_400_not_modified_is_not_transient(self):
        """Test HTTP 400 'not modified' error is not transient."""
        response = MockHTTPResponse(400, "Message is not modified")
        error = MockHTTPExceptionWithResponse(response, "Message is not modified")
        assert not is_transient_error(error)

    def test_http_error_with_404_is_not_transient(self):
        """Test HTTP 404 error is not transient via response.status_code."""
        response = MockHTTPResponse(404, "Not Found")
        error = MockHTTPExceptionWithResponse(response, "Resource not found")
        assert not is_transient_error(error)

    def test_http_error_with_401_is_not_transient(self):
        """Test HTTP 401 error is not transient via response.status_code."""
        response = MockHTTPResponse(401, "Unauthorized")
        error = MockHTTPExceptionWithResponse(response, "Unauthorized access")
        assert not is_transient_error(error)

    def test_http_error_with_invalid_status_code_type(self):
        """Test HTTP error with invalid status_code type doesn't crash."""
        response = MockHTTPResponse("not_a_number")  # Invalid type
        error = MockHTTPExceptionWithResponse(response, "Invalid status")
        # Should not crash, falls back to string checking
        result = is_transient_error(error)
        assert isinstance(result, bool)

    def test_direct_status_code_429_is_transient(self):
        """Test error with direct status_code attribute (429)."""
        error = MockHTTPExceptionWithStatus(429, "Rate limit")
        assert is_transient_error(error)

    def test_direct_status_code_408_is_transient(self):
        """Test error with direct status_code attribute (408)."""
        error = MockHTTPExceptionWithStatus(408, "Timeout")
        assert is_transient_error(error)

    def test_direct_status_code_500_is_transient(self):
        """Test error with direct status_code attribute (500)."""
        error = MockHTTPExceptionWithStatus(500, "Server error")
        assert is_transient_error(error)

    def test_direct_status_code_503_is_transient(self):
        """Test error with direct status_code attribute (503)."""
        error = MockHTTPExceptionWithStatus(503, "Service unavailable")
        assert is_transient_error(error)

    def test_direct_status_code_400_not_modified_is_not_transient(self):
        """Test direct status_code 400 with 'not modified' message is not transient."""
        error = MockHTTPExceptionWithStatus(400, "Message is not modified")
        assert not is_transient_error(error)

    def test_direct_status_code_404_is_not_transient(self):
        """Test error with direct status_code 404 is not transient."""
        error = MockHTTPExceptionWithStatus(404, "Not found")
        assert not is_transient_error(error)

    def test_direct_status_code_invalid_type(self):
        """Test error with invalid direct status_code type doesn't crash."""
        error = MockHTTPExceptionWithStatus("invalid", "Some error message")
        # Should not crash, falls back to string checking
        result = is_transient_error(error)
        assert isinstance(result, bool)

    def test_message_not_modified_lowercase(self):
        """Test message_not_modified in lowercase is not transient."""
        error = Exception("message_not_modified")
        assert not is_transient_error(error)

    def test_deadline_exceeded_is_transient(self):
        """Test deadline exceeded errors are transient."""
        error = Exception("deadline exceeded")
        assert is_transient_error(error)

    def test_flood_error_is_transient(self):
        """Test flood errors are transient."""
        error = Exception("Flood wait 5 seconds")
        assert is_transient_error(error)

    def test_retry_after_is_transient(self):
        """Test 'retry after' errors are transient."""
        error = Exception("Retry after 30 seconds")
        assert is_transient_error(error)


class TestRetryWithBackoff(unittest.IsolatedAsyncioTestCase):
    """Test suite for retry_with_backoff function."""

    async def test_success_on_first_try(self):
        """Test that successful operation on first try works."""
        mock_func = AsyncMock(return_value="success")

        result, success = await retry_with_backoff(mock_func, max_retries=3)

        assert success is True
        assert result == "success"
        assert mock_func.call_count == 1

    async def test_success_after_one_retry(self):
        """Test that function succeeds after one retry."""
        call_count = 0

        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Timeout - temporary issue")
            return "success"

        result, success = await retry_with_backoff(flaky_func, max_retries=3, initial_delay=0.01)

        assert success is True
        assert result == "success"
        assert call_count == 2

    async def test_success_after_multiple_retries(self):
        """Test that function succeeds after multiple retries."""
        call_count = 0

        async def very_flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise Exception("Network error")
            return "finally worked"

        result, success = await retry_with_backoff(
            very_flaky_func, max_retries=3, initial_delay=0.01
        )

        assert success is True
        assert result == "finally worked"
        assert call_count == 3

    async def test_failure_after_all_retries(self):
        """Test that function fails after exhausting all retries."""
        mock_func = AsyncMock(side_effect=Exception("Timeout"))

        result, success = await retry_with_backoff(mock_func, max_retries=2, initial_delay=0.01)

        assert success is False
        assert result is None
        assert mock_func.call_count == 3  # Initial + 2 retries

    async def test_non_transient_error_no_retry(self):
        """Test that non-transient errors are not retried."""
        mock_func = AsyncMock(side_effect=Exception("Invalid parameter"))

        result, success = await retry_with_backoff(mock_func, max_retries=3, initial_delay=0.01)

        assert success is False
        assert result is None
        assert mock_func.call_count == 1  # No retries for non-transient

    async def test_exponential_backoff_delays(self):
        """Test that delays increase exponentially."""
        delays = []
        call_times = []

        async def failing_func():
            call_times.append(asyncio.get_event_loop().time())
            raise Exception("Network timeout")

        await retry_with_backoff(
            failing_func,
            max_retries=3,
            initial_delay=0.1,
            backoff_factor=2.0,
        )

        # Calculate actual delays between calls
        if len(call_times) >= 2:
            for i in range(1, len(call_times)):
                delay = call_times[i] - call_times[i - 1]
                delays.append(delay)

            # Delays should approximately follow: 0.1, 0.2, 0.4
            # Allow some variance for timing
            if len(delays) >= 2:
                assert delays[1] > delays[0]  # Second delay should be longer

    async def test_max_delay_cap(self):
        """Test that delay is capped at max_delay."""
        delays = []
        call_times = []

        async def failing_func():
            call_times.append(asyncio.get_event_loop().time())
            raise Exception("Connection error")

        await retry_with_backoff(
            failing_func,
            max_retries=5,
            initial_delay=1.0,
            max_delay=0.2,  # Max delay is smaller than initial!
            backoff_factor=2.0,
        )

        # Calculate actual delays
        if len(call_times) >= 2:
            for i in range(1, len(call_times)):
                delay = call_times[i] - call_times[i - 1]
                delays.append(delay)

            # All delays should be capped at max_delay (0.2s)
            for delay in delays:
                assert delay <= 0.3  # Allow some variance

    async def test_function_with_arguments(self):
        """Test that function arguments are passed correctly."""
        mock_func = AsyncMock(return_value="result")

        _result, success = await retry_with_backoff(
            mock_func,
            "arg1",
            "arg2",
            kwarg1="value1",
            max_retries=2,
        )

        assert success is True
        mock_func.assert_called_with("arg1", "arg2", kwarg1="value1")

    async def test_zero_retries(self):
        """Test behavior with zero retries configured."""
        mock_func = AsyncMock(side_effect=Exception("Timeout"))

        _result, success = await retry_with_backoff(mock_func, max_retries=0, initial_delay=0.01)

        assert success is False
        assert mock_func.call_count == 1  # Only initial attempt


class TestRetryTelegramOperation(unittest.IsolatedAsyncioTestCase):
    """Test suite for retry_telegram_operation wrapper."""

    async def test_telegram_retry_success(self):
        """Test successful Telegram operation."""
        mock_func = AsyncMock(return_value={"message_id": 123})

        result, success = await retry_telegram_operation(mock_func, operation_name="test_operation")

        assert success is True
        assert result == {"message_id": 123}

    async def test_telegram_retry_with_retries(self):
        """Test Telegram operation that succeeds after retries."""
        call_count = 0

        async def telegram_api():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Rate limit exceeded")
            return {"status": "ok"}

        result, success = await retry_telegram_operation(
            telegram_api, operation_name="send_message"
        )

        assert success is True
        assert result == {"status": "ok"}
        assert call_count == 2

    async def test_telegram_retry_failure(self):
        """Test Telegram operation that fails after all retries."""
        mock_func = AsyncMock(side_effect=Exception("Network timeout"))

        result, success = await retry_telegram_operation(mock_func, operation_name="edit_message")

        assert success is False
        assert result is None
        assert mock_func.call_count == 4  # Initial + 3 retries (default)

    async def test_telegram_retry_default_params(self):
        """Test that telegram retry uses sensible defaults."""
        call_count = 0
        call_times = []

        async def telegram_api():
            nonlocal call_count
            call_count += 1
            call_times.append(asyncio.get_event_loop().time())
            raise Exception("Connection timeout")

        await retry_telegram_operation(telegram_api, operation_name="test")

        # Should try initial + 3 retries
        assert call_count == 4

        # Check that delays are reasonable (should start at 0.5s with 2x backoff)
        if len(call_times) >= 2:
            first_delay = call_times[1] - call_times[0]
            # Should be around 0.5s (allow variance for test timing)
            assert 0.3 < first_delay < 0.8


class TestEdgeCases(unittest.IsolatedAsyncioTestCase):
    """Test edge cases for retry logic."""

    async def test_function_returns_none(self):
        """Test that functions returning None are handled correctly."""
        mock_func = AsyncMock(return_value=None)

        result, success = await retry_with_backoff(mock_func)

        assert success is True
        assert result is None

    async def test_function_returns_false(self):
        """Test that functions returning False are handled correctly."""
        mock_func = AsyncMock(return_value=False)

        result, success = await retry_with_backoff(mock_func)

        assert success is True
        assert result is False

    async def test_exception_in_first_call_then_success(self):
        """Test recovery from initial exception."""
        call_count = 0

        async def func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError("First call timeout")
            return "recovered"

        result, success = await retry_with_backoff(func, initial_delay=0.01)

        assert success is True
        assert result == "recovered"
