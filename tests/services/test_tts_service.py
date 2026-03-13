"""Unit tests for TTSService."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.elevenlabs.exceptions import ElevenLabsAPIError
from app.services.tts_service import AudioGenerationResult, TTSService


def _make_config(tmp_path) -> SimpleNamespace:
    return SimpleNamespace(
        api_key="test-key",
        voice_id="voice-abc",
        model="eleven_multilingual_v2",
        output_format="mp3_44100_128",
        stability=0.5,
        similarity_boost=0.75,
        speed=1.0,
        timeout_sec=30.0,
        max_chars_per_request=5000,
        audio_storage_path=str(tmp_path),
    )


def _make_audio_row(
    *,
    status: str = "completed",
    file_path: str | None = None,
    file_size_bytes: int | None = None,
    char_count: int | None = None,
    latency_ms: int | None = None,
    error_text: str | None = None,
    lang: str = "en",
) -> MagicMock:
    row = MagicMock()
    row.status = status
    row.file_path = file_path
    row.file_size_bytes = file_size_bytes
    row.char_count = char_count
    row.latency_ms = latency_ms
    row.error_text = error_text
    row.lang = lang
    return row


def _make_summary(*, payload: dict | None = None, lang: str = "en") -> MagicMock:
    summary = MagicMock()
    summary.lang = lang
    summary.json_payload = payload or {
        "summary_250": "Short summary.",
        "summary_1000": "Long summary with more detail.",
        "tldr": "TL;DR here.",
    }
    return summary


@pytest.mark.asyncio(loop_scope="function")
async def test_returns_cached_result_when_completed_file_exists(tmp_path):
    """Cache hit: completed row with existing file returns immediately."""
    cfg = _make_config(tmp_path)
    audio_file = tmp_path / "1.mp3"
    audio_file.write_bytes(b"cached_audio")

    row = _make_audio_row(
        status="completed",
        file_path=str(audio_file),
        file_size_bytes=len(b"cached_audio"),
        char_count=20,
        latency_ms=500,
    )

    with patch("app.services.tts_service.ElevenLabsTTSClient"):
        service = TTSService(cfg)

    with patch("asyncio.to_thread") as mock_to_thread:
        # First call (cache check) returns the completed row; all others never reached.
        mock_to_thread.return_value = row
        result = await service.generate_audio(1)

    assert result.status == "completed"
    assert result.file_path == str(audio_file)
    assert result.file_size_bytes == len(b"cached_audio")


@pytest.mark.asyncio(loop_scope="function")
async def test_returns_error_when_summary_not_found(tmp_path):
    cfg = _make_config(tmp_path)

    with patch("app.services.tts_service.ElevenLabsTTSClient"):
        service = TTSService(cfg)

    call_count = 0

    async def _side_effect(fn):
        nonlocal call_count
        call_count += 1

    with patch("asyncio.to_thread", side_effect=_side_effect):
        result = await service.generate_audio(999)

    assert result.status == "error"
    assert "not found" in (result.error or "").lower()


@pytest.mark.asyncio(loop_scope="function")
async def test_falls_back_through_source_field_chain(tmp_path):
    """When summary_1000 is empty, falls back to summary_250."""
    cfg = _make_config(tmp_path)
    summary = _make_summary(
        payload={"summary_250": "Fallback text.", "summary_1000": "", "tldr": ""}
    )
    row = _make_audio_row(status="generating")

    audio_bytes = b"fallback_audio"

    # 4 to_thread calls: cache check, load summary, _upsert, final row.save
    call_results = [None, summary, row, None]
    idx = 0

    async def _to_thread(fn):
        nonlocal idx
        result = call_results[idx]
        idx += 1
        return result

    mock_client = AsyncMock()
    mock_client.synthesize = AsyncMock(return_value=audio_bytes)
    mock_client.synthesize_long = AsyncMock(return_value=audio_bytes)

    with patch("app.services.tts_service.ElevenLabsTTSClient", return_value=mock_client):
        service = TTSService(cfg)

    with patch("asyncio.to_thread", side_effect=_to_thread):
        result = await service.generate_audio(1, source_field="summary_1000")

    assert result.status == "completed"
    assert result.file_path is not None
    assert result.char_count == len("Fallback text.")


@pytest.mark.asyncio(loop_scope="function")
async def test_on_elevenlabs_error_updates_row_to_error_status(tmp_path):
    cfg = _make_config(tmp_path)
    summary = _make_summary()
    row = _make_audio_row(status="generating")

    call_results = [None, summary, row]
    saved_rows: list = []
    idx = 0

    async def _to_thread(fn):
        nonlocal idx
        # Capture save calls
        if hasattr(fn, "__self__") or (callable(fn) and not idx < len(call_results)):
            saved_rows.append(fn)
            return None
        result = call_results[idx]
        idx += 1
        return result

    mock_client = AsyncMock()
    mock_client.synthesize = AsyncMock(side_effect=ElevenLabsAPIError("boom", status_code=500))

    with patch("app.services.tts_service.ElevenLabsTTSClient", return_value=mock_client):
        service = TTSService(cfg)

    saves = []

    async def _to_thread2(fn):
        nonlocal idx
        if idx < len(call_results):
            result = call_results[idx]
            idx += 1
            return result
        # This is a row.save() call
        saves.append(fn)
        return None

    with patch("asyncio.to_thread", side_effect=_to_thread2):
        result = await service.generate_audio(1)

    assert result.status == "error"
    assert result.error is not None
    # Row status should have been set to error before save
    assert row.status == "error"


@pytest.mark.asyncio(loop_scope="function")
async def test_on_success_writes_mp3_and_updates_row(tmp_path):
    cfg = _make_config(tmp_path)
    summary = _make_summary()
    row = _make_audio_row(status="generating")

    audio_bytes = b"real_audio_data"

    call_results = [None, summary, row]
    idx = 0

    async def _to_thread(fn):
        nonlocal idx
        if idx < len(call_results):
            result = call_results[idx]
            idx += 1
            return result
        # row.save() calls — execute them to test file writing side effects
        if callable(fn):
            try:
                fn()
            except Exception:
                pass
        return None

    mock_client = AsyncMock()
    mock_client.synthesize = AsyncMock(return_value=audio_bytes)

    with patch("app.services.tts_service.ElevenLabsTTSClient", return_value=mock_client):
        service = TTSService(cfg)

    with patch("asyncio.to_thread", side_effect=_to_thread):
        result = await service.generate_audio(1)

    assert result.status == "completed"
    # File should have been written to storage path
    expected_file = tmp_path / "1.mp3"
    assert expected_file.exists()
    assert expected_file.read_bytes() == audio_bytes


def test_get_audio_status_returns_none_when_no_row():
    with patch("app.services.tts_service.AudioGeneration") as mock_ag:
        mock_ag.select.return_value.where.return_value.first.return_value = None
        result = TTSService.get_audio_status(42)
    assert result is None


def test_get_audio_status_returns_result_when_row_exists():
    row = _make_audio_row(
        status="completed", file_path="/data/audio/42.mp3", file_size_bytes=1024, char_count=200
    )
    with patch("app.services.tts_service.AudioGeneration") as mock_ag:
        mock_ag.select.return_value.where.return_value.first.return_value = row
        result = TTSService.get_audio_status(42)

    assert result is not None
    assert isinstance(result, AudioGenerationResult)
    assert result.status == "completed"
    assert result.file_path == "/data/audio/42.mp3"
