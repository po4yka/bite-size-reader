"""OpenTelemetry observability configuration."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class OtelConfig(BaseSettings):
    model_config = {"populate_by_name": True, "extra": "ignore"}

    enabled: bool = Field(default=False, validation_alias="OTEL_ENABLED")
    endpoint: str = Field(
        default="http://tempo:4317",
        validation_alias="OTEL_EXPORTER_OTLP_ENDPOINT",
    )
    sqlite3_enabled: bool = Field(default=False, validation_alias="OTEL_SQLITE3_ENABLED")
    db_session_spans_enabled: bool = Field(
        default=False, validation_alias="OTEL_DB_SESSION_SPANS_ENABLED"
    )
    sample_ratio: float = Field(default=1.0, validation_alias="OTEL_SAMPLE_RATIO")

    @classmethod
    def from_env(cls) -> OtelConfig:
        return cls()
