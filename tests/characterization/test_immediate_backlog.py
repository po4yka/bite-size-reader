from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.youtube.youtube_downloader import YouTubeDownloader
from app.application.use_cases.get_unread_summaries import (
    GetUnreadSummariesQuery,
    GetUnreadSummariesUseCase,
)
from app.application.use_cases.mark_summary_as_read import (
    MarkSummaryAsReadCommand,
    MarkSummaryAsReadUseCase,
)
from app.application.use_cases.mark_summary_as_unread import (
    MarkSummaryAsUnreadCommand,
    MarkSummaryAsUnreadUseCase,
)
from tests.conftest import make_test_app_config
from tests.test_commands import BotSpy, FakeMessage

pytest.importorskip("grpc", reason="grpcio not installed")

from app.grpc.client import ProcessingClient
from app.protos import processing_pb2

# Cast to Any so mypy doesn't complain about dynamically-generated protobuf attrs
_pb2: Any = processing_pb2


async def _async_generator(items):
    for item in items:
        yield item


@pytest.mark.asyncio
async def test_characterization_summary_command_happy_path_preserved() -> None:
    """Lock current /summarize command behavior for a single URL."""
    cfg = make_test_app_config(db_path=":memory:", allowed_user_ids=(1, 42))

    from app.adapters import telegram_bot as tbmod

    tbmod.Client = object
    tbmod.filters = None

    from unittest.mock import patch

    with patch("app.adapters.openrouter.openrouter_client.OpenRouterClient") as mock_openrouter:
        mock_openrouter.return_value = AsyncMock()
        bot = BotSpy(cfg=cfg, db=MagicMock())

    url = "https://example.com/characterization"
    msg = FakeMessage(f"/summarize {url}")

    await bot._on_message(msg)

    assert url in bot.seen_urls
    assert any(url in reply for reply in msg._replies)


@pytest.mark.asyncio
async def test_characterization_youtube_uses_vtt_fallback_when_api_transcript_empty(
    tmp_path,
) -> None:
    """Lock fallback behavior: empty API transcript should use downloaded VTT subtitles."""
    cfg = MagicMock()
    cfg.youtube.storage_path = str(tmp_path / "videos")
    cfg.youtube.max_video_size_mb = 500
    cfg.youtube.max_storage_gb = 100
    cfg.youtube.preferred_quality = "1080p"
    cfg.youtube.subtitle_languages = ["en"]
    cfg.youtube.auto_cleanup_enabled = False
    cfg.youtube.cleanup_after_days = 30

    rf = MagicMock()
    rf.sender.send_message_draft = AsyncMock()
    rf.sender.safe_reply = AsyncMock()
    rf.notifications.send_youtube_download_notification = AsyncMock()
    rf.notifications.send_youtube_download_complete_notification = AsyncMock()

    downloader: Any = YouTubeDownloader(
        cfg=cfg, db=MagicMock(), response_formatter=rf, audit_func=lambda *_a, **_k: None
    )

    downloader._check_storage_limits = AsyncMock()
    downloader.request_repo = MagicMock()
    downloader.video_repo = MagicMock()

    downloader.request_repo.async_get_request_by_dedupe_hash = AsyncMock(return_value=None)
    downloader.video_repo.async_get_video_download_by_request = AsyncMock(return_value=None)
    downloader.video_repo.async_create_video_download = AsyncMock(return_value=900)
    downloader.video_repo.async_update_video_download_status = AsyncMock()
    downloader.video_repo.async_update_video_download = AsyncMock()
    downloader.request_repo.async_update_request_status = AsyncMock()
    downloader.request_repo.async_update_request_lang_detected = AsyncMock()
    downloader._create_video_request = AsyncMock(return_value=500)

    downloader._extract_transcript_api = AsyncMock(return_value=("", "", False, "api"))
    downloader._download_video_sync = MagicMock(
        return_value={
            "title": "Example video",
            "channel": "Channel",
            "channel_id": "ch-1",
            "duration": 123,
            "upload_date": "20260101",
            "view_count": 1000,
            "like_count": 100,
            "resolution": "1080p",
            "file_size": 1024 * 1024,
            "vcodec": "h264",
            "acodec": "aac",
            "format_id": "137+140",
            "subtitle_file_path": str(tmp_path / "captions.en.vtt"),
        }
    )
    downloader._load_transcript_from_vtt = MagicMock(return_value=("vtt transcript body", "en"))

    (
        req_id,
        combined_text,
        transcript_source,
        detected_lang,
        _metadata,
    ) = await downloader.download_and_extract(
        message=MagicMock(),
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        silent=True,
    )

    assert req_id == 500
    assert transcript_source == "vtt"
    assert detected_lang == "en"
    assert "vtt transcript body" in combined_text
    downloader.video_repo.async_update_video_download.assert_awaited_once()


