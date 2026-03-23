from __future__ import annotations

import re

from app.core.logging_utils import get_logger

logger = get_logger(__name__)

_YOUTUBE_PATTERNS = [
    re.compile(
        r"(?:https?://)?(?:(?:www|m)\.)?youtube\.com/watch\?(?:[^&]+&)*v=([a-zA-Z0-9_-]{11})",
        re.IGNORECASE,
    ),
    re.compile(r"(?:https?://)?youtu\.be/([a-zA-Z0-9_-]{11})", re.IGNORECASE),
    re.compile(
        r"(?:https?://)?(?:www\.)?youtube(?:-nocookie)?\.com/embed/([a-zA-Z0-9_-]{11})",
        re.IGNORECASE,
    ),
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/v/([a-zA-Z0-9_-]{11})", re.IGNORECASE),
    re.compile(
        r"(?:https?://)?(?:(?:www|m)\.)?youtube\.com/shorts/([a-zA-Z0-9_-]{11})",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:https?://)?music\.youtube\.com/watch\?(?:[^&]+&)*v=([a-zA-Z0-9_-]{11})",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:https?://)?(?:(?:www|m)\.)?youtube\.com/live/([a-zA-Z0-9_-]{11})",
        re.IGNORECASE,
    ),
]


def is_youtube_url(url: str) -> bool:
    """Check if URL is a YouTube video."""
    if not url or not isinstance(url, str):
        return False

    try:
        return any(pattern.search(url) for pattern in _YOUTUBE_PATTERNS)
    except Exception as exc:
        logger.exception("is_youtube_url_failed", extra={"error": str(exc), "url": url[:100]})
        return False


def extract_youtube_video_id(url: str) -> str | None:
    """Extract YouTube video ID from URL."""
    if not url or not isinstance(url, str):
        return None

    try:
        for pattern in _YOUTUBE_PATTERNS:
            match = pattern.search(url)
            if match:
                video_id = match.group(1)
                if len(video_id) == 11 and re.match(r"^[a-zA-Z0-9_-]{11}$", video_id):
                    logger.debug(
                        "extract_youtube_video_id",
                        extra={"url": url[:100], "video_id": video_id},
                    )
                    return video_id

        logger.debug("extract_youtube_video_id_not_found", extra={"url": url[:100]})
        return None
    except Exception as exc:
        logger.exception(
            "extract_youtube_video_id_failed",
            extra={"error": str(exc), "url": url[:100]},
        )
        return None


__all__ = [
    "extract_youtube_video_id",
    "is_youtube_url",
]
