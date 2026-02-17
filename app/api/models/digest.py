"""Pydantic models for Digest Mini App API."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - required at runtime by Pydantic

from pydantic import BaseModel, Field


class ChannelSubscriptionResponse(BaseModel):
    """A channel subscription entry."""

    id: int
    username: str
    title: str | None = None
    is_active: bool
    fetch_error_count: int = 0
    last_error: str | None = None
    created_at: datetime


class SubscribeRequest(BaseModel):
    """Request to subscribe to a channel."""

    channel_username: str = Field(..., min_length=5, max_length=32)


class DigestPreferenceResponse(BaseModel):
    """User digest preferences with source annotations."""

    delivery_time: str
    delivery_time_source: str  # "user" | "global"
    timezone: str
    timezone_source: str
    hours_lookback: int
    hours_lookback_source: str
    max_posts_per_digest: int
    max_posts_per_digest_source: str
    min_relevance_score: float
    min_relevance_score_source: str


class UpdatePreferenceRequest(BaseModel):
    """Request to update digest preferences. Null fields keep current value."""

    delivery_time: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")
    timezone: str | None = Field(None, max_length=50)
    hours_lookback: int | None = Field(None, ge=1, le=168)
    max_posts_per_digest: int | None = Field(None, ge=1, le=100)
    min_relevance_score: float | None = Field(None, ge=0.0, le=1.0)


class DigestDeliveryResponse(BaseModel):
    """A digest delivery record."""

    id: int
    delivered_at: datetime
    post_count: int
    channel_count: int
    digest_type: str


class TriggerDigestResponse(BaseModel):
    """Response for on-demand digest trigger."""

    status: str = "queued"
    correlation_id: str
