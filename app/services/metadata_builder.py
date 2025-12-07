"""Service for building metadata and note text for vector storage."""

from __future__ import annotations

from typing import Any

from app.infrastructure.vector.chroma_schemas import ChromaMetadata
from app.services.note_text_builder import build_note_text


class MetadataBuilder:
    """Centralized logic for extracting metadata and building note text."""

    @staticmethod
    def extract_user_note(payload: dict[str, Any] | None) -> str | None:
        """Extract user note from payload or metadata."""
        payload = payload or {}
        metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}

        for key in ("user_note", "note", "notes"):
            value = payload.get(key)
            if value:
                return str(value)

            meta_value = metadata.get(key)
            if meta_value:
                return str(meta_value)
        return None

    @staticmethod
    def build_metadata(
        payload: dict[str, Any] | None,
        summary_row: dict[str, Any] | None = None,
        user_scope: str | None = None,
    ) -> dict[str, Any]:
        """Build standardized metadata dictionary for vector storage."""
        payload = payload or {}
        metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
        request_data = (
            summary_row.get("request") if summary_row and isinstance(summary_row, dict) else {}
        )

        url = (
            metadata.get("canonical_url")
            or metadata.get("url")
            or (request_data or {}).get("normalized_url")
            or (request_data or {}).get("input_url")
        )

        title = metadata.get("title") or payload.get("title")
        source = metadata.get("domain") or metadata.get("source")
        published_at = metadata.get("published_at") or metadata.get("published")

        clean_metadata = {
            "url": url,
            "title": title,
            "source": source,
            "published_at": published_at,
            "user_scope": user_scope,
        }

        # Add IDs if available in summary_row
        if summary_row:
            clean_metadata["request_id"] = summary_row.get("request_id")
            clean_metadata["summary_id"] = summary_row.get("id") or summary_row.get("summary_id")
            clean_metadata["language"] = summary_row.get("lang") or summary_row.get("language")

        return {k: v for k, v in clean_metadata.items() if v is not None}

    @classmethod
    def prepare_for_upsert(
        cls,
        request_id: int,
        summary_id: int,
        payload: dict[str, Any],
        language: str | None,
        user_scope: str,
        environment: str,
        summary_row: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Prepare text and metadata for upsert."""
        user_note = cls.extract_user_note(payload)
        note_text = build_note_text(
            payload,
            request_id=request_id,
            summary_id=summary_id,
            language=language,
            user_note=user_note,
        )

        if not note_text.text:
            return "", {}

        # Combine summary_row data if not provided
        if not summary_row:
            summary_row = {
                "request_id": request_id,
                "id": summary_id,
                "lang": language,
            }

        base_metadata = cls.build_metadata(payload, summary_row, user_scope)

        final_metadata = {
            **note_text.metadata,
            **base_metadata,
            "text": note_text.text,
            "environment": environment,
            "user_scope": user_scope,
        }

        validated = ChromaMetadata(**final_metadata).model_dump()

        return note_text.text, validated
