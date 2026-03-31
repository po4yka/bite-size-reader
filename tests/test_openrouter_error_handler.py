"""Tests for OpenRouter error handler provider rejection detection."""

from __future__ import annotations

import pytest

from app.adapters.openrouter.error_handler import ErrorHandler


@pytest.fixture
def handler() -> ErrorHandler:
    return ErrorHandler(max_retries=2, auto_fallback_structured=True)


class TestIsProviderSpecificRejection:
    def test_anthropic_robots_txt(self, handler: ErrorHandler) -> None:
        data = {
            "error": {
                "message": "Provider returned error",
                "code": 400,
                "metadata": {
                    "raw": '{"type":"error","error":{"type":"invalid_request_error",'
                    '"message":"This URL is disallowed by the website\'s robots.txt file."}}',
                    "provider_name": "Azure",
                    "is_byok": False,
                },
            }
        }
        assert handler.is_provider_specific_rejection(data) is True

    def test_anthropic_unable_to_download(self, handler: ErrorHandler) -> None:
        data = {
            "error": {
                "message": "Provider returned error",
                "code": 400,
                "metadata": {
                    "raw": '{"type":"error","error":{"type":"invalid_request_error",'
                    '"message":"Unable to download the file."}}',
                    "provider_name": "Anthropic",
                    "is_byok": False,
                },
            }
        }
        assert handler.is_provider_specific_rejection(data) is True

    def test_alibaba_content_moderation(self, handler: ErrorHandler) -> None:
        data = {
            "error": {
                "message": "Provider returned error",
                "code": 400,
                "metadata": {
                    "raw": '{"error":{"message":"Input data may contain inappropriate content.",'
                    '"type":"data_inspection_failed"}}',
                    "provider_name": "Alibaba",
                    "is_byok": False,
                },
            }
        }
        assert handler.is_provider_specific_rejection(data) is True

    def test_alibaba_free_tier_exhausted(self, handler: ErrorHandler) -> None:
        data = {
            "error": {
                "message": "Provider returned error",
                "code": 400,
                "metadata": {
                    "raw": '{"error":{"message":"The free tier of the model has been exhausted.",'
                    '"type":"AllocationQuota.FreeTierOnly"}}',
                    "provider_name": "Alibaba",
                    "is_byok": False,
                },
            }
        }
        assert handler.is_provider_specific_rejection(data) is True

    def test_openrouter_own_400_no_provider(self, handler: ErrorHandler) -> None:
        """OpenRouter's own validation errors have no provider_name."""
        data = {
            "error": {
                "message": "anthropic/invalid-model is not a valid model ID",
                "code": 400,
            }
        }
        assert handler.is_provider_specific_rejection(data) is False

    def test_openrouter_402_no_metadata(self, handler: ErrorHandler) -> None:
        data = {
            "error": {
                "message": "Insufficient credits.",
                "code": 402,
            }
        }
        assert handler.is_provider_specific_rejection(data) is False

    def test_empty_data(self, handler: ErrorHandler) -> None:
        assert handler.is_provider_specific_rejection({}) is False

    def test_malformed_error(self, handler: ErrorHandler) -> None:
        assert handler.is_provider_specific_rejection({"error": "string"}) is False

    def test_metadata_without_provider(self, handler: ErrorHandler) -> None:
        data = {
            "error": {
                "message": "Some error",
                "code": 400,
                "metadata": {"is_byok": False},
            }
        }
        assert handler.is_provider_specific_rejection(data) is False
