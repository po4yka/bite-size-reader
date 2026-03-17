"""Tests for Firecrawl exception hierarchy."""

from __future__ import annotations

from app.adapters.external.firecrawl.exceptions import (
    APIError,
    ConfigurationError,
    ContentError,
    FirecrawlError,
    NetworkError,
    RateLimitError,
    ResponseSizeExceededError,
    ValidationError,
)


def test_firecrawl_error_basic() -> None:
    err = FirecrawlError("something went wrong")
    assert str(err) == "something went wrong"
    assert err.context == {}


def test_firecrawl_error_with_context() -> None:
    err = FirecrawlError("failure", context={"key": "val"})
    assert "context:" in str(err)
    assert err.context["key"] == "val"


def test_configuration_error_stores_parameter() -> None:
    err = ConfigurationError("bad config", parameter="timeout", value=-1)
    assert err.parameter == "timeout"
    assert err.value == -1
    assert "parameter" in err.context


def test_validation_error_truncates_long_value() -> None:
    long_val = "x" * 200
    err = ValidationError("bad input", field="url", value=long_val)
    assert len(err.context["value"]) <= 100
    assert err.field == "url"


def test_api_error_stores_status_code() -> None:
    err = APIError("server error", status_code=500, error_code="INTERNAL")
    assert err.status_code == 500
    assert err.error_code == "INTERNAL"
    assert err.context["status_code"] == 500


def test_rate_limit_error_defaults() -> None:
    err = RateLimitError()
    assert err.status_code == 429
    assert err.retry_after is None
    assert isinstance(err, APIError)


def test_rate_limit_error_with_retry_after() -> None:
    err = RateLimitError("Too many requests", retry_after=30)
    assert err.retry_after == 30
    assert err.context["retry_after"] == 30


def test_network_error_stores_original() -> None:
    cause = ConnectionRefusedError("refused")
    err = NetworkError("connection failed", original_error=cause, url="https://x.com")
    assert err.original_error is cause
    assert err.url == "https://x.com"
    assert err.context["original_error"] == "ConnectionRefusedError"


def test_content_error_defaults() -> None:
    err = ContentError()
    assert "No content" in str(err)
    assert err.has_markdown is False
    assert err.has_html is False


def test_response_size_exceeded_error() -> None:
    err = ResponseSizeExceededError("too big", actual_size=5_000_000, max_size=1_000_000)
    assert err.actual_size == 5_000_000
    assert err.max_size == 1_000_000
    assert err.context["actual_size_bytes"] == 5_000_000


def test_exception_hierarchy() -> None:
    assert issubclass(RateLimitError, APIError)
    assert issubclass(APIError, FirecrawlError)
    assert issubclass(NetworkError, FirecrawlError)
    assert issubclass(ContentError, FirecrawlError)
    assert issubclass(ConfigurationError, FirecrawlError)
    assert issubclass(ValidationError, FirecrawlError)
