from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

VALID_QUALITIES = {"240", "360", "480", "720", "1080", "1440", "2160"}


def build_ydl_opts(
    *,
    video_id: str,
    output_path: Path,
    preferred_quality: str,
    subtitle_languages: list[str],
    max_video_size_mb: int,
) -> dict[str, Any]:
    raw_quality = preferred_quality.rstrip("p")
    if raw_quality not in VALID_QUALITIES:
        logger.warning(
            "youtube_invalid_quality_fallback",
            extra={"configured": preferred_quality, "fallback": "1080"},
        )
        raw_quality = "1080"

    return {
        "format": (
            f"bestvideo[height<={raw_quality}][ext=mp4]+bestaudio[ext=m4a]/"
            f"best[height<={raw_quality}]"
        ),
        "outtmpl": str(output_path / f"{video_id}_%(title)s.%(ext)s"),
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": subtitle_languages,
        "subtitlesformat": "vtt",
        "writeinfojson": True,
        "writethumbnail": True,
        "prefer_ffmpeg": True,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": False,
        "ignoreerrors": False,
        "max_filesize": max_video_size_mb * 1024 * 1024,
    }


def download_video_sync(
    *,
    url: str,
    ydl_opts: dict[str, Any],
    subtitle_languages: list[str],
    correlation_id: str | None,
    extract_youtube_video_id: Callable[[str], str | None],
    yt_dlp_module: Any,
) -> dict[str, Any]:
    """Synchronous download using yt-dlp; designed to run in a thread."""
    video_id = extract_youtube_video_id(url)

    with yt_dlp_module.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
        except yt_dlp_module.utils.DownloadError as exc:
            error_msg = str(exc).lower()
            logger.error(
                "yt_dlp_extract_info_failed",
                extra={"url": url, "error": str(exc), "cid": correlation_id},
            )

            if "sign in to confirm your age" in error_msg or "age-restricted" in error_msg:
                raise ValueError(
                    "❌ This video is age-restricted and cannot be downloaded. "
                    "YouTube requires login/age verification for this content."
                ) from exc
            if "video is not available" in error_msg or "video unavailable" in error_msg:
                raise ValueError(
                    "❌ Video is not available. It may be private, deleted, or geo-blocked in your region."
                ) from exc
            if "private video" in error_msg:
                raise ValueError("❌ This video is private and cannot be accessed.") from exc
            if "members-only" in error_msg or "join this channel" in error_msg:
                raise ValueError(
                    "❌ This video is members-only content. YouTube Premium or channel membership required."
                ) from exc
            if "this live event will begin" in error_msg or "premieres in" in error_msg:
                raise ValueError(
                    "❌ This video is a scheduled premiere or upcoming live stream. "
                    "Please try again after it starts."
                ) from exc
            if "copyright" in error_msg:
                raise ValueError("❌ Video unavailable due to copyright restrictions.") from exc
            if "geo" in error_msg or "not available in your country" in error_msg:
                raise ValueError(
                    "❌ This video is geo-blocked and not available in your region."
                ) from exc
            raise ValueError(f"❌ Failed to extract video information: {str(exc)[:200]}") from exc
        except Exception as exc:
            logger.error(
                "yt_dlp_extract_info_failed",
                extra={"url": url, "error": str(exc), "cid": correlation_id},
            )
            raise ValueError(
                f"❌ Unexpected error extracting video info: {str(exc)[:200]}"
            ) from exc

        filesize = info.get("filesize") or info.get("filesize_approx", 0)
        max_size = int(ydl_opts.get("max_filesize") or 0)
        if max_size and filesize and filesize > max_size:
            raise ValueError(
                f"❌ Video too large: {filesize / 1024 / 1024:.1f}MB exceeds maximum allowed size "
                f"({max_size / 1024 / 1024:.0f}MB). Try a lower quality setting."
            )

        try:
            ydl.download([url])
        except yt_dlp_module.utils.DownloadError as exc:
            error_msg = str(exc).lower()
            logger.error(
                "yt_dlp_download_failed",
                extra={"url": url, "error": str(exc), "cid": correlation_id},
            )

            if "http error 429" in error_msg or "too many requests" in error_msg:
                raise ValueError(
                    "❌ YouTube rate limit exceeded. Please try again in a few minutes."
                ) from exc
            if "http error 403" in error_msg:
                raise ValueError(
                    "❌ Access forbidden. Video may require authentication or is geo-blocked."
                ) from exc
            if "http error 404" in error_msg:
                raise ValueError(
                    "❌ Video not found. It may have been deleted or the URL is incorrect."
                ) from exc
            if "timed out" in error_msg or "timeout" in error_msg:
                raise ValueError(
                    "❌ Download timed out. Please try again or check your internet connection."
                ) from exc
            if "connection" in error_msg:
                raise ValueError(
                    "❌ Network connection error. Please check your internet connection and try again."
                ) from exc
            raise ValueError(f"❌ Download failed: {str(exc)[:200]}") from exc
        except Exception as exc:
            logger.error(
                "yt_dlp_download_failed",
                extra={"url": url, "error": str(exc), "cid": correlation_id},
            )
            raise ValueError(f"❌ Unexpected download error: {str(exc)[:200]}") from exc

        video_file = ydl.prepare_filename(info)
        video_path = Path(video_file)

        subtitle_file = None
        for lang in subtitle_languages:
            sub_path = video_path.with_suffix(f".{lang}.vtt")
            if sub_path.exists():
                subtitle_file = str(sub_path)
                break

        for vtt_path in video_path.parent.glob(f"{video_id}_*.vtt"):
            if subtitle_file and str(vtt_path) == subtitle_file:
                continue
            try:
                vtt_path.unlink()
            except OSError:
                pass

        metadata_file = video_path.with_suffix(".info.json")
        thumbnail_file = None
        for ext in [".jpg", ".png", ".webp"]:
            thumb_path = video_path.with_suffix(ext)
            if thumb_path.exists():
                thumbnail_file = str(thumb_path)
                break

        if metadata_file.exists():
            try:
                metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(
                    "youtube_metadata_file_corrupt",
                    extra={"path": str(metadata_file), "error": str(exc)},
                )
                metadata = info
        else:
            metadata = info

        actual_size = video_path.stat().st_size if video_path.exists() else 0
        if actual_size == 0:
            raise ValueError(
                "Video file missing or empty after download. "
                "ffmpeg may have failed to merge video/audio streams."
            )

        uploader = metadata.get("uploader")
        return {
            "video_file_path": str(video_file),
            "subtitle_file_path": subtitle_file,
            "metadata_file_path": str(metadata_file) if metadata_file.exists() else None,
            "thumbnail_file_path": thumbnail_file,
            "video_id": metadata.get("id", video_id),
            "title": metadata.get("title", "Unknown"),
            "channel": uploader if uploader is not None else metadata.get("channel", "Unknown"),
            "channel_id": metadata.get("channel_id"),
            "duration": metadata.get("duration"),
            "resolution": f"{metadata.get('height', '?')}p",
            "file_size": actual_size,
            "upload_date": metadata.get("upload_date"),
            "view_count": metadata.get("view_count"),
            "like_count": metadata.get("like_count"),
            "vcodec": metadata.get("vcodec"),
            "acodec": metadata.get("acodec"),
            "format_id": metadata.get("format_id"),
        }
