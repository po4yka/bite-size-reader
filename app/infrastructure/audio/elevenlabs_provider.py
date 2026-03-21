"""Application-port adapter for ElevenLabs TTS."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.adapters.elevenlabs.tts_client import ElevenLabsTTSClient

if TYPE_CHECKING:
    from app.config.tts import ElevenLabsConfig


class ElevenLabsTTSProviderAdapter:
    """Wrap the ElevenLabs client behind the application TTS provider port."""

    def __init__(self, config: ElevenLabsConfig) -> None:
        self.voice_id = config.voice_id
        self.model_name = config.model
        self.max_chars_per_request = config.max_chars_per_request
        self._client = ElevenLabsTTSClient(config)

    async def synthesize(self, text: str, *, use_long_form: bool = False) -> bytes:
        if use_long_form:
            return await self._client.synthesize_long(text)
        return await self._client.synthesize(text)

    async def close(self) -> None:
        await self._client.close()
