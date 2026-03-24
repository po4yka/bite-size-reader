"""TTS audio generation endpoints for summaries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse

from app.api.dependencies.database import (
    get_audio_generation_repository,
    get_session_manager,
    get_summary_repository,
)
from app.api.exceptions import FeatureDisabledError, ResourceNotFoundError
from app.api.models.responses import success_response
from app.api.routers.auth import get_current_user
from app.application.services.tts_service import TTSService
from app.config import load_config
from app.infrastructure.audio.elevenlabs_provider import ElevenLabsTTSProviderAdapter
from app.infrastructure.audio.filesystem_storage import FileSystemAudioStorageAdapter

router = APIRouter()


def _get_tts_config():
    return load_config(allow_stub_telegram=True).tts


def _get_tts_service(request: Request) -> TTSService:
    config = _get_tts_config()
    db = get_session_manager(request)
    return TTSService(
        summary_repository=get_summary_repository(db, request),
        audio_generation_repository=get_audio_generation_repository(db, request),
        tts_provider=ElevenLabsTTSProviderAdapter(config),
        audio_storage=FileSystemAudioStorageAdapter(config.audio_storage_path),
        voice_id=config.voice_id,
        model_name=config.model,
        max_chars_per_request=config.max_chars_per_request,
    )


async def _ensure_summary_owned(summary_id: int, user_id: int, request: Request) -> None:
    summary = await get_summary_repository(
        get_session_manager(request), request
    ).async_get_summary_by_id(summary_id)
    if summary is None or summary.get("user_id") != user_id:
        raise ResourceNotFoundError("Summary", summary_id)


@router.post("/{summary_id}/audio")
async def generate_audio(
    summary_id: int,
    request: Request,
    source_field: str = Query("summary_1000", pattern="^(summary_250|summary_1000|tldr)$"),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Generate audio for a summary, reusing cached output when available."""
    tts_config = _get_tts_config()
    if not tts_config.enabled:
        raise FeatureDisabledError("tts")

    await _ensure_summary_owned(summary_id, user["user_id"], request)
    service = _get_tts_service(request)
    try:
        result = await service.generate_audio(summary_id, source_field=source_field)
    finally:
        await service.close()

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
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
) -> FileResponse:
    """Stream/download the generated audio file for a summary."""
    tts_config = _get_tts_config()
    if not tts_config.enabled:
        raise FeatureDisabledError("tts")

    await _ensure_summary_owned(summary_id, user["user_id"], request)
    service = _get_tts_service(request)
    try:
        result = await service.get_audio_status(summary_id)
    finally:
        await service.close()

    if result is None or result.status != "completed" or not result.file_path:
        raise ResourceNotFoundError("audio", summary_id)

    file_path = Path(result.file_path)
    if not file_path.is_file():
        raise ResourceNotFoundError("audio_file", summary_id)

    return FileResponse(
        path=str(file_path),
        media_type="audio/mpeg",
        filename=f"summary-{summary_id}.mp3",
    )
