"""ZIP archive safety validation -- central-directory only, no decompression."""

from __future__ import annotations

import zipfile
from io import BytesIO

__all__ = ["ZipSafetyViolation", "validate_zip_safety"]


class ZipSafetyViolation(ValueError):
    """Raised when a ZIP archive fails a safety check."""


def validate_zip_safety(
    data: bytes,
    *,
    max_entries: int,
    max_compressed_bytes: int,
    max_decompressed_bytes: int,
    max_ratio: float,
) -> None:
    """Validate *data* as a safe ZIP archive using central-directory metadata only.

    No entry content is decompressed during validation.

    Raises ZipSafetyViolation with a descriptive message if any check fails.
    Raises ZipSafetyViolation (wrapping BadZipFile) for corrupt/invalid archives.
    """
    try:
        with zipfile.ZipFile(BytesIO(data), "r") as zf:
            entries = zf.infolist()
    except zipfile.BadZipFile as exc:
        raise ZipSafetyViolation(f"Invalid or corrupt ZIP archive: {exc}") from exc

    if not entries:
        raise ZipSafetyViolation("Archive contains no entries")

    if len(entries) > max_entries:
        raise ZipSafetyViolation(f"Archive has {len(entries)} entries; limit is {max_entries}")

    total_compressed = sum(e.compress_size for e in entries)
    if total_compressed > max_compressed_bytes:
        raise ZipSafetyViolation(
            f"Total compressed size {total_compressed} B exceeds limit {max_compressed_bytes} B"
        )

    total_decompressed = sum(e.file_size for e in entries)
    if total_decompressed > max_decompressed_bytes:
        raise ZipSafetyViolation(
            f"Total decompressed size {total_decompressed} B exceeds limit "
            f"{max_decompressed_bytes} B"
        )

    for entry in entries:
        normalized = entry.filename.replace("\\", "/")
        if normalized.startswith("/") or (len(normalized) >= 2 and normalized[1] == ":"):
            raise ZipSafetyViolation(
                f"Entry '{entry.filename}' has an absolute path (path traversal risk)"
            )
        if ".." in normalized.split("/"):
            raise ZipSafetyViolation(
                f"Entry '{entry.filename}' contains '..' component (path traversal risk)"
            )
        if entry.compress_size == 0 and entry.file_size > 0:
            raise ZipSafetyViolation(
                f"Entry '{entry.filename}' reports {entry.file_size} B uncompressed "
                "but 0 B compressed (suspicious metadata)"
            )
        ratio = entry.file_size / max(entry.compress_size, 1)
        if ratio > max_ratio:
            raise ZipSafetyViolation(
                f"Entry '{entry.filename}' compression ratio {ratio:.1f} exceeds "
                f"limit {max_ratio} (zip bomb guard)"
            )
