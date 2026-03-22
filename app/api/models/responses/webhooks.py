"""Webhook API response models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WebhookSubscriptionResponse(BaseModel):
    id: int
    name: str | None = None
    url: str
    events: list[str]
    enabled: bool
    status: str
    secret_preview: str = Field(serialization_alias="secretPreview")
    failure_count: int = Field(serialization_alias="failureCount")
    last_delivery_at: str | None = Field(default=None, serialization_alias="lastDeliveryAt")
    created_at: str = Field(serialization_alias="createdAt")
    updated_at: str = Field(serialization_alias="updatedAt")


class WebhookDeliveryResponse(BaseModel):
    id: int
    event_type: str = Field(serialization_alias="eventType")
    response_status: int | None = Field(default=None, serialization_alias="responseStatus")
    success: bool
    attempt: int
    duration_ms: int | None = Field(default=None, serialization_alias="durationMs")
    error: str | None = None
    created_at: str = Field(serialization_alias="createdAt")
