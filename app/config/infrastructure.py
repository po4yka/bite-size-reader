from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationInfo, field_validator


class DatabaseConfig(BaseModel):
    """Database operation limits and timeouts configuration."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    operation_timeout: float = Field(
        default=30.0,
        validation_alias="DB_OPERATION_TIMEOUT",
        description="Database operation timeout in seconds",
    )
    max_retries: int = Field(
        default=3,
        validation_alias="DB_MAX_RETRIES",
        description="Maximum retries for transient database errors",
    )
    json_max_size: int = Field(
        default=10_000_000,
        validation_alias="DB_JSON_MAX_SIZE",
        description="Maximum JSON payload size in bytes (10MB)",
    )
    json_max_depth: int = Field(
        default=20,
        validation_alias="DB_JSON_MAX_DEPTH",
        description="Maximum JSON nesting depth",
    )
    json_max_array_length: int = Field(
        default=10_000,
        validation_alias="DB_JSON_MAX_ARRAY_LENGTH",
        description="Maximum JSON array length",
    )
    json_max_dict_keys: int = Field(
        default=1_000,
        validation_alias="DB_JSON_MAX_DICT_KEYS",
        description="Maximum JSON dictionary keys",
    )

    @field_validator("operation_timeout", mode="before")
    @classmethod
    def _validate_timeout(cls, value: Any) -> float:
        if value in (None, ""):
            return 30.0
        try:
            parsed = float(str(value))
        except ValueError as exc:
            msg = "Database operation timeout must be a valid number"
            raise ValueError(msg) from exc
        if parsed <= 0:
            msg = "Database operation timeout must be positive"
            raise ValueError(msg)
        if parsed > 3600:
            msg = "Database operation timeout must be 3600 seconds or less"
            raise ValueError(msg)
        return parsed

    @field_validator(
        "max_retries",
        "json_max_size",
        "json_max_depth",
        "json_max_array_length",
        "json_max_dict_keys",
        mode="before",
    )
    @classmethod
    def _validate_positive_int(cls, value: Any, info: ValidationInfo) -> int:
        if value in (None, ""):
            default = cls.model_fields[info.field_name].default
            return int(default)
        try:
            parsed = int(str(value))
        except ValueError as exc:
            msg = f"{info.field_name.replace('_', ' ')} must be a valid integer"
            raise ValueError(msg) from exc
        if parsed <= 0:
            msg = f"{info.field_name.replace('_', ' ').capitalize()} must be positive"
            raise ValueError(msg)
        return parsed


class RedisConfig(BaseModel):
    """Shared Redis connection settings."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    enabled: bool = Field(default=True, validation_alias="REDIS_ENABLED")
    cache_enabled: bool = Field(default=True, validation_alias="REDIS_CACHE_ENABLED")
    required: bool = Field(
        default=False,
        validation_alias="REDIS_REQUIRED",
        description="If true, fail requests when Redis is unavailable.",
    )
    url: str | None = Field(default=None, validation_alias="REDIS_URL")
    host: str = Field(default="127.0.0.1", validation_alias="REDIS_HOST")
    port: int = Field(default=6379, validation_alias="REDIS_PORT")
    db: int = Field(default=0, validation_alias="REDIS_DB")
    password: str | None = Field(default=None, validation_alias="REDIS_PASSWORD")
    prefix: str = Field(default="bsr", validation_alias="REDIS_PREFIX")
    socket_timeout: float = Field(default=5.0, validation_alias="REDIS_SOCKET_TIMEOUT")
    cache_timeout_sec: float = Field(default=0.3, validation_alias="REDIS_CACHE_TIMEOUT_SEC")
    firecrawl_ttl_seconds: int = Field(
        default=21_600, validation_alias="REDIS_FIRECRAWL_TTL_SECONDS"
    )
    llm_ttl_seconds: int = Field(default=7_200, validation_alias="REDIS_LLM_TTL_SECONDS")

    @field_validator("url", mode="before")
    @classmethod
    def _normalize_url(cls, value: Any) -> str | None:
        if value in (None, ""):
            return None
        cleaned = str(value).strip()
        if cleaned and len(cleaned) > 200:
            msg = "Redis URL appears too long"
            raise ValueError(msg)
        return cleaned

    @field_validator("host", mode="before")
    @classmethod
    def _validate_host(cls, value: Any) -> str:
        host = str(value or "").strip()
        if not host:
            msg = "Redis host is required when URL is not provided"
            raise ValueError(msg)
        if len(host) > 200:
            msg = "Redis host appears too long"
            raise ValueError(msg)
        return host

    @field_validator("port", "db", mode="before")
    @classmethod
    def _validate_int_bounds(cls, value: Any, info: ValidationInfo) -> int:
        default = cls.model_fields[info.field_name].default
        try:
            parsed = int(str(value if value not in (None, "") else default))
        except ValueError as exc:  # pragma: no cover - defensive
            msg = f"{info.field_name.replace('_', ' ')} must be a valid integer"
            raise ValueError(msg) from exc
        limits: dict[str, tuple[int, int]] = {
            "port": (0, 65535),
            "db": (0, 65535),
            "firecrawl_ttl_seconds": (60, 86_400 * 14),
            "llm_ttl_seconds": (60, 86_400 * 14),
        }
        min_val, max_val = limits.get(info.field_name, (0, 65535))
        if parsed < min_val or parsed > max_val:
            msg = (
                f"{info.field_name.replace('_', ' ').capitalize()} must be between "
                f"{min_val} and {max_val}"
            )
            raise ValueError(msg)
        return parsed

    @field_validator("socket_timeout", mode="before")
    @classmethod
    def _validate_timeout(cls, value: Any) -> float:
        default = cls.model_fields["socket_timeout"].default
        try:
            parsed = float(str(value if value not in (None, "") else default))
        except ValueError as exc:  # pragma: no cover - defensive
            msg = "Redis socket timeout must be a valid number"
            raise ValueError(msg) from exc
        if parsed <= 0 or parsed > 60:
            msg = "Redis socket timeout must be between 0 and 60 seconds"
            raise ValueError(msg)
        return parsed

    @field_validator("cache_timeout_sec", mode="before")
    @classmethod
    def _validate_cache_timeout(cls, value: Any) -> float:
        default = cls.model_fields["cache_timeout_sec"].default
        try:
            parsed = float(str(value if value not in (None, "") else default))
        except ValueError as exc:  # pragma: no cover - defensive
            msg = "Redis cache timeout must be a valid number"
            raise ValueError(msg) from exc
        if parsed <= 0 or parsed > 5:
            msg = "Redis cache timeout must be between 0 and 5 seconds"
            raise ValueError(msg)
        return parsed

    @field_validator("prefix", mode="before")
    @classmethod
    def _validate_prefix(cls, value: Any) -> str:
        prefix = str(value or "bsr").strip()
        if not prefix:
            msg = "Redis prefix cannot be empty"
            raise ValueError(msg)
        if len(prefix) > 50:
            msg = "Redis prefix appears too long"
            raise ValueError(msg)
        if any(ch in prefix for ch in (" ", "\t", "\n", "\r")):
            msg = "Redis prefix cannot contain whitespace"
            raise ValueError(msg)
        return prefix


