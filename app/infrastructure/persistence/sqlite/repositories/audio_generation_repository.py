"""SQLite adapter for cached TTS audio generation records."""

from __future__ import annotations

from typing import Any

import peewee

from app.db.models import AudioGeneration, model_to_dict
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository


class SqliteAudioGenerationRepositoryAdapter(SqliteBaseRepository):
    """Persist and query generated summary audio."""

    async def async_get_completed_generation(
        self,
        summary_id: int,
        source_field: str,
    ) -> dict[str, Any] | None:
        """Return a completed generation record for the requested source field."""

        def _get() -> dict[str, Any] | None:
            row = (
                AudioGeneration.select()
                .where(
                    (AudioGeneration.summary == summary_id)
                    & (AudioGeneration.source_field == source_field)
                    & (AudioGeneration.status == "completed")
                )
                .first()
            )
            return model_to_dict(row)

        return await self._execute(
            _get,
            operation_name="get_completed_audio_generation",
            read_only=True,
        )

    async def async_get_latest_generation(self, summary_id: int) -> dict[str, Any] | None:
        """Return the latest generation row for the summary."""

        def _get() -> dict[str, Any] | None:
            row = (
                AudioGeneration.select()
                .where(AudioGeneration.summary == summary_id)
                .order_by(AudioGeneration.created_at.desc())
                .first()
            )
            return model_to_dict(row)

        return await self._execute(
            _get,
            operation_name="get_latest_audio_generation",
            read_only=True,
        )

    async def async_mark_generation_started(
        self,
        *,
        summary_id: int,
        source_field: str,
        voice_id: str,
        model_name: str,
        language: str | None,
        char_count: int,
    ) -> None:
        """Create or update a generation row in generating state."""

        def _mark() -> None:
            row, _ = AudioGeneration.get_or_create(
                summary=summary_id,
                defaults={
                    "provider": "elevenlabs",
                    "voice_id": voice_id,
                    "model": model_name,
                    "source_field": source_field,
                    "language": language,
                    "status": "generating",
                    "char_count": char_count,
                },
            )
            row.voice_id = voice_id
            row.model = model_name
            row.source_field = source_field
            row.language = language
            row.status = "generating"
            row.char_count = char_count
            row.error_text = None
            row.file_path = None
            row.file_size_bytes = None
            row.latency_ms = None
            row.save()

        await self._execute(_mark, operation_name="mark_audio_generation_started")

    async def async_mark_generation_completed(
        self,
        *,
        summary_id: int,
        source_field: str,
        file_path: str,
        file_size_bytes: int,
        char_count: int,
        latency_ms: int,
    ) -> None:
        """Persist a completed generation result."""

        def _mark() -> None:
            AudioGeneration.update(
                {
                    AudioGeneration.source_field: source_field,
                    AudioGeneration.status: "completed",
                    AudioGeneration.file_path: file_path,
                    AudioGeneration.file_size_bytes: file_size_bytes,
                    AudioGeneration.char_count: char_count,
                    AudioGeneration.latency_ms: latency_ms,
                    AudioGeneration.error_text: None,
                }
            ).where(AudioGeneration.summary == summary_id).execute()

        await self._execute(_mark, operation_name="mark_audio_generation_completed")

    async def async_mark_generation_failed(
        self,
        *,
        summary_id: int,
        source_field: str,
        error_text: str,
        latency_ms: int,
    ) -> None:
        """Persist a failed generation result."""

        def _mark() -> None:
            updated = (
                AudioGeneration.update(
                    {
                        AudioGeneration.source_field: source_field,
                        AudioGeneration.status: "error",
                        AudioGeneration.error_text: error_text,
                        AudioGeneration.latency_ms: latency_ms,
                    }
                )
                .where(AudioGeneration.summary == summary_id)
                .execute()
            )
            if updated:
                return

            try:
                AudioGeneration.create(
                    summary=summary_id,
                    provider="elevenlabs",
                    voice_id="",
                    model="",
                    source_field=source_field,
                    status="error",
                    error_text=error_text,
                    latency_ms=latency_ms,
                )
            except peewee.IntegrityError:
                AudioGeneration.update(
                    {
                        AudioGeneration.source_field: source_field,
                        AudioGeneration.status: "error",
                        AudioGeneration.error_text: error_text,
                        AudioGeneration.latency_ms: latency_ms,
                    }
                ).where(AudioGeneration.summary == summary_id).execute()

        await self._execute(_mark, operation_name="mark_audio_generation_failed")