@pytest.mark.asyncio
async def test_characterization_unread_read_unread_transition_with_topic_filter() -> None:
    """Lock unread filtering and read-state transitions around topic-like filtering."""

    class InMemorySummaryRepo:
        def __init__(self) -> None:
            self.rows = {
                1: {
                    "id": 1,
                    "request_id": 10,
                    "lang": "en",
                    "json_payload": {
                        "title": "Rust migration notes",
                        "topic_tags": ["rust"],
                        "tldr": "r",
                        "summary_250": "rust",
                        "key_ideas": ["idea"],
                    },
                    "is_read": False,
                    "version": 1,
                },
                2: {
                    "id": 2,
                    "request_id": 11,
                    "lang": "en",
                    "json_payload": {
                        "title": "Python release notes",
                        "topic_tags": ["python"],
                        "tldr": "p",
                        "summary_250": "python",
                        "key_ideas": ["idea"],
                    },
                    "is_read": False,
                    "version": 1,
                },
            }

        async def async_get_unread_summaries(self, uid, cid, limit=10, topic=None):
            _ = (uid, cid)
            unread = [v for v in self.rows.values() if not v["is_read"]]
            if topic:
                t = topic.casefold()
                unread = [r for r in unread if t in str(r["json_payload"]).casefold()]
            return unread[:limit]

        async def async_get_summary_by_id(self, summary_id: int):
            return self.rows.get(summary_id)

        async def async_mark_summary_as_read(self, summary_id: int):
            self.rows[summary_id]["is_read"] = True

        async def async_mark_summary_as_unread(self, summary_id: int):
            self.rows[summary_id]["is_read"] = False

        def to_domain_model(self, db_summary):
            from datetime import datetime

            from app.domain.models.summary import Summary

            return Summary(
                id=db_summary["id"],
                request_id=db_summary["request_id"],
                content=db_summary["json_payload"],
                language=db_summary["lang"],
                version=db_summary["version"],
                is_read=db_summary["is_read"],
                created_at=datetime.utcnow(),
            )

    repo: Any = InMemorySummaryRepo()
    unread_use_case = GetUnreadSummariesUseCase(repo)
    mark_read = MarkSummaryAsReadUseCase(repo)
    mark_unread = MarkSummaryAsUnreadUseCase(repo)

    rust_only = await unread_use_case.execute(
        GetUnreadSummariesQuery(user_id=1, chat_id=1, topic="rust")
    )
    assert [s.id for s in rust_only] == [1]

    await mark_read.execute(MarkSummaryAsReadCommand(summary_id=1, user_id=1))
    rust_after_read = await unread_use_case.execute(
        GetUnreadSummariesQuery(user_id=1, chat_id=1, topic="rust")
    )
    assert rust_after_read == []

    await mark_unread.execute(MarkSummaryAsUnreadCommand(summary_id=1, user_id=1))
    rust_after_unread = await unread_use_case.execute(
        GetUnreadSummariesQuery(user_id=1, chat_id=1, topic="rust")
    )
    assert [s.id for s in rust_after_unread] == [1]


@pytest.mark.asyncio
async def test_characterization_grpc_submit_url_stream_order_and_terminal_state() -> None:
    """Lock stream contract: queued -> processing -> done with terminal summary id."""
    from unittest.mock import AsyncMock, MagicMock, patch

    updates = [
        _pb2.ProcessingUpdate(
            request_id=101,
            status=_pb2.ProcessingStatus.ProcessingStatus_PENDING,
            stage=_pb2.ProcessingStage.ProcessingStage_QUEUED,
            message="queued",
            progress=0.0,
        ),
        _pb2.ProcessingUpdate(
            request_id=101,
            status=_pb2.ProcessingStatus.ProcessingStatus_PROCESSING,
            stage=_pb2.ProcessingStage.ProcessingStage_EXTRACTION,
            message="extracting",
            progress=0.3,
        ),
        _pb2.ProcessingUpdate(
            request_id=101,
            status=_pb2.ProcessingStatus.ProcessingStatus_COMPLETED,
            stage=_pb2.ProcessingStage.ProcessingStage_DONE,
            message="done",
            progress=1.0,
            summary_id=777,
        ),
    ]

    mock_channel = MagicMock()
    mock_channel.channel_ready = AsyncMock()
    mock_channel.close = AsyncMock()

    mock_stub = MagicMock()
    mock_stub.SubmitUrl = MagicMock(return_value=_async_generator(updates))

    with (
        patch("grpc.aio.insecure_channel", return_value=mock_channel),
        patch("app.grpc.client.processing_pb2_grpc.ProcessingServiceStub", return_value=mock_stub),
    ):
        client = ProcessingClient("localhost:50051")
        await client.connect()

        received = []
        async for u in client.submit_url("https://example.com/article"):
            received.append(u)

        assert [u.status for u in received] == ["PENDING", "PROCESSING", "COMPLETED"]
        assert received[-1].summary_id == 777