class CircuitBreakerConfig(BaseModel):
    """Circuit breaker configuration for external services."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    enabled: bool = Field(
        default=True,
        validation_alias="CIRCUIT_BREAKER_ENABLED",
        description="Enable circuit breaker for external service calls",
    )
    failure_threshold: int = Field(
        default=5,
        validation_alias="CIRCUIT_BREAKER_FAILURE_THRESHOLD",
        description="Number of failures before opening circuit",
    )
    timeout_seconds: float = Field(
        default=60.0,
        validation_alias="CIRCUIT_BREAKER_TIMEOUT_SECONDS",
        description="Seconds to wait before entering half-open state",
    )
    success_threshold: int = Field(
        default=2,
        validation_alias="CIRCUIT_BREAKER_SUCCESS_THRESHOLD",
        description="Successful attempts needed in half-open to close",
    )

    @field_validator("failure_threshold", "success_threshold", mode="before")
    @classmethod
    def _validate_threshold(cls, value: Any, info: ValidationInfo) -> int:
        default = cls.model_fields[info.field_name].default
        try:
            parsed = int(str(value if value not in (None, "") else default))
        except ValueError as exc:
            msg = f"{info.field_name.replace('_', ' ')} must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 1 or parsed > 100:
            msg = f"{info.field_name.replace('_', ' ').capitalize()} must be between 1 and 100"
            raise ValueError(msg)
        return parsed

    @field_validator("timeout_seconds", mode="before")
    @classmethod
    def _validate_timeout(cls, value: Any) -> float:
        try:
            parsed = float(str(value if value not in (None, "") else 60.0))
        except ValueError as exc:
            msg = "Circuit breaker timeout must be a valid number"
            raise ValueError(msg) from exc
        if parsed < 1.0 or parsed > 600.0:
            msg = "Circuit breaker timeout must be between 1 and 600 seconds"
            raise ValueError(msg)
        return parsed


class McpConfig(BaseModel):
    """MCP (Model Context Protocol) server configuration.

    Controls the MCP server that exposes articles and search
    to external AI agents like OpenClaw.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    enabled: bool = Field(
        default=False,
        validation_alias="MCP_ENABLED",
        description="Enable the MCP server for external agent access",
    )
    transport: str = Field(
        default="stdio",
        validation_alias="MCP_TRANSPORT",
        description="Transport protocol: 'stdio' or 'sse'",
    )
    host: str = Field(
        default="0.0.0.0",
        validation_alias="MCP_HOST",
        description="Bind address for SSE transport",
    )
    port: int = Field(
        default=8200,
        validation_alias="MCP_PORT",
        description="Port for SSE transport",
    )

    @field_validator("transport", mode="before")
    @classmethod
    def _validate_transport(cls, value: Any) -> str:
        if value in (None, ""):
            return "stdio"
        value = str(value).strip().lower()
        if value not in ("stdio", "sse"):
            msg = "MCP transport must be 'stdio' or 'sse'"
            raise ValueError(msg)
        return value

    @field_validator("port", mode="before")
    @classmethod
    def _validate_port(cls, value: Any) -> int:
        if value in (None, ""):
            return 8200
        try:
            parsed = int(str(value))
        except ValueError as exc:
            msg = "MCP port must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 1 or parsed > 65535:
            msg = "MCP port must be between 1 and 65535"
            raise ValueError(msg)
        return parsed


