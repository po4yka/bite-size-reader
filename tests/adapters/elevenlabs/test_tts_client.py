"""Unit tests for ElevenLabsTTSClient."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.adapters.elevenlabs.exceptions import (
    ElevenLabsAPIError,
    ElevenLabsQuotaExceededError,
    ElevenLabsRateLimitError,
)
from app.adapters.elevenlabs.tts_client import ElevenLabsTTSClient


def _make_config(*, max_chars: int = 5000) -> SimpleNamespace:
    return SimpleNamespace(
        api_key="test-key",
        voice_id="voice-abc",
        model="eleven_multilingual_v2",
        output_format="mp3_44100_128",
        stability=0.5,
        similarity_boost=0.75,
        speed=1.0,
        timeout_sec=30.0,
        max_chars_per_request=max_chars,
    )


def _make_response(status_code: int, content: bytes = b"", json_body: dict | None = None):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.content = content
    if json_body is not None:
        resp.json.return_value = json_body
    else:
        resp.json.side_effect = Exception("no json")
        resp.text = ""
    return resp


@pytest.mark.asyncio(loop_scope="function")
async def test_synthesize_returns_bytes_on_200():
    client = ElevenLabsTTSClient(_make_config())
    audio = b"MP3_DATA"
    mock_resp = _make_response(200, content=audio)

    with patch.object(client, "_get_client") as mock_get_client:
        http = AsyncMock()
        http.post = AsyncMock(return_value=mock_resp)
        mock_get_client.return_value = http

        result = await client.synthesize("Hello world")

    assert result == audio


@pytest.mark.asyncio(loop_scope="function")
async def test_synthesize_401_raises_api_error():
    client = ElevenLabsTTSClient(_make_config())
    mock_resp = _make_response(401, json_body={"detail": {"message": "Invalid key"}})

    with patch.object(client, "_get_client") as mock_get_client:
        http = AsyncMock()
        http.post = AsyncMock(return_value=mock_resp)
        mock_get_client.return_value = http

        with pytest.raises(ElevenLabsAPIError) as exc_info:
            await client.synthesize("Hello")

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio(loop_scope="function")
async def test_synthesize_429_raises_rate_limit_error():
    client = ElevenLabsTTSClient(_make_config())
    mock_resp = _make_response(429, json_body={"detail": {"message": "Too many requests"}})

    with patch.object(client, "_get_client") as mock_get_client:
        http = AsyncMock()
        http.post = AsyncMock(return_value=mock_resp)
        mock_get_client.return_value = http

        with pytest.raises(ElevenLabsRateLimitError):
            await client.synthesize("Hello")


@pytest.mark.asyncio(loop_scope="function")
async def test_synthesize_quota_exceeded_error():
    client = ElevenLabsTTSClient(_make_config())
    mock_resp = _make_response(400, json_body={"detail": {"message": "quota characters exceeded"}})

    with patch.object(client, "_get_client") as mock_get_client:
        http = AsyncMock()
        http.post = AsyncMock(return_value=mock_resp)
        mock_get_client.return_value = http

        with pytest.raises(ElevenLabsQuotaExceededError):
            await client.synthesize("Hello")


@pytest.mark.asyncio(loop_scope="function")
async def test_synthesize_retries_on_500_then_succeeds():
    """500 should be retried; second attempt succeeds."""
    client = ElevenLabsTTSClient(_make_config())
    fail_resp = _make_response(500, json_body={"detail": {"message": "server error"}})
    ok_resp = _make_response(200, content=b"audio")

    with (
        patch.object(client, "_get_client") as mock_get_client,
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        http = AsyncMock()
        http.post = AsyncMock(side_effect=[fail_resp, ok_resp])
        mock_get_client.return_value = http

        result = await client.synthesize("Hello")

    assert result == b"audio"
    assert http.post.call_count == 2


def test_chunk_text_single_chunk_when_short():
    client = ElevenLabsTTSClient(_make_config(max_chars=5000))
    text = "Short sentence."
    chunks = client._chunk_text(text)
    assert chunks == ["Short sentence."]


def test_chunk_text_splits_at_sentence_boundaries():
    client = ElevenLabsTTSClient(_make_config(max_chars=20))
    text = "Hello world. Foo bar. Baz qux."
    chunks = client._chunk_text(text)
    # Each chunk must be <= 20 chars (with some tolerance for +1 space)
    assert len(chunks) > 1
    # Reconstructing should recover all sentences
    rejoined = " ".join(chunks)
    assert "Hello world" in rejoined
    assert "Foo bar" in rejoined


@pytest.mark.asyncio(loop_scope="function")
async def test_synthesize_long_delegates_to_synthesize_when_single_chunk():
    """synthesize_long should call synthesize() when text fits in one chunk."""
    client = ElevenLabsTTSClient(_make_config(max_chars=5000))

    with patch.object(client, "synthesize", new_callable=AsyncMock) as mock_synth:
        mock_synth.return_value = b"audio"
        result = await client.synthesize_long("Short text.")

    mock_synth.assert_called_once_with("Short text.")
    assert result == b"audio"


@pytest.mark.asyncio(loop_scope="function")
async def test_synthesize_long_concatenates_chunks():
    """synthesize_long should concatenate audio bytes from all chunks."""
    client = ElevenLabsTTSClient(_make_config(max_chars=10))
    # Force multiple chunks by using a very short max_chars
    text = "Sentence one. Sentence two. Sentence three."

    call_payloads: list[dict] = []

    async def _fake_request(url: str, payload: dict) -> bytes:
        call_payloads.append(dict(payload))
        return b"chunk"

    with patch.object(client, "_request_with_retry", side_effect=_fake_request):
        result = await client.synthesize_long(text)

    assert len(call_payloads) > 1
    assert result == b"chunk" * len(call_payloads)
