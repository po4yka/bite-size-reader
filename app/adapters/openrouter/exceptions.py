"""Custom exceptions for OpenRouter client."""

from __future__ import annotations


class OpenRouterError(Exception):
    """Base exception for OpenRouter client errors."""

    def __init__(
        self,
        message: str,
        *,
        model: str | None = None,
        attempt: int | None = None,
        request_id: int | None = None,
        context: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.model = model
        self.attempt = attempt
        self.request_id = request_id
        self.context = context or {}


class ConfigurationError(OpenRouterError):
    """Raised when there's an issue with client configuration."""

    def __init__(
        self,
        message: str,
        *,
        model: str | None = None,
        attempt: int | None = None,
        request_id: int | None = None,
        context: dict | None = None,
    ) -> None:
        super().__init__(
            message, model=model, attempt=attempt, request_id=request_id, context=context
        )
        self.context["error_type"] = "configuration"


class ValidationError(OpenRouterError):
    """Raised when request validation fails."""

    def __init__(
        self,
        message: str,
        *,
        model: str | None = None,
        attempt: int | None = None,
        request_id: int | None = None,
        context: dict | None = None,
    ) -> None:
        super().__init__(
            message, model=model, attempt=attempt, request_id=request_id, context=context
        )
        self.context["error_type"] = "validation"


class APIError(OpenRouterError):
    """Raised when the OpenRouter API returns an error."""

    def __init__(
        self,
        message: str,
        *,
        model: str | None = None,
        attempt: int | None = None,
        request_id: int | None = None,
        status_code: int | None = None,
        context: dict | None = None,
    ) -> None:
        super().__init__(
            message, model=model, attempt=attempt, request_id=request_id, context=context
        )
        self.status_code = status_code
        if status_code:
            self.context["status_code"] = status_code
        self.context["error_type"] = "api"


class RateLimitError(APIError):
    """Raised when rate limits are exceeded."""

    def __init__(
        self,
        message: str,
        *,
        model: str | None = None,
        attempt: int | None = None,
        request_id: int | None = None,
        status_code: int | None = None,
        retry_after: int | None = None,
        context: dict | None = None,
    ) -> None:
        super().__init__(
            message,
            model=model,
            attempt=attempt,
            request_id=request_id,
            status_code=status_code,
            context=context,
        )
        self.retry_after = retry_after
        if retry_after:
            self.context["retry_after"] = retry_after
        self.context["error_type"] = "rate_limit"


class NetworkError(OpenRouterError):
    """Raised when network-related errors occur."""

    def __init__(
        self,
        message: str,
        *,
        model: str | None = None,
        attempt: int | None = None,
        request_id: int | None = None,
        context: dict | None = None,
    ) -> None:
        super().__init__(
            message, model=model, attempt=attempt, request_id=request_id, context=context
        )
        self.context["error_type"] = "network"


class ModelError(OpenRouterError):
    """Raised when there are issues with model selection or capabilities."""

    def __init__(
        self,
        message: str,
        *,
        model: str | None = None,
        attempt: int | None = None,
        request_id: int | None = None,
        context: dict | None = None,
    ) -> None:
        super().__init__(
            message, model=model, attempt=attempt, request_id=request_id, context=context
        )
        self.context["error_type"] = "model"


class StructuredOutputError(OpenRouterError):
    """Raised when structured output processing fails."""

    def __init__(
        self,
        message: str,
        *,
        model: str | None = None,
        attempt: int | None = None,
        request_id: int | None = None,
        context: dict | None = None,
    ) -> None:
        super().__init__(
            message, model=model, attempt=attempt, request_id=request_id, context=context
        )
        self.context["error_type"] = "structured_output"


class ClientError(OpenRouterError):
    """Raised when there are issues with the HTTP client."""

    def __init__(
        self,
        message: str,
        *,
        model: str | None = None,
        attempt: int | None = None,
        request_id: int | None = None,
        context: dict | None = None,
    ) -> None:
        super().__init__(
            message, model=model, attempt=attempt, request_id=request_id, context=context
        )
        self.context["error_type"] = "client"
