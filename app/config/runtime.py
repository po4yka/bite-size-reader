from __future__ import annotations

import logging
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from app.config.validation_helpers import parse_positive_int

logger = logging.getLogger(__name__)


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    db_path: str = Field(default="/data/app.db", validation_alias="DB_PATH")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    request_timeout_sec: int = Field(default=60, validation_alias="REQUEST_TIMEOUT_SEC")
    preferred_lang: str = Field(default="auto", validation_alias="PREFERRED_LANG")
    debug_payloads: bool = Field(default=False, validation_alias="DEBUG_PAYLOADS")
    enable_textacy: bool = Field(default=False, validation_alias="TEXTACY_ENABLED")
    enable_chunking: bool = Field(default=True, validation_alias="CHUNKING_ENABLED")
    chunk_max_chars: int = Field(default=200000, validation_alias="CHUNK_MAX_CHARS")
    log_truncate_length: int = Field(default=1000, validation_alias="LOG_TRUNCATE_LENGTH")
    topic_search_max_results: int = Field(default=5, validation_alias="TOPIC_SEARCH_MAX_RESULTS")
    max_concurrent_calls: int = Field(default=4, validation_alias="MAX_CONCURRENT_CALLS")
    summary_prompt_version: str = Field(default="v1", validation_alias="SUMMARY_PROMPT_VERSION")
    summary_streaming_enabled: bool = Field(
        default=True, validation_alias="SUMMARY_STREAMING_ENABLED"
    )
    summary_streaming_mode: str = Field(
        default="section", validation_alias="SUMMARY_STREAMING_MODE"
    )
    summary_streaming_provider_scope: str = Field(
        default="openrouter", validation_alias="SUMMARY_STREAMING_PROVIDER_SCOPE"
    )
    migration_shadow_mode_enabled: bool = Field(
        default=True, validation_alias="MIGRATION_SHADOW_MODE_ENABLED"
    )
    migration_shadow_mode_sample_rate: float = Field(
        default=0.0, validation_alias="MIGRATION_SHADOW_MODE_SAMPLE_RATE"
    )
    migration_shadow_mode_emit_match_logs: bool = Field(
        default=False, validation_alias="MIGRATION_SHADOW_MODE_EMIT_MATCH_LOGS"
    )
    migration_shadow_mode_timeout_ms: int = Field(
        default=250, validation_alias="MIGRATION_SHADOW_MODE_TIMEOUT_MS"
    )
    migration_shadow_mode_max_diffs: int = Field(
        default=8, validation_alias="MIGRATION_SHADOW_MODE_MAX_DIFFS"
    )
    migration_interface_backend: str = Field(
        default="rust", validation_alias="MIGRATION_INTERFACE_BACKEND"
    )
    migration_interface_sample_rate: float = Field(
        default=0.0, validation_alias="MIGRATION_INTERFACE_SAMPLE_RATE"
    )
    migration_interface_timeout_ms: int = Field(
        default=150, validation_alias="MIGRATION_INTERFACE_TIMEOUT_MS"
    )
    migration_interface_emit_match_logs: bool = Field(
        default=False, validation_alias="MIGRATION_INTERFACE_EMIT_MATCH_LOGS"
    )
    migration_interface_max_diffs: int = Field(
        default=8, validation_alias="MIGRATION_INTERFACE_MAX_DIFFS"
    )
    migration_telegram_runtime_timeout_ms: int = Field(
        default=150, validation_alias="MIGRATION_TELEGRAM_RUNTIME_TIMEOUT_MS"
    )
    migration_processing_orchestrator_backend: str = Field(
        default="python", validation_alias="MIGRATION_PROCESSING_ORCHESTRATOR_BACKEND"
    )
    migration_processing_orchestrator_timeout_ms: int = Field(
        default=250, validation_alias="MIGRATION_PROCESSING_ORCHESTRATOR_TIMEOUT_MS"
    )
    jwt_secret_key: str = Field(
        default="", validation_alias=AliasChoices("JWT_SECRET_KEY", "JWT_SECRET")
    )
    db_backup_enabled: bool = Field(default=True, validation_alias="DB_BACKUP_ENABLED")
    db_backup_interval_minutes: int = Field(
        default=360, validation_alias="DB_BACKUP_INTERVAL_MINUTES"
    )
    db_backup_retention: int = Field(default=14, validation_alias="DB_BACKUP_RETENTION")
    db_backup_dir: str | None = Field(default=None, validation_alias="DB_BACKUP_DIR")
    llm_provider: str = Field(default="openrouter", validation_alias="LLM_PROVIDER")
    telegram_reply_timeout_sec: float = Field(
        default=30.0, validation_alias="TELEGRAM_REPLY_TIMEOUT_SEC"
    )
    semaphore_acquire_timeout_sec: float = Field(
        default=30.0, validation_alias="SEMAPHORE_ACQUIRE_TIMEOUT_SEC"
    )
    llm_call_timeout_sec: float = Field(default=300.0, validation_alias="LLM_CALL_TIMEOUT_SEC")
    llm_call_max_retries: int = Field(default=2, validation_alias="LLM_CALL_MAX_RETRIES")
    json_parse_timeout_sec: float = Field(default=60.0, validation_alias="JSON_PARSE_TIMEOUT_SEC")
    summary_two_pass_enabled: bool = Field(
        default=False, validation_alias="SUMMARY_TWO_PASS_ENABLED"
    )
    rate_limit_max_requests: int = Field(default=10, validation_alias="RATE_LIMIT_MAX_REQUESTS")
    rate_limit_window_seconds: int = Field(default=60, validation_alias="RATE_LIMIT_WINDOW_SECONDS")
    rate_limit_max_concurrent: int = Field(default=3, validation_alias="RATE_LIMIT_MAX_CONCURRENT")
    related_reads_enabled: bool = Field(default=True, validation_alias="RELATED_READS_ENABLED")
    related_reads_min_similarity: float = Field(
        default=0.75, validation_alias="RELATED_READS_MIN_SIMILARITY"
    )

    @field_validator("llm_provider", mode="before")
    @classmethod
    def _validate_llm_provider(cls, value: Any) -> str:
        provider = str(value or "openrouter").lower().strip()
        valid_providers = {"openrouter", "openai", "anthropic"}
        if provider not in valid_providers:
            msg = f"Invalid LLM provider: {provider}. Must be one of {sorted(valid_providers)}"
            raise ValueError(msg)
        return provider

    @field_validator("log_level", mode="before")
    @classmethod
    def _validate_log_level(cls, value: Any) -> str:
        log_level = str(value or "INFO").upper()
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if log_level not in valid_levels:
            msg = f"Invalid log level: {value}. Must be one of {valid_levels}"
            raise ValueError(msg)
        return log_level

    @field_validator("request_timeout_sec", mode="before")
    @classmethod
    def _validate_timeout(cls, value: Any) -> int:
        try:
            timeout = int(str(value or 60))
        except ValueError as exc:  # pragma: no cover - defensive
            msg = "Timeout must be a valid integer"
            raise ValueError(msg) from exc
        if timeout <= 0:
            msg = "Timeout must be positive"
            raise ValueError(msg)
        if timeout > 3600:
            msg = "Timeout too large (max 3600 seconds)"
            raise ValueError(msg)
        return timeout

    @field_validator("preferred_lang", mode="before")
    @classmethod
    def _validate_lang(cls, value: Any) -> str:
        lang = str(value or "auto")
        if lang not in {"auto", "en", "ru"}:
            msg = f"Invalid language: {lang}. Must be one of {{'auto', 'en', 'ru'}}"
            raise ValueError(msg)
        return lang

    @field_validator("chunk_max_chars", "log_truncate_length", mode="before")
    @classmethod
    def _validate_positive_int(cls, value: Any, info: ValidationInfo) -> int:
        default = cls.model_fields[info.field_name].default
        return parse_positive_int(value, field_name=info.field_name, default=default)

    @field_validator(
        "telegram_reply_timeout_sec",
        "semaphore_acquire_timeout_sec",
        "llm_call_timeout_sec",
        "json_parse_timeout_sec",
        mode="before",
    )
    @classmethod
    def _validate_timeout_float(cls, value: Any, info: ValidationInfo) -> float:
        default = cls.model_fields[info.field_name].default
        try:
            parsed = float(str(value if value not in (None, "") else default))
        except (ValueError, TypeError) as exc:
            msg = f"{info.field_name} must be a valid number"
            raise ValueError(msg) from exc
        if parsed < 0.1 or parsed > 3600.0:
            msg = f"{info.field_name} must be between 0.1 and 3600 seconds, got {parsed}"
            raise ValueError(msg)
        return parsed

    @field_validator("topic_search_max_results", mode="before")
    @classmethod
    def _validate_topic_search_limit(cls, value: Any) -> int:
        default = cls.model_fields["topic_search_max_results"].default
        try:
            parsed = int(str(value if value not in (None, "") else default))
        except ValueError as exc:  # pragma: no cover - defensive
            msg = "Topic search max results must be a valid integer"
            raise ValueError(msg) from exc
        if parsed <= 0:
            msg = "Topic search max results must be positive"
            raise ValueError(msg)
        if parsed > 10:
            msg = "Topic search max results must be 10 or fewer"
            raise ValueError(msg)
        return parsed

    @field_validator("summary_prompt_version", mode="before")
    @classmethod
    def _validate_prompt_version(cls, value: Any) -> str:
        raw = str(value or "v1").strip()
        if not raw:
            msg = "Summary prompt version cannot be empty"
            raise ValueError(msg)
        if len(raw) > 30:
            msg = "Summary prompt version is too long"
            raise ValueError(msg)
        if any(ch.isspace() for ch in raw):
            msg = "Summary prompt version cannot contain whitespace"
            raise ValueError(msg)
        return raw

    @field_validator("summary_streaming_mode", mode="before")
    @classmethod
    def _validate_summary_streaming_mode(cls, value: Any) -> str:
        mode = str(value or "section").strip().lower()
        allowed = {"section", "disabled"}
        if mode not in allowed:
            msg = f"Summary streaming mode must be one of {sorted(allowed)}"
            raise ValueError(msg)
        return mode

    @field_validator("summary_streaming_provider_scope", mode="before")
    @classmethod
    def _validate_summary_streaming_scope(cls, value: Any) -> str:
        scope = str(value or "openrouter").strip().lower()
        allowed = {"openrouter", "all", "disabled"}
        if scope not in allowed:
            msg = f"Summary streaming provider scope must be one of {sorted(allowed)}"
            raise ValueError(msg)
        return scope

    @field_validator("migration_shadow_mode_enabled", mode="before")
    @classmethod
    def _validate_migration_shadow_mode_enabled(cls, value: Any) -> bool:
        raw = value if value not in (None, "") else True
        if isinstance(raw, str):
            normalized = raw.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                enabled = True
            elif normalized in {"0", "false", "no", "off"}:
                enabled = False
            else:
                msg = "MIGRATION_SHADOW_MODE_ENABLED must be a boolean value"
                raise ValueError(msg)
        else:
            enabled = bool(raw)
        if not enabled:
            msg = (
                "Migration shadow fallback modes are decommissioned; "
                "MIGRATION_SHADOW_MODE_ENABLED must be true"
            )
            raise ValueError(msg)
        return True

    @field_validator("migration_shadow_mode_sample_rate", mode="before")
    @classmethod
    def _validate_migration_shadow_sample_rate(cls, value: Any) -> float:
        default = cls.model_fields["migration_shadow_mode_sample_rate"].default
        try:
            parsed = float(str(value if value not in (None, "") else default))
        except (ValueError, TypeError) as exc:
            msg = "Migration shadow sample rate must be a valid number"
            raise ValueError(msg) from exc
        if parsed < 0.0 or parsed > 1.0:
            msg = "Migration shadow sample rate must be between 0.0 and 1.0"
            raise ValueError(msg)
        return parsed

    @field_validator("migration_shadow_mode_timeout_ms", mode="before")
    @classmethod
    def _validate_migration_shadow_timeout_ms(cls, value: Any) -> int:
        default = cls.model_fields["migration_shadow_mode_timeout_ms"].default
        try:
            parsed = int(str(value if value not in (None, "") else default))
        except ValueError as exc:
            msg = "Migration shadow timeout must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 25 or parsed > 10000:
            msg = "Migration shadow timeout must be between 25 and 10000 milliseconds"
            raise ValueError(msg)
        return parsed

    @field_validator("migration_shadow_mode_max_diffs", mode="before")
    @classmethod
    def _validate_migration_shadow_max_diffs(cls, value: Any) -> int:
        default = cls.model_fields["migration_shadow_mode_max_diffs"].default
        try:
            parsed = int(str(value if value not in (None, "") else default))
        except ValueError as exc:
            msg = "Migration shadow max diffs must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 1 or parsed > 64:
            msg = "Migration shadow max diffs must be between 1 and 64"
            raise ValueError(msg)
        return parsed

    @field_validator("migration_interface_backend", mode="before")
    @classmethod
    def _validate_migration_interface_backend(cls, value: Any) -> str:
        backend = str(value or "rust").strip().lower()
        if backend != "rust":
            msg = (
                "Migration interface backend fallback modes are decommissioned; "
                "MIGRATION_INTERFACE_BACKEND must be 'rust'"
            )
            raise ValueError(msg)
        return backend

    @field_validator("migration_interface_sample_rate", mode="before")
    @classmethod
    def _validate_migration_interface_sample_rate(cls, value: Any) -> float:
        default = cls.model_fields["migration_interface_sample_rate"].default
        try:
            parsed = float(str(value if value not in (None, "") else default))
        except (ValueError, TypeError) as exc:
            msg = "Migration interface sample rate must be a valid number"
            raise ValueError(msg) from exc
        if parsed < 0.0 or parsed > 1.0:
            msg = "Migration interface sample rate must be between 0.0 and 1.0"
            raise ValueError(msg)
        return parsed

    @field_validator("migration_interface_timeout_ms", mode="before")
    @classmethod
    def _validate_migration_interface_timeout_ms(cls, value: Any) -> int:
        default = cls.model_fields["migration_interface_timeout_ms"].default
        try:
            parsed = int(str(value if value not in (None, "") else default))
        except ValueError as exc:
            msg = "Migration interface timeout must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 25 or parsed > 10000:
            msg = "Migration interface timeout must be between 25 and 10000 milliseconds"
            raise ValueError(msg)
        return parsed

    @field_validator("migration_telegram_runtime_timeout_ms", mode="before")
    @classmethod
    def _validate_migration_telegram_runtime_timeout_ms(cls, value: Any) -> int:
        default = cls.model_fields["migration_telegram_runtime_timeout_ms"].default
        try:
            parsed = int(str(value if value not in (None, "") else default))
        except ValueError as exc:
            msg = "Migration telegram runtime timeout must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 25 or parsed > 10000:
            msg = "Migration telegram runtime timeout must be between 25 and 10000 milliseconds"
            raise ValueError(msg)
        return parsed

    @field_validator("migration_processing_orchestrator_backend", mode="before")
    @classmethod
    def _validate_migration_processing_orchestrator_backend(cls, value: Any) -> str:
        backend = str(value or "python").strip().lower()
        allowed = {"python", "rust"}
        if backend not in allowed:
            msg = f"Migration processing orchestrator backend must be one of {sorted(allowed)}"
            raise ValueError(msg)
        return backend

    @field_validator("migration_processing_orchestrator_timeout_ms", mode="before")
    @classmethod
    def _validate_migration_processing_orchestrator_timeout_ms(cls, value: Any) -> int:
        default = cls.model_fields["migration_processing_orchestrator_timeout_ms"].default
        try:
            parsed = int(str(value if value not in (None, "") else default))
        except ValueError as exc:
            msg = "Migration processing orchestrator timeout must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 25 or parsed > 10000:
            msg = (
                "Migration processing orchestrator timeout must be between 25 and 10000 "
                "milliseconds"
            )
            raise ValueError(msg)
        return parsed

    @field_validator("migration_interface_max_diffs", mode="before")
    @classmethod
    def _validate_migration_interface_max_diffs(cls, value: Any) -> int:
        default = cls.model_fields["migration_interface_max_diffs"].default
        try:
            parsed = int(str(value if value not in (None, "") else default))
        except ValueError as exc:
            msg = "Migration interface max diffs must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 1 or parsed > 64:
            msg = "Migration interface max diffs must be between 1 and 64"
            raise ValueError(msg)
        return parsed

    @field_validator("db_backup_interval_minutes", mode="before")
    @classmethod
    def _validate_backup_interval(cls, value: Any) -> int:
        try:
            parsed = int(str(value or 360))
        except ValueError as exc:
            msg = "DB backup interval (minutes) must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 5 or parsed > 10080:
            msg = "DB backup interval (minutes) must be between 5 and 10080"
            raise ValueError(msg)
        return parsed

    @field_validator("db_backup_retention", mode="before")
    @classmethod
    def _validate_backup_retention(cls, value: Any) -> int:
        try:
            parsed = int(str(value or 14))
        except ValueError as exc:
            msg = "DB backup retention must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 0 or parsed > 1000:
            msg = "DB backup retention must be between 0 and 1000"
            raise ValueError(msg)
        return parsed

    @field_validator("db_backup_dir", mode="before")
    @classmethod
    def _validate_backup_dir(cls, value: Any) -> str | None:
        if value is None:
            return None
        trimmed = str(value).strip()
        if not trimmed:
            return None
        if "\x00" in trimmed:
            msg = "DB backup directory contains invalid characters"
            raise ValueError(msg)
        return trimmed

    @field_validator("llm_call_max_retries", mode="before")
    @classmethod
    def _validate_llm_call_max_retries(cls, value: Any) -> int:
        try:
            parsed = int(str(value or 2))
        except ValueError as exc:
            msg = "LLM call max retries must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 0 or parsed > 5:
            msg = "LLM call max retries must be between 0 and 5"
            raise ValueError(msg)
        return parsed

    @field_validator("max_concurrent_calls", mode="before")
    @classmethod
    def _validate_max_concurrent_calls(cls, value: Any) -> int:
        try:
            parsed = int(str(value or 4))
        except ValueError as exc:
            msg = "Max concurrent calls must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 1 or parsed > 100:
            msg = "Max concurrent calls must be between 1 and 100"
            raise ValueError(msg)
        return parsed

    @field_validator("rate_limit_max_requests", mode="before")
    @classmethod
    def _validate_rate_limit_max_requests(cls, value: Any) -> int:
        try:
            parsed = int(str(value if value not in (None, "") else 10))
        except ValueError as exc:
            msg = "Rate limit max requests must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 1 or parsed > 100:
            msg = "Rate limit max requests must be between 1 and 100"
            raise ValueError(msg)
        return parsed

    @field_validator("rate_limit_window_seconds", mode="before")
    @classmethod
    def _validate_rate_limit_window_seconds(cls, value: Any) -> int:
        try:
            parsed = int(str(value if value not in (None, "") else 60))
        except ValueError as exc:
            msg = "Rate limit window seconds must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 10 or parsed > 3600:
            msg = "Rate limit window seconds must be between 10 and 3600"
            raise ValueError(msg)
        return parsed

    @field_validator("rate_limit_max_concurrent", mode="before")
    @classmethod
    def _validate_rate_limit_max_concurrent(cls, value: Any) -> int:
        try:
            parsed = int(str(value if value not in (None, "") else 3))
        except ValueError as exc:
            msg = "Rate limit max concurrent must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 1 or parsed > 20:
            msg = "Rate limit max concurrent must be between 1 and 20"
            raise ValueError(msg)
        return parsed

    @field_validator("related_reads_min_similarity", mode="before")
    @classmethod
    def _validate_related_reads_min_similarity(cls, value: Any) -> float:
        default = cls.model_fields["related_reads_min_similarity"].default
        try:
            parsed = float(str(value if value not in (None, "") else default))
        except (ValueError, TypeError) as exc:
            msg = "Related reads min similarity must be a valid number"
            raise ValueError(msg) from exc
        if parsed < 0.0 or parsed > 1.0:
            msg = "Related reads min similarity must be between 0.0 and 1.0"
            raise ValueError(msg)
        return parsed

    @field_validator("jwt_secret_key", mode="before")
    @classmethod
    def _validate_jwt_secret_key(cls, value: Any) -> str:
        if value in (None, ""):
            return ""
        secret = str(value).strip()
        if len(secret) < 32:
            logger.warning(
                "JWT secret key is shorter than 32 characters - this is insecure for production"
            )
        if len(secret) > 500:
            msg = "JWT secret key appears to be too long"
            raise ValueError(msg)
        return secret
