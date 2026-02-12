from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationInfo, field_validator


class KarakeepConfig(BaseModel):
    """Karakeep integration configuration for bookmark synchronization."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    enabled: bool = Field(default=False, validation_alias="KARAKEEP_ENABLED")
    api_url: str = Field(
        default="http://localhost:3000/api/v1",
        validation_alias="KARAKEEP_API_URL",
    )
    api_key: str = Field(default="", validation_alias="KARAKEEP_API_KEY")
    sync_tag: str = Field(default="bsr-synced", validation_alias="KARAKEEP_SYNC_TAG")
    sync_interval_hours: int = Field(default=6, validation_alias="KARAKEEP_SYNC_INTERVAL_HOURS")
    auto_sync_enabled: bool = Field(default=True, validation_alias="KARAKEEP_AUTO_SYNC_ENABLED")

    @field_validator("api_url", mode="before")
    @classmethod
    def _validate_api_url(cls, value: Any) -> str:
        url = str(value or "http://localhost:3000/api/v1").strip()
        if not url:
            return "http://localhost:3000/api/v1"
        return url.rstrip("/")

    @field_validator("api_key", mode="before")
    @classmethod
    def _validate_api_key(cls, value: Any) -> str:
        if value in (None, ""):
            return ""
        key = str(value).strip()
        if len(key) > 500:
            msg = "Karakeep API key appears to be too long"
            raise ValueError(msg)
        return key

    @field_validator("sync_tag", mode="before")
    @classmethod
    def _validate_sync_tag(cls, value: Any) -> str:
        tag = str(value or "bsr-synced").strip()
        if not tag:
            return "bsr-synced"
        if len(tag) > 50:
            msg = "Karakeep sync tag is too long"
            raise ValueError(msg)
        return tag

    @field_validator("sync_interval_hours", mode="before")
    @classmethod
    def _validate_sync_interval(cls, value: Any) -> int:
        try:
            parsed = int(str(value if value not in (None, "") else 6))
        except ValueError as exc:
            msg = "Karakeep sync interval must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 1 or parsed > 168:
            msg = "Karakeep sync interval must be between 1 and 168 hours"
            raise ValueError(msg)
        return parsed


class WebSearchConfig(BaseModel):
    """Web search enrichment configuration for LLM summarization."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    enabled: bool = Field(
        default=False,
        validation_alias="WEB_SEARCH_ENABLED",
        description="Enable web search enrichment for summaries (opt-in)",
    )
    max_queries: int = Field(
        default=3,
        validation_alias="WEB_SEARCH_MAX_QUERIES",
        description="Maximum search queries per article",
    )
    min_content_length: int = Field(
        default=500,
        validation_alias="WEB_SEARCH_MIN_CONTENT_LENGTH",
        description="Minimum content length (chars) to trigger search",
    )
    timeout_sec: float = Field(
        default=10.0,
        validation_alias="WEB_SEARCH_TIMEOUT_SEC",
        description="Timeout for search operations in seconds",
    )
    max_context_chars: int = Field(
        default=2000,
        validation_alias="WEB_SEARCH_MAX_CONTEXT_CHARS",
        description="Maximum characters for injected search context",
    )
    cache_ttl_sec: int = Field(
        default=3600,
        validation_alias="WEB_SEARCH_CACHE_TTL_SEC",
        description="Cache TTL for search results in seconds",
    )

    @field_validator("max_queries", mode="before")
    @classmethod
    def _validate_max_queries(cls, value: Any) -> int:
        if value in (None, ""):
            return 3
        try:
            parsed = int(str(value))
        except ValueError as exc:
            msg = "Max queries must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 1 or parsed > 10:
            msg = "Max queries must be between 1 and 10"
            raise ValueError(msg)
        return parsed

    @field_validator("min_content_length", mode="before")
    @classmethod
    def _validate_min_content_length(cls, value: Any) -> int:
        if value in (None, ""):
            return 500
        try:
            parsed = int(str(value))
        except ValueError as exc:
            msg = "Min content length must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 0 or parsed > 10000:
            msg = "Min content length must be between 0 and 10000"
            raise ValueError(msg)
        return parsed

    @field_validator("timeout_sec", mode="before")
    @classmethod
    def _validate_timeout_sec(cls, value: Any) -> float:
        if value in (None, ""):
            return 10.0
        try:
            parsed = float(str(value))
        except ValueError as exc:
            msg = "Timeout must be a valid number"
            raise ValueError(msg) from exc
        if parsed < 1.0 or parsed > 60.0:
            msg = "Timeout must be between 1 and 60 seconds"
            raise ValueError(msg)
        return parsed

    @field_validator("max_context_chars", mode="before")
    @classmethod
    def _validate_max_context_chars(cls, value: Any) -> int:
        if value in (None, ""):
            return 2000
        try:
            parsed = int(str(value))
        except ValueError as exc:
            msg = "Max context chars must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 500 or parsed > 10000:
            msg = "Max context chars must be between 500 and 10000"
            raise ValueError(msg)
        return parsed

    @field_validator("cache_ttl_sec", mode="before")
    @classmethod
    def _validate_cache_ttl_sec(cls, value: Any) -> int:
        if value in (None, ""):
            return 3600
        try:
            parsed = int(str(value))
        except ValueError as exc:
            msg = "Cache TTL must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 60 or parsed > 86400:
            msg = "Cache TTL must be between 60 and 86400 seconds"
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
        default="127.0.0.1",
        validation_alias="MCP_HOST",
        description="Bind address for SSE transport",
    )
    port: int = Field(
        default=8200,
        validation_alias="MCP_PORT",
        description="Port for SSE transport",
    )
    user_id: int | None = Field(
        default=None,
        validation_alias="MCP_USER_ID",
        description="Optional user ID scope for MCP queries",
    )
    allow_remote_sse: bool = Field(
        default=False,
        validation_alias="MCP_ALLOW_REMOTE_SSE",
        description="Allow SSE transport to bind non-loopback hosts",
    )
    allow_unscoped_sse: bool = Field(
        default=False,
        validation_alias="MCP_ALLOW_UNSCOPED_SSE",
        description="Allow SSE transport without MCP_USER_ID scoping",
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

    @field_validator("user_id", mode="before")
    @classmethod
    def _validate_user_id(cls, value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            parsed = int(str(value))
        except ValueError as exc:
            msg = "MCP user ID must be a valid integer"
            raise ValueError(msg) from exc
        if parsed <= 0:
            msg = "MCP user ID must be a positive integer"
            raise ValueError(msg)
        return parsed


class BatchAnalysisConfig(BaseModel):
    """Batch article relationship detection and combined summary configuration."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    enabled: bool = Field(
        default=True,
        validation_alias="BATCH_ANALYSIS_ENABLED",
        description="Enable batch relationship analysis for multi-URL submissions",
    )
    min_articles: int = Field(
        default=2,
        validation_alias="BATCH_ANALYSIS_MIN_ARTICLES",
        description="Minimum successful articles required to trigger analysis",
    )
    series_threshold: float = Field(
        default=0.9,
        validation_alias="BATCH_ANALYSIS_SERIES_THRESHOLD",
        description="Confidence threshold for series detection (0.0-1.0)",
    )
    cluster_threshold: float = Field(
        default=0.75,
        validation_alias="BATCH_ANALYSIS_CLUSTER_THRESHOLD",
        description="Confidence threshold for topic cluster detection (0.0-1.0)",
    )
    combined_summary_enabled: bool = Field(
        default=True,
        validation_alias="BATCH_COMBINED_SUMMARY_ENABLED",
        description="Generate combined summary when relationship is detected",
    )
    use_llm_for_analysis: bool = Field(
        default=True,
        validation_alias="BATCH_ANALYSIS_USE_LLM",
        description="Use LLM for ambiguous relationship analysis",
    )

    @field_validator("min_articles", mode="before")
    @classmethod
    def _validate_min_articles(cls, value: Any) -> int:
        if value in (None, ""):
            return 2
        try:
            parsed = int(str(value))
        except ValueError as exc:
            msg = "Min articles must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 2 or parsed > 100:
            msg = "Min articles must be between 2 and 100"
            raise ValueError(msg)
        return parsed

    @field_validator("series_threshold", "cluster_threshold", mode="before")
    @classmethod
    def _validate_threshold(cls, value: Any, info: ValidationInfo) -> float:
        default = 0.9 if "series" in info.field_name else 0.75
        if value in (None, ""):
            return default
        try:
            parsed = float(str(value))
        except ValueError as exc:
            msg = f"{info.field_name} must be a valid number"
            raise ValueError(msg) from exc
        if parsed < 0.0 or parsed > 1.0:
            msg = f"{info.field_name} must be between 0.0 and 1.0"
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
