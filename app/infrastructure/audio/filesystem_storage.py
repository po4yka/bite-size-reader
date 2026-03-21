"""Filesystem-backed audio storage adapter."""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.application.dto.audio_generation import StoredAudioFileDTO


class FileSystemAudioStorageAdapter:
    """Persist generated MP3 files on the local filesystem."""

    def __init__(self, storage_path: str) -> None:
        self._storage_dir = Path(storage_path)

    async def save_audio(self, summary_id: int, audio_bytes: bytes) -> StoredAudioFileDTO:
        def _write() -> StoredAudioFileDTO:
            self._storage_dir.mkdir(parents=True, exist_ok=True)
            file_path = self._storage_dir / f"{summary_id}.mp3"
            file_path.write_bytes(audio_bytes)
            return StoredAudioFileDTO(
                file_path=str(file_path),
                file_size_bytes=len(audio_bytes),
            )

        return await asyncio.to_thread(_write)
