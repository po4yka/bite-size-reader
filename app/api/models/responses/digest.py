"""Digest API response models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CustomDigestResponse(BaseModel):
    id: str
    title: str | None = None
    content: str | None = None
    status: str
    created_at: str = Field(serialization_alias="createdAt")
