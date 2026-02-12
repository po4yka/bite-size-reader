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
        user_id: int | None = None,
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
            "user_id": user_id,
            "text": note_text.text,
            "environment": environment,
            "user_scope": user_scope,
        }

        validated = ChromaMetadata(**final_metadata).model_dump()

        return note_text.text, validated

    @classmethod
    def prepare_chunk_windows_for_upsert(
        cls,
        request_id: int,
        summary_id: int,
        payload: dict[str, Any],
        language: str | None,
        user_scope: str,
        environment: str,
        user_id: int | None = None,
        *,
        window_size: int = 3,
        booster_limit: int = 8,
    ) -> list[tuple[str, dict[str, Any]]]:
        """Build per-chunk window texts and metadata for multi-vector upserts."""

        payload = payload or {}
        semantic_chunks = payload.get("semantic_chunks") or []
        if not semantic_chunks:
            return []

        summary_row = {
            "request_id": request_id,
            "id": summary_id,
            "lang": language,
        }
        base_metadata = cls.build_metadata(payload, summary_row, user_scope)

        topics = []
        if isinstance(payload.get("topic_tags"), list):
            topics.extend([str(tag).lstrip("#") for tag in payload["topic_tags"] if tag])

        boosters = [
            str(b).strip() for b in (payload.get("semantic_boosters") or []) if str(b).strip()
        ][:booster_limit]
        expansion = [
            str(t).strip()
            for t in (payload.get("query_expansion_keywords") or [])
            if str(t).strip()
        ][:30]

        window_radius = max(0, (window_size - 1) // 2)
        prepared: list[tuple[str, dict[str, Any]]] = []

        for idx, chunk in enumerate(semantic_chunks):
            if not isinstance(chunk, dict):
                continue

            chunk_text = str(chunk.get("text") or "").strip()
            if not chunk_text:
                continue

            local_summary = str(chunk.get("local_summary") or "").strip() or None
            local_keywords_raw = chunk.get("local_keywords") or []
            local_keywords = [
                str(k).strip() for k in local_keywords_raw if isinstance(k, str) and str(k).strip()
            ]

            chunk_topics = []
            if isinstance(chunk.get("topics"), list):
                chunk_topics = [str(t).lstrip("#") for t in chunk["topics"] if t]
            chunk_topics = chunk_topics or topics

            chunk_language = chunk.get("language") or language
            chunk_section = chunk.get("section") or base_metadata.get("section")

            chunk_id = str(chunk.get("chunk_id") or f"{summary_id}:{idx}")
            window_id = str(chunk.get("window_id") or f"{summary_id}:w{idx}")

            neighbor_chunk_ids: list[str] = []
            for neighbor_idx in range(
                max(0, idx - window_radius), min(len(semantic_chunks), idx + window_radius + 1)
            ):
                if neighbor_idx == idx:
                    continue
                neighbor = semantic_chunks[neighbor_idx]
                if isinstance(neighbor, dict):
                    neighbor_id = str(neighbor.get("chunk_id") or f"{summary_id}:{neighbor_idx}")
                    neighbor_chunk_ids.append(neighbor_id)

            text_parts = [chunk_text]
            if local_summary:
                text_parts.append(local_summary)
            if boosters:
                text_parts.extend(boosters)
            if local_keywords:
                text_parts.extend(local_keywords[:3])

            embedding_text = " ".join(part for part in text_parts if part).strip()
            if not embedding_text:
                continue

            metadata = {
                **base_metadata,
                "request_id": request_id,
                "summary_id": summary_id,
                "user_id": user_id,
                "language": chunk_language,
                "section": chunk_section,
                "topics": chunk_topics,
                "tags": chunk_topics,
                "semantic_boosters": boosters,
                "query_expansion_keywords": expansion,
                "local_keywords": local_keywords,
                "local_summary": local_summary,
                "text": embedding_text,
                "chunk_id": chunk_id,
                "window_id": window_id,
                "window_index": idx,
                "neighbor_chunk_ids": neighbor_chunk_ids,
                "user_scope": user_scope,
                "environment": environment,
            }

            validated = ChromaMetadata(**metadata).model_dump()
            prepared.append((embedding_text, validated))

        return prepared
