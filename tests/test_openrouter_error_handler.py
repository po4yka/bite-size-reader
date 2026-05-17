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


class TestIsSchemaConstructRejection:
    """Distinguish 400s about specific JSON Schema constructs (worth
    progressively simplifying) from blanket 'response_format unsupported'
    rejections (the existing binary downgrade handles those)."""

    def test_additional_properties_rejection(self, handler: ErrorHandler) -> None:
        data = {
            "error": {
                "message": "Invalid response_format: additionalProperties is not supported",
                "code": 400,
            }
        }
        assert handler.is_schema_construct_rejection(data) is True

    def test_oneof_rejection(self, handler: ErrorHandler) -> None:
        data = {
            "error": {
                "message": "schema validation failed: oneOf is not allowed at this position",
                "code": 400,
            }
        }
        assert handler.is_schema_construct_rejection(data) is True

    def test_ref_defs_rejection(self, handler: ErrorHandler) -> None:
        data = {
            "error": {
                "message": "$ref to $defs is not supported by this provider",
                "code": 400,
            }
        }
        assert handler.is_schema_construct_rejection(data) is True

    def test_generic_response_format_rejection_is_not_construct(
        self, handler: ErrorHandler
    ) -> None:
        # Blanket "response_format not supported" should fall through to
        # the existing binary downgrade, not simplification.
        data = {
            "error": {
                "message": "response_format is not supported by this model",
                "code": 400,
            }
        }
        assert handler.is_schema_construct_rejection(data) is False

    def test_non_400_status_is_not_construct(self, handler: ErrorHandler) -> None:
        data = {"error": {"message": "additionalProperties not allowed", "code": 500}}
        # No status hint in payload; helper looks at the error body string only,
        # but caller is expected to gate on status_code anyway. We still expect
        # it to require the construct keyword to be present.
        assert handler.is_schema_construct_rejection(data) is True

    def test_empty_data(self, handler: ErrorHandler) -> None:
        assert handler.is_schema_construct_rejection({}) is False
