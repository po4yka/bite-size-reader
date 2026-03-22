# ruff: noqa: TC001
"""Sync API response models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .common import PaginationInfo


class SyncSessionData(BaseModel):
    session_id: str = Field(serialization_alias="sessionId")
    expires_at: str = Field(serialization_alias="expiresAt")
    default_limit: int = Field(serialization_alias="defaultLimit")
    max_limit: int = Field(serialization_alias="maxLimit")
    last_issued_since: int | None = Field(default=None, serialization_alias="lastIssuedSince")


class SyncEntityEnvelope(BaseModel):
    entity_type: str = Field(serialization_alias="entityType")
    id: int | str
    server_version: int = Field(serialization_alias="serverVersion")
    updated_at: str = Field(serialization_alias="updatedAt")
    deleted_at: str | None = Field(default=None, serialization_alias="deletedAt")
    summary: dict[str, Any] | None = None
    request: dict[str, Any] | None = None
    preference: dict[str, Any] | None = None
    stat: dict[str, Any] | None = None
    crawl_result: dict[str, Any] | None = Field(default=None, serialization_alias="crawlResult")
    llm_call: dict[str, Any] | None = Field(default=None, serialization_alias="llmCall")
    highlight: dict[str, Any] | None = None
    tag: dict[str, Any] | None = None
    summary_tag: dict[str, Any] | None = Field(default=None, serialization_alias="summaryTag")


class FullSyncResponseData(BaseModel):
    session_id: str = Field(serialization_alias="sessionId")
    has_more: bool = Field(serialization_alias="hasMore")
    next_since: int | None = Field(default=None, serialization_alias="nextSince")
    items: list[SyncEntityEnvelope]
    pagination: PaginationInfo


class DeltaSyncResponseData(BaseModel):
    session_id: str = Field(serialization_alias="sessionId")
    since: int
    has_more: bool = Field(serialization_alias="hasMore")
    next_since: int | None = Field(default=None, serialization_alias="nextSince")
    created: list[SyncEntityEnvelope]
    updated: list[SyncEntityEnvelope]
    deleted: list[SyncEntityEnvelope]


class SyncApplyItemResult(BaseModel):
    entity_type: str = Field(serialization_alias="entityType")
    id: int | str
    status: Literal["applied", "conflict", "invalid"]
    server_version: int | None = Field(default=None, serialization_alias="serverVersion")
    server_snapshot: dict[str, Any] | None = Field(
        default=None, serialization_alias="serverSnapshot"
    )
    error_code: str | None = Field(default=None, serialization_alias="errorCode")


class SyncApplyResponseData(BaseModel):
    session_id: str = Field(serialization_alias="sessionId")
    results: list[SyncApplyItemResult]
    conflicts: list[SyncApplyItemResult] | None = None
    has_more: bool | None = Field(default=None, serialization_alias="hasMore")
