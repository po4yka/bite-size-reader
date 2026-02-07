from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ._validators import _ensure_api_key, validate_model_name


class OpenRouterConfig(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    api_key: str = Field(..., validation_alias="OPENROUTER_API_KEY")
    model: str = Field(default="deepseek/deepseek-v3.2", validation_alias="OPENROUTER_MODEL")
    fallback_models: tuple[str, ...] = Field(
        default_factory=lambda: (
            "moonshotai/kimi-k2.5",
            "qwen/qwen3-max",
            "deepseek/deepseek-r1",
        ),
        validation_alias="OPENROUTER_FALLBACK_MODELS",
    )
    http_referer: str | None = Field(default=None, validation_alias="OPENROUTER_HTTP_REFERER")
    x_title: str | None = Field(default=None, validation_alias="OPENROUTER_X_TITLE")
    max_tokens: int | None = Field(default=None, validation_alias="OPENROUTER_MAX_TOKENS")
    top_p: float | None = Field(default=None, validation_alias="OPENROUTER_TOP_P")
    temperature: float = Field(default=0.2, validation_alias="OPENROUTER_TEMPERATURE")
    provider_order: tuple[str, ...] = Field(
        default_factory=tuple, validation_alias="OPENROUTER_PROVIDER_ORDER"
    )
    enable_stats: bool = Field(default=False, validation_alias="OPENROUTER_ENABLE_STATS")
    long_context_model: str | None = Field(
        default="moonshotai/kimi-k2.5", validation_alias="OPENROUTER_LONG_CONTEXT_MODEL"
    )
    flash_model: str = Field(
        default="google/gemini-3-flash", validation_alias="OPENROUTER_FLASH_MODEL"
    )
    flash_fallback_models: tuple[str, ...] = Field(
        default_factory=lambda: ("anthropic/claude-4.5-haiku",),
        validation_alias="OPENROUTER_FLASH_FALLBACK_MODELS",
    )
    summary_temperature_relaxed: float | None = Field(
        default=None, validation_alias="OPENROUTER_SUMMARY_TEMPERATURE_RELAXED"
    )
    summary_top_p_relaxed: float | None = Field(
        default=None, validation_alias="OPENROUTER_SUMMARY_TOP_P_RELAXED"
    )
    summary_temperature_json_fallback: float | None = Field(
        default=None, validation_alias="OPENROUTER_SUMMARY_TEMPERATURE_JSON"
    )
    summary_top_p_json_fallback: float | None = Field(
        default=None, validation_alias="OPENROUTER_SUMMARY_TOP_P_JSON"
    )
    enable_structured_outputs: bool = Field(
        default=True, validation_alias="OPENROUTER_ENABLE_STRUCTURED_OUTPUTS"
    )
    structured_output_mode: str = Field(
        default="json_schema", validation_alias="OPENROUTER_STRUCTURED_OUTPUT_MODE"
    )
    require_parameters: bool = Field(default=True, validation_alias="OPENROUTER_REQUIRE_PARAMETERS")
    auto_fallback_structured: bool = Field(
        default=True, validation_alias="OPENROUTER_AUTO_FALLBACK_STRUCTURED"
    )
    max_response_size_mb: int = Field(
        default=10, validation_alias="OPENROUTER_MAX_RESPONSE_SIZE_MB"
    )
    # Prompt caching settings (reduces inference costs)
    enable_prompt_caching: bool = Field(
        default=True,
        validation_alias="OPENROUTER_ENABLE_PROMPT_CACHING",
        description="Enable OpenRouter prompt caching for supported providers",
    )
    prompt_cache_ttl: str = Field(
        default="ephemeral",
        validation_alias="OPENROUTER_PROMPT_CACHE_TTL",
        description="Cache TTL: 'ephemeral' (5min) or '1h'",
    )
    cache_system_prompt: bool = Field(
        default=True,
        validation_alias="OPENROUTER_CACHE_SYSTEM_PROMPT",
        description="Cache the system message for reuse across requests",
    )
    cache_large_content_threshold: int = Field(
        default=4096,
        validation_alias="OPENROUTER_CACHE_LARGE_CONTENT_THRESHOLD",
        description="Minimum tokens to auto-cache content (Gemini requires 4096)",
    )

    @field_validator("api_key", mode="before")
    @classmethod
    def _validate_api_key(cls, value: Any) -> str:
        return _ensure_api_key(str(value or ""), name="OpenRouter")

    @field_validator("model", mode="before")
    @classmethod
    def _validate_model(cls, value: Any) -> str:
        return validate_model_name(str(value or ""))

    @field_validator("fallback_models", "flash_fallback_models", mode="before")
    @classmethod
    def _parse_fallback_models(cls, value: Any) -> tuple[str, ...]:
        if value in (None, ""):
            return ()
        iterable = value if isinstance(value, list | tuple) else str(value).split(",")

        validated: list[str] = []
        for raw in iterable:
            candidate = str(raw).strip()
            if not candidate:
                continue
            try:
                validated.append(validate_model_name(candidate))
            except ValueError:
                continue
        return tuple(validated)

    @field_validator("long_context_model", "flash_model", mode="before")
    @classmethod
    def _validate_long_context_model(cls, value: Any) -> str | None:
        if value in (None, ""):
            return None
        return validate_model_name(str(value))

    @field_validator("max_tokens", mode="before")
    @classmethod
    def _validate_max_tokens(cls, value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            tokens = int(str(value))
        except ValueError as exc:
            msg = "Max tokens must be a valid integer"
            raise ValueError(msg) from exc
        if tokens <= 0:
            msg = "Max tokens must be positive"
            raise ValueError(msg)
        if tokens > 100000:
            msg = "Max tokens too large"
            raise ValueError(msg)
        return tokens

    @field_validator("top_p", mode="before")
    @classmethod
    def _validate_top_p(cls, value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            top_p = float(str(value))
        except ValueError as exc:
            msg = "Top_p must be a valid number"
            raise ValueError(msg) from exc
        if top_p < 0 or top_p > 1:
            msg = "Top_p must be between 0 and 1"
            raise ValueError(msg)
        return top_p

    @field_validator("summary_top_p_relaxed", "summary_top_p_json_fallback", mode="before")
    @classmethod
    def _validate_summary_top_p(cls, value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            parsed = float(str(value))
        except ValueError as exc:
            msg = "Summary top_p override must be a valid number"
            raise ValueError(msg) from exc
        if parsed < 0 or parsed > 1:
            msg = "Summary top_p override must be between 0 and 1"
            raise ValueError(msg)
        return parsed

    @field_validator("temperature", mode="before")
    @classmethod
    def _validate_temperature(cls, value: Any) -> float:
        if value in (None, ""):
            return 0.2
        try:
            temperature = float(str(value))
        except ValueError as exc:
            msg = "Temperature must be a valid number"
            raise ValueError(msg) from exc
        if temperature < 0 or temperature > 2:
            msg = "Temperature must be between 0 and 2"
            raise ValueError(msg)
        return temperature

    @field_validator(
        "summary_temperature_relaxed",
        "summary_temperature_json_fallback",
        mode="before",
    )
    @classmethod
    def _validate_summary_temperatures(cls, value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            parsed = float(str(value))
        except ValueError as exc:
            msg = "Summary temperature override must be a valid number"
            raise ValueError(msg) from exc
        if parsed < 0 or parsed > 2:
            msg = "Summary temperature override must be between 0 and 2"
            raise ValueError(msg)
        return parsed

    @field_validator("structured_output_mode", mode="before")
    @classmethod
    def _validate_structured_output_mode(cls, value: Any) -> str:
        if value in (None, ""):
            return "json_schema"
        mode_value = str(value)
        if mode_value not in {"json_schema", "json_object"}:
            msg = f"Invalid structured output mode: {mode_value}. Must be one of {{'json_schema', 'json_object'}}"
            raise ValueError(msg)
        return mode_value

    @field_validator("provider_order", mode="before")
    @classmethod
    def _parse_provider_order(cls, value: Any) -> tuple[str, ...]:
        if value in (None, ""):
            return ()
        iterable = value if isinstance(value, list | tuple) else str(value).split(",")

        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-:")
        parsed: list[str] = []
        for raw in iterable:
            slug = str(raw).strip()
            if not slug or len(slug) > 100:
                continue
            if any(ch not in allowed for ch in slug):
                continue
            parsed.append(slug)
        return tuple(parsed)

    @field_validator("max_response_size_mb", mode="before")
    @classmethod
    def _validate_max_response_size_mb(cls, value: Any) -> int:
        if value in (None, ""):
            return 10
        try:
            size_mb = int(str(value))
        except ValueError as exc:
            msg = "Max response size must be a valid integer"
            raise ValueError(msg) from exc
        if size_mb < 1 or size_mb > 100:
            msg = "Max response size must be between 1 and 100 MB"
            raise ValueError(msg)
        return size_mb

    @field_validator("prompt_cache_ttl", mode="before")
    @classmethod
    def _validate_prompt_cache_ttl(cls, value: Any) -> str:
        if value in (None, ""):
            return "ephemeral"
        ttl = str(value).strip().lower()
        if ttl not in {"ephemeral", "1h"}:
            msg = f"Invalid prompt cache TTL: {ttl}. Must be 'ephemeral' or '1h'"
            raise ValueError(msg)
        return ttl

    @field_validator("cache_large_content_threshold", mode="before")
    @classmethod
    def _validate_cache_large_content_threshold(cls, value: Any) -> int:
        if value in (None, ""):
            return 4096
        try:
            threshold = int(str(value))
        except ValueError as exc:
            msg = "Cache large content threshold must be a valid integer"
            raise ValueError(msg) from exc
        if threshold < 0 or threshold > 100000:
            msg = "Cache large content threshold must be between 0 and 100000"
            raise ValueError(msg)
        return threshold


class OpenAIConfig(BaseModel):
    """OpenAI API configuration for direct API access."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    model: str = Field(default="gpt-4o", validation_alias="OPENAI_MODEL")
    fallback_models: tuple[str, ...] = Field(
        default_factory=lambda: ("gpt-4o-mini",),
        validation_alias="OPENAI_FALLBACK_MODELS",
    )
    organization: str | None = Field(default=None, validation_alias="OPENAI_ORGANIZATION")
    enable_structured_outputs: bool = Field(
        default=True, validation_alias="OPENAI_ENABLE_STRUCTURED_OUTPUTS"
    )

    @field_validator("api_key", mode="before")
    @classmethod
    def _validate_api_key(cls, value: Any) -> str:
        if value in (None, ""):
            return ""
        return _ensure_api_key(str(value), name="OpenAI")

    @field_validator("model", mode="before")
    @classmethod
    def _validate_model(cls, value: Any) -> str:
        if value in (None, ""):
            return "gpt-4o"
        return validate_model_name(str(value))

    @field_validator("fallback_models", mode="before")
    @classmethod
    def _parse_fallback_models(cls, value: Any) -> tuple[str, ...]:
        if value in (None, ""):
            return ()
        iterable = value if isinstance(value, list | tuple) else str(value).split(",")

        validated: list[str] = []
        for raw in iterable:
            candidate = str(raw).strip()
            if not candidate:
                continue
            try:
                validated.append(validate_model_name(candidate))
            except ValueError:
                continue
        return tuple(validated)

    @field_validator("organization", mode="before")
    @classmethod
    def _validate_organization(cls, value: Any) -> str | None:
        if value in (None, ""):
            return None
        org = str(value).strip()
        if len(org) > 100:
            msg = "OpenAI organization ID appears too long"
            raise ValueError(msg)
        return org


class AnthropicConfig(BaseModel):
    """Anthropic API configuration for direct API access."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    model: str = Field(default="claude-sonnet-4-5-20250929", validation_alias="ANTHROPIC_MODEL")
    fallback_models: tuple[str, ...] = Field(
        default_factory=lambda: ("claude-3-5-haiku-20241022",),
        validation_alias="ANTHROPIC_FALLBACK_MODELS",
    )
    enable_structured_outputs: bool = Field(
        default=True, validation_alias="ANTHROPIC_ENABLE_STRUCTURED_OUTPUTS"
    )

    @field_validator("api_key", mode="before")
    @classmethod
    def _validate_api_key(cls, value: Any) -> str:
        if value in (None, ""):
            return ""
        return _ensure_api_key(str(value), name="Anthropic")

    @field_validator("model", mode="before")
    @classmethod
    def _validate_model(cls, value: Any) -> str:
        if value in (None, ""):
            return "claude-sonnet-4-5-20250929"
        return validate_model_name(str(value))

    @field_validator("fallback_models", mode="before")
    @classmethod
    def _parse_fallback_models(cls, value: Any) -> tuple[str, ...]:
        if value in (None, ""):
            return ()
        iterable = value if isinstance(value, list | tuple) else str(value).split(",")

        validated: list[str] = []
        for raw in iterable:
            candidate = str(raw).strip()
            if not candidate:
                continue
            try:
                validated.append(validate_model_name(candidate))
            except ValueError:
                continue
        return tuple(validated)
