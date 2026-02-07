from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, cast

from app.core.backoff import sleep_backoff

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

_TRANSCRIPT_MAX_RETRIES = 3


def format_transcript(
    transcript_data: list[dict],
    *,
    max_chars: int,
    log: logging.Logger | None = None,
) -> str:
    """Join transcript segments into a single text block, de-duping whitespace."""
    lines: list[str] = []
    for entry in transcript_data:
        text = entry.get("text", "").strip()
        if text:
            lines.append(text)

    transcript = " ".join(lines)
    result = " ".join(transcript.split())
    if len(result) > max_chars:
        (log or logger).warning(
            "youtube_transcript_truncated",
            extra={"original_length": len(result), "truncated_to": max_chars},
        )
        result = result[:max_chars]
    return result


async def extract_transcript_via_api(
    *,
    video_id: str,
    preferred_langs: list[str],
    correlation_id: str | None,
    youtube_transcript_api: Any,
    no_transcript_found_exc: type[Exception],
    transcripts_disabled_exc: type[Exception],
    video_unavailable_exc: type[Exception],
    raise_if_cancelled: Callable[[BaseException], None],
    max_transcript_chars: int,
    log: logging.Logger | None = None,
) -> tuple[str, str, bool, str]:
    """Extract transcript using youtube-transcript-api with a light retry."""
    last_error: Exception | None = None
    logger_ = log or logger

    for attempt in range(_TRANSCRIPT_MAX_RETRIES):
        try:
            transcript_list = await asyncio.wait_for(
                asyncio.to_thread(
                    cast("Any", youtube_transcript_api).list_transcripts,
                    video_id,
                ),
                timeout=30.0,
            )

            transcript = None
            auto_generated = False
            selected_lang = "en"

            # Try manually created transcripts first
            try:
                for lang in preferred_langs:
                    try:
                        transcript = transcript_list.find_transcript([lang])
                        selected_lang = lang
                        auto_generated = False
                        logger_.info(
                            "youtube_transcript_manual_found",
                            extra={"video_id": video_id, "language": lang, "cid": correlation_id},
                        )
                        break
                    except no_transcript_found_exc:
                        continue
            except (transcripts_disabled_exc, video_unavailable_exc):
                raise
            except Exception as exc:
                logger_.warning(
                    "youtube_transcript_manual_search_error",
                    extra={
                        "video_id": video_id,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                        "cid": correlation_id,
                    },
                )

            # Fallback to auto-generated if no manual transcript found
            if not transcript:
                try:
                    transcript = transcript_list.find_generated_transcript(preferred_langs)
                    selected_lang = transcript.language_code
                    auto_generated = True
                    logger_.info(
                        "youtube_transcript_auto_found",
                        extra={
                            "video_id": video_id,
                            "language": selected_lang,
                            "cid": correlation_id,
                        },
                    )
                except no_transcript_found_exc:
                    logger_.warning(
                        "youtube_transcript_not_found",
                        extra={"video_id": video_id, "cid": correlation_id},
                    )
                    return "", "en", False, "youtube-transcript-api"

            transcript_data = await asyncio.wait_for(
                asyncio.to_thread(transcript.fetch),
                timeout=30.0,
            )

            transcript_text = format_transcript(
                transcript_data, max_chars=max_transcript_chars, log=logger_
            )

            logger_.info(
                "youtube_transcript_extracted",
                extra={
                    "video_id": video_id,
                    "language": selected_lang,
                    "auto_generated": auto_generated,
                    "length": len(transcript_text),
                    "cid": correlation_id,
                },
            )
            return transcript_text, selected_lang, auto_generated, "youtube-transcript-api"

        except transcripts_disabled_exc as exc:
            logger_.warning(
                "youtube_transcript_disabled",
                extra={"video_id": video_id, "error": str(exc), "cid": correlation_id},
            )
            logger_.info(
                "youtube_continuing_without_transcript",
                extra={"video_id": video_id, "cid": correlation_id},
            )
            return "", "en", False, "youtube-transcript-api"

        except video_unavailable_exc as exc:
            logger_.error(
                "youtube_transcript_video_unavailable",
                extra={"video_id": video_id, "error": str(exc), "cid": correlation_id},
            )
            raise ValueError(
                "❌ Video is unavailable or does not exist. The video may have been deleted or made private."
            ) from exc

        except Exception as exc:
            raise_if_cancelled(exc)
            last_error = exc
            logger_.warning(
                "youtube_transcript_extraction_failed",
                extra={
                    "video_id": video_id,
                    "error": str(exc),
                    "attempt": attempt + 1,
                    "cid": correlation_id,
                },
            )
            if attempt < _TRANSCRIPT_MAX_RETRIES - 1:
                await sleep_backoff(attempt, backoff_base=1.0, max_delay=10.0)
                continue
            return "", "en", False, "youtube-transcript-api"

    logger_.warning(
        "youtube_transcript_extraction_exhausted",
        extra={"video_id": video_id, "error": str(last_error), "cid": correlation_id},
    )
    return "", "en", False, "youtube-transcript-api"
