"""Backup and import API response models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BackupResponse(BaseModel):
    id: int
    type: str
    status: str
    file_path: str | None = Field(default=None, serialization_alias="filePath")
    file_size_bytes: int | None = Field(default=None, serialization_alias="fileSizeBytes")
    items_count: int | None = Field(default=None, serialization_alias="itemsCount")
    error: str | None = None
    created_at: str = Field(serialization_alias="createdAt")
    updated_at: str = Field(serialization_alias="updatedAt")


class ImportJobResponse(BaseModel):
    id: int
    source_format: str = Field(serialization_alias="sourceFormat")
    file_name: str | None = Field(default=None, serialization_alias="fileName")
    status: str
    total_items: int = Field(serialization_alias="totalItems")
    processed_items: int = Field(serialization_alias="processedItems")
    created_items: int = Field(serialization_alias="createdItems")
    skipped_items: int = Field(serialization_alias="skippedItems")
    failed_items: int = Field(serialization_alias="failedItems")
    errors: list[str] = Field(default_factory=list)
    created_at: str = Field(serialization_alias="createdAt")
    updated_at: str = Field(serialization_alias="updatedAt")
