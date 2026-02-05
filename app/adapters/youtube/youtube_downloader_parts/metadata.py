from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

_YOUTUBE_PREAMBLE = (
    "[Source: YouTube video transcript. "
    "Summarize this as video content — "
    "use watch time instead of reading time, "
    "and set source_type to an appropriate value for video content.]"
)


def format_duration(duration: int | None) -> str:
    if duration is None:
        return ""
    minutes, seconds = divmod(int(duration), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"Duration: {hours}h {minutes}m {seconds}s"
    if minutes:
        return f"Duration: {minutes}m {seconds}s"
    return f"Duration: {seconds}s"


def format_metadata_header(metadata: Mapping[str, Any]) -> str:
    title = metadata.get("title")
    channel = metadata.get("channel")
    duration = metadata.get("duration")
    resolution = metadata.get("resolution")

    parts: list[str] = []
    if title:
        parts.append(f"Title: {title}")
    if channel:
        parts.append(f"Channel: {channel}")
    if duration:
        parts.append(format_duration(duration))
    if resolution:
        parts.append(f"Resolution: {resolution}")

    return " | ".join(parts)


def combine_metadata_and_transcript(metadata: Mapping[str, Any], transcript_text: str) -> str:
    header = format_metadata_header(metadata)
    parts: list[str] = [_YOUTUBE_PREAMBLE]
    if header:
        parts.append(header)
    if transcript_text:
        parts.append(transcript_text)
    return "\n\n".join(parts)
