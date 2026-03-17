"""TTS service -- orchestrates audio generation with caching and DB persistence."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from app.adapters.elevenlabs.exceptions import ElevenLabsError
from app.adapters.elevenlabs.tts_client import ElevenLabsTTSClient
from app.db.models import AudioGeneration, Summary

if TYPE_CHECKING:
    from app.config.tts import ElevenLabsConfig

logger = logging.getLogger(__name__)

_VALID_SOURCE_FIELDS = frozenset({"summary_250", "summary_1000", "tldr"})


@dataclass(frozen=True)
class AudioGenerationResult:
    summary_id: int
    status: str
    file_path: str | None = None
    file_size_bytes: int | None = None
    char_count: int | None = None
    latency_ms: int | None = None
    error: str | None = None


class TTSService:
    """Orchestrates TTS generation, caching, and DB persistence."""

    def __init__(self, config: ElevenLabsConfig) -> None:
        self._config = config
        self._client = ElevenLabsTTSClient(config)

    async def generate_audio(
        self, summary_id: int, *, source_field: str = "summary_1000"
    ) -> AudioGenerationResult:
        """Generate audio for a summary, returning cached result if available."""
        if source_field not in _VALID_SOURCE_FIELDS:
            source_field = "summary_1000"

        # Check cache
        existing: AudioGeneration | None = await asyncio.to_thread(
            lambda: (
                AudioGeneration.select()
                .where(
                    (AudioGeneration.summary == summary_id)
                    & (AudioGeneration.source_field == source_field)
                    & (AudioGeneration.status == "completed")
                )
                .first()
            )
        )
        if existing and existing.file_path and Path(existing.file_path).is_file():
            return AudioGenerationResult(
                summary_id=summary_id,
                status="completed",
                file_path=existing.file_path,
                file_size_bytes=existing.file_size_bytes,
                char_count=existing.char_count,
                latency_ms=existing.latency_ms,
            )

        # Load summary
        summary: Summary | None = await asyncio.to_thread(
            lambda: Summary.get_or_none(Summary.id == summary_id)
        )
        if summary is None:
            return AudioGenerationResult(
                summary_id=summary_id, status="error", error="Summary not found"
            )

        payload = summary.json_payload or {}
        text = str(payload.get(source_field, "") or "").strip()
        if not text:
            # Fallback to summary_1000 -> summary_250 -> tldr
            for fallback in ("summary_1000", "summary_250", "tldr"):
                text = str(payload.get(fallback, "") or "").strip()
                if text:
                    source_field = fallback
                    break

        if not text:
            return AudioGenerationResult(
                summary_id=summary_id, status="error", error="No summary text available"
            )

        # Create or update DB record
        def _upsert() -> AudioGeneration:
            _row, _ = AudioGeneration.get_or_create(
                summary=summary_id,
                defaults={
                    "voice_id": self._config.voice_id,
                    "model": self._config.model,
                    "source_field": source_field,
                    "language": summary.lang,
                    "status": "generating",
                    "char_count": len(text),
                },
            )
            if _row.status != "generating":
                _row.status = "generating"
                _row.source_field = source_field
                _row.char_count = len(text)
                _row.error_text = None
                _row.save()
            return _row

        row: AudioGeneration = await asyncio.to_thread(_upsert)

        # Synthesize
        start = time.monotonic()
        try:
            if len(text) > self._config.max_chars_per_request:
                audio_bytes = await self._client.synthesize_long(text)
            else:
                audio_bytes = await self._client.synthesize(text)
        except ElevenLabsError as exc:
            latency = int((time.monotonic() - start) * 1000)
            error_msg = str(exc)[:500]
            row.status = "error"
            row.error_text = error_msg
            row.latency_ms = latency
            await asyncio.to_thread(row.save)
            logger.error(
                "tts_generation_failed",
                extra={"summary_id": summary_id, "error": error_msg, "latency_ms": latency},
            )
            return AudioGenerationResult(
                summary_id=summary_id, status="error", error=error_msg, latency_ms=latency
            )

        latency_ms = int((time.monotonic() - start) * 1000)

        # Write file
        storage_dir = Path(self._config.audio_storage_path)
        storage_dir.mkdir(parents=True, exist_ok=True)
        file_path = storage_dir / f"{summary_id}.mp3"
        file_path.write_bytes(audio_bytes)
        file_size = len(audio_bytes)

        # Update DB
        row.status = "completed"
        row.file_path = str(file_path)
        row.file_size_bytes = file_size
        row.latency_ms = latency_ms
        await asyncio.to_thread(row.save)

        logger.info(
            "tts_generation_completed",
            extra={
                "summary_id": summary_id,
                "file_size_bytes": file_size,
                "char_count": len(text),
                "latency_ms": latency_ms,
                "source_field": source_field,
            },
        )

        return AudioGenerationResult(
            summary_id=summary_id,
            status="completed",
            file_path=str(file_path),
            file_size_bytes=file_size,
            char_count=len(text),
            latency_ms=latency_ms,
        )

    @staticmethod
    def get_audio_status(summary_id: int) -> AudioGenerationResult | None:
        """Check if audio exists for a summary."""
        row: AudioGeneration | None = (
            AudioGeneration.select().where(AudioGeneration.summary == summary_id).first()
        )
        if row is None:
            return None
        return AudioGenerationResult(
            summary_id=summary_id,
            status=row.status,
            file_path=row.file_path,
            file_size_bytes=row.file_size_bytes,
            char_count=row.char_count,
            latency_ms=row.latency_ms,
            error=row.error_text,
        )

    async def close(self) -> None:
        await self._client.close()
