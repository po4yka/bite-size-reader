from __future__ import annotations

from typing import Any

from app.adapters.openrouter.exceptions import ConfigurationError


def get_error_message(status_code: int, data: dict[str, Any] | None) -> str:
    """Return a human-friendly error message for an HTTP status.

    This mirrors the expectations asserted in tests by mapping common
    statuses to stable, descriptive messages and appending any message
    provided by the API payload when present.
    """
    # Extract optional message from payload (string or nested {error: {message}})
    payload_message: str | None = None
    if data:
        try:
            err = data.get("error")
            if isinstance(err, dict):
                msg = err.get("message")
                if isinstance(msg, str) and msg:
                    payload_message = msg
            elif isinstance(err, str) and err:
                payload_message = err
        except (AttributeError, TypeError):
            # Handle malformed data gracefully
            pass

    base_map: dict[int, str] = {
        400: "Invalid or missing request parameters",
        401: "Authentication failed",
        402: "Insufficient account balance",
        404: "Requested resource not found",
        429: "Rate limit exceeded",
    }

    if status_code == 500:
        base = "Internal server error"
    elif status_code >= 500:
        base = f"HTTP {status_code} error"
    else:
        base = base_map.get(status_code, f"HTTP {status_code} error")

    if payload_message:
        return f"{base}: {payload_message}"
    return base


def validate_init_params(
    *,
    api_key: str,
    model: str,
    fallback_models: list[str] | tuple[str, ...] | None,
    http_referer: str | None,
    x_title: str | None,
    timeout_sec: int,
    max_retries: int,
    backoff_base: float,
    structured_output_mode: str,
    max_response_size_mb: int,
) -> None:
    """Validate initialization parameters with specific error types."""
    _ = fallback_models  # kept for signature compatibility / future use

    # Security: Validate API key presence
    if not api_key or not isinstance(api_key, str):
        msg = "API key is required and must be a non-empty string"
        raise ConfigurationError(
            msg,
            context={"parameter": "api_key", "type": type(api_key).__name__},
        )
    if len(api_key.strip()) < 10:  # Basic sanity check
        msg = "API key appears to be invalid (too short)"
        raise ConfigurationError(
            msg,
            context={"parameter": "api_key", "length": len(api_key.strip())},
        )

    # Security: Validate model
    if not model or not isinstance(model, str):
        msg = "Model is required and must be a non-empty string"
        raise ConfigurationError(
            msg,
            context={"parameter": "model", "type": type(model).__name__},
        )
    if len(model) > 100:
        msg = f"Model name too long (max 100 characters, got {len(model)})"
        raise ConfigurationError(
            msg,
            context={"parameter": "model", "length": len(model)},
        )

    # Security: Validate headers
    if http_referer and (not isinstance(http_referer, str) or len(http_referer) > 500):
        msg = f"HTTP referer must be a string with max 500 characters (got {len(http_referer)})"
        raise ConfigurationError(
            msg,
            context={
                "parameter": "http_referer",
                "length": len(http_referer) if http_referer else 0,
            },
        )
    if x_title and (not isinstance(x_title, str) or len(x_title) > 200):
        msg = f"X-Title must be a string with max 200 characters (got {len(x_title)})"
        raise ConfigurationError(
            msg,
            context={"parameter": "x_title", "length": len(x_title) if x_title else 0},
        )

    # Security: Validate timeout
    if not isinstance(timeout_sec, int | float) or timeout_sec <= 0:
        msg = f"Timeout must be a positive number (got {timeout_sec})"
        raise ConfigurationError(
            msg,
            context={
                "parameter": "timeout_sec",
                "value": timeout_sec,
                "type": type(timeout_sec).__name__,
            },
        )
    if timeout_sec > 300:  # 5 minutes max
        msg = f"Timeout too large (max 300 seconds, got {timeout_sec})"
        raise ConfigurationError(
            msg,
            context={"parameter": "timeout_sec", "value": timeout_sec},
        )

    # Security: Validate retry parameters
    if not isinstance(max_retries, int) or max_retries < 0 or max_retries > 10:
        msg = f"Max retries must be an integer between 0 and 10 (got {max_retries})"
        raise ConfigurationError(
            msg,
            context={
                "parameter": "max_retries",
                "value": max_retries,
                "type": type(max_retries).__name__,
            },
        )
    if not isinstance(backoff_base, int | float) or backoff_base < 0:
        msg = f"Backoff base must be a non-negative number (got {backoff_base})"
        raise ConfigurationError(
            msg,
            context={
                "parameter": "backoff_base",
                "value": backoff_base,
                "type": type(backoff_base).__name__,
            },
        )

    # Validate structured output settings
    if structured_output_mode not in {"json_schema", "json_object"}:
        msg = (
            "Structured output mode must be 'json_schema' or 'json_object' "
            f"(got '{structured_output_mode}')"
        )
        raise ConfigurationError(
            msg,
            context={"parameter": "structured_output_mode", "value": structured_output_mode},
        )

    # Validate max_response_size_mb
    if (
        not isinstance(max_response_size_mb, int)
        or max_response_size_mb < 1
        or max_response_size_mb > 100
    ):
        msg = f"Max response size must be between 1 and 100 MB (got {max_response_size_mb})"
        raise ConfigurationError(
            msg,
            context={"parameter": "max_response_size_mb", "value": max_response_size_mb},
        )


def validate_fallback_models(fallback_models: list[str] | tuple[str, ...] | None) -> list[str]:
    """Validate and return fallback models."""
    validated_fallbacks: list[str] = []
    if fallback_models:
        for fallback in fallback_models:
            if isinstance(fallback, str) and fallback.strip() and len(fallback) <= 100:
                validated_fallbacks.append(fallback.strip())
    return validated_fallbacks