class ChromaConfig(BaseModel):
    """Vector store configuration for Chroma."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    host: str = Field(
        default="http://localhost:8000",
        validation_alias="CHROMA_HOST",
        description="Chroma HTTP endpoint (scheme + host)",
    )
    auth_token: str | None = Field(
        default=None,
        validation_alias="CHROMA_AUTH_TOKEN",
        description="Optional bearer token for secured Chroma deployments",
    )
    environment: str = Field(
        default="dev",
        validation_alias=AliasChoices("CHROMA_ENV", "APP_ENV", "ENVIRONMENT"),
        description="Environment label used for namespacing collections",
    )
    user_scope: str = Field(
        default="public",
        validation_alias="CHROMA_USER_SCOPE",
        description="User or tenant scope used for namespacing collections",
    )
    collection_version: str = Field(
        default="v1",
        validation_alias="CHROMA_COLLECTION_VERSION",
        description="Collection version suffix to prevent bleed-over between schema changes",
    )
    required: bool = Field(
        default=False,
        validation_alias="CHROMA_REQUIRED",
        description="If true, fail startup when ChromaDB is unavailable. Default false for graceful degradation.",
    )
    connection_timeout: float = Field(
        default=10.0,
        validation_alias="CHROMA_CONNECTION_TIMEOUT",
        description="Connection timeout in seconds for ChromaDB HTTP client",
    )

    @field_validator("host", mode="before")
    @classmethod
    def _validate_host(cls, value: Any) -> str:
        host = str(value or "").strip()
        if not host:
            msg = "Chroma host is required"
            raise ValueError(msg)
        if len(host) > 200:
            msg = "Chroma host value appears to be too long"
            raise ValueError(msg)
        if "\x00" in host:
            msg = "Chroma host contains invalid characters"
            raise ValueError(msg)
        return host

    @field_validator("auth_token", mode="before")
    @classmethod
    def _validate_auth_token(cls, value: Any) -> str | None:
        if value in (None, ""):
            return None
        token = str(value).strip()
        if len(token) > 500:
            msg = "Chroma auth token appears to be too long"
            raise ValueError(msg)
        return token

    @field_validator("environment", "user_scope", mode="before")
    @classmethod
    def _sanitize_names(cls, value: Any, info: ValidationInfo) -> str:
        raw = str(value or "").strip() or cls.model_fields[info.field_name].default
        cleaned = "".join(ch for ch in raw if ch.isalnum() or ch in {"-", "_"})
        if not cleaned:
            msg = f"{info.field_name.replace('_', ' ').capitalize()} cannot be empty"
            raise ValueError(msg)
        return cleaned.lower()

    @field_validator("collection_version", mode="before")
    @classmethod
    def _sanitize_version(cls, value: Any) -> str:
        raw = str(value or "").strip() or "v1"
        cleaned = "".join(ch for ch in raw if ch.isalnum() or ch in {"-", "_"})
        if not cleaned:
            msg = "Collection version cannot be empty"
            raise ValueError(msg)
        return cleaned.lower()
