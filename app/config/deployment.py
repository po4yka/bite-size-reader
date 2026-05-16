from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DeploymentConfig(BaseModel):
    """Deployment environment and production-safety configuration."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    env: Literal["development", "staging", "production"] = Field(
        default="development",
        validation_alias="APP_ENV",
        description=(
            "Deployment environment. Set to 'production' to enable strict safety checks, "
            "including mandatory Redis-backed rate limiting."
        ),
    )
    api_public_exposure: bool = Field(
        default=False,
        validation_alias="API_PUBLIC_EXPOSURE",
        description=(
            "Set to true when the API is reachable from the public internet. "
            "Triggers production-level safety checks regardless of APP_ENV."
        ),
    )
    rate_limit_redis_override: bool = Field(
        default=False,
        validation_alias="RATE_LIMIT_REDIS_OVERRIDE",
        description=(
            "Emergency override: allow in-memory rate limiting in production. "
            "Must be explicitly set to acknowledge that multi-worker deployments "
            "will have per-process rate limit state (limits are not shared)."
        ),
    )

    @field_validator("env", mode="before")
    @classmethod
    def _validate_env(cls, value: Any) -> str:
        if value in (None, ""):
            return "development"
        v = str(value).strip().lower()
        allowed = ("development", "staging", "production")
        if v not in allowed:
            msg = f"APP_ENV must be one of: {', '.join(allowed)}"
            raise ValueError(msg)
        return v

    @property
    def is_production_mode(self) -> bool:
        """True when running in production or with public API exposure."""
        return self.env == "production" or self.api_public_exposure
