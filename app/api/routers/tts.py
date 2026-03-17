"""TTS audio generation endpoints for summaries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from app.api.exceptions import FeatureDisabledError, ResourceNotFoundError
from app.api.models.responses import success_response
from app.api.routers.auth import get_current_user
from app.config import load_config
from app.core.logging_utils import get_logger
from app.db.models import AudioGeneration, Request, Summary

logger = get_logger(__name__)

router = APIRouter()

# Module-level singleton — avoids creating a new httpx.AsyncClient per request.
_tts_service = None


def _get_tts_config():
    """Lazy-load TTS config."""
    return load_config(allow_stub_telegram=True).tts


def _get_tts_service():
    """Return a shared TTSService instance (lazy init)."""
    global _tts_service
    if _tts_service is None:
        from app.services.tts_service import TTSService

        _tts_service = TTSService(_get_tts_config())
    return _tts_service


def _get_user_summary(summary_id: int, user_id: int) -> Summary:
    """Get a summary that belongs to the given user, or raise 404."""
    row: Summary | None = (
        Summary.select()
        .join(Request)
        .where((Summary.id == summary_id) & (Request.user_id == user_id))
        .first()
    )
    if row is None:
        raise ResourceNotFoundError("Summary", summary_id)
    return row


@router.post("/{summary_id}/audio")
async def generate_audio(
    summary_id: int,
    source_field: str = Query("summary_1000", pattern="^(summary_250|summary_1000|tldr)$"),
    user: dict[str, Any] = Depends(get_current_user),
):
    """Trigger audio generation for a summary.

    Returns immediately with status if already cached, otherwise generates
    on-demand and returns the result.
    """
    tts_config = _get_tts_config()
    if not tts_config.enabled:
        raise FeatureDisabledError("tts")

    _get_user_summary(summary_id, user["user_id"])

    result = await _get_tts_service().generate_audio(summary_id, source_field=source_field)

    return success_response(
        {
            "summaryId": summary_id,
            "status": result.status,
            "charCount": result.char_count,
            "fileSizeBytes": result.file_size_bytes,
            "latencyMs": result.latency_ms,
            "error": result.error,
        }
    )


@router.get("/{summary_id}/audio")
async def get_audio(
    summary_id: int,
    user: dict[str, Any] = Depends(get_current_user),
):
    """Stream/download the generated audio file for a summary."""
    tts_config = _get_tts_config()
    if not tts_config.enabled:
        raise FeatureDisabledError("tts")

    _get_user_summary(summary_id, user["user_id"])

    # Look up audio record
    row: AudioGeneration | None = (
        AudioGeneration.select()
        .where((AudioGeneration.summary == summary_id) & (AudioGeneration.status == "completed"))
        .first()
    )
    if row is None or not row.file_path:
        raise ResourceNotFoundError("audio", summary_id)

    file_path = Path(row.file_path)
    if not file_path.is_file():
        raise ResourceNotFoundError("audio_file", summary_id)

    return FileResponse(
        path=str(file_path),
        media_type="audio/mpeg",
        filename=f"summary-{summary_id}.mp3",
    )
