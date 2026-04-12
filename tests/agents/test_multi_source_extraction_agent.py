from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.multi_source_extraction_agent import (
    MultiSourceExtractionAgent,
    MultiSourceExtractionInput,
)
from app.application.dto.aggregation import (
    NormalizedSourceDocument,
    SourceMediaAsset,
    SourceMediaKind,
    SourceProvenance,
    SourceSubmission,
)
from app.domain.models.source import SourceKind
from app.infrastructure.persistence.sqlite.repositories.aggregation_session_repository import (
    SqliteAggregationSessionRepositoryAdapter,
)
from tests.helpers.aggregation_fixture_loader import load_aggregation_fixture
from tests.integration.helpers import temp_db


def _make_user_and_repo(db):
    from app.db.models import User

    user = User.create(
        telegram_user_id=123456789,
        username="bundle-user",
        is_owner=True,
    )
    repo = SqliteAggregationSessionRepositoryAdapter(db)
    return user, repo


def _make_forward_message_with_photo() -> SimpleNamespace:
    return SimpleNamespace(
        id=501,
        message_id=501,
        text=None,
        caption="Photo post caption",
        chat=SimpleNamespace(id=-100777),
        media_group_id=None,
        photo=[SimpleNamespace(file_id="photo-1", width=1280, height=720)],
        document=None,
        video=None,
        animation=None,
        forward_from_chat=SimpleNamespace(id=-10042, title="Forwarded Channel"),
        forward_from_message_id=88,
        forward_from=None,
        forward_sender_name=None,
    )


@pytest.mark.asyncio
async def test_multi_source_extraction_agent_returns_partial_success_for_mixed_bundle() -> None:
    with temp_db() as db:
        user, repo = _make_user_and_repo(db)

        content_extractor = MagicMock()

        async def _extract(
            url: str, correlation_id: str | None = None, request_id: int | None = None
        ):
            del correlation_id, request_id
            if "broken" in url:
                raise ValueError("Simulated extraction failure")
            if "threads.net" in url:
                return (
                    "Threads body",
                    "markdown",
                    {
                        "firecrawl_metadata": {"title": "Threads title"},
                        "detected_lang": "en",
                    },
                )
            return (
                "Tweet body",
                "twitter_graphql",
                {
                    "title": "Tweet title",
                    "source": "twitter",
                    "detected_lang": "en",
                },
            )

        content_extractor.extract_content_pure = AsyncMock(side_effect=_extract)
        agent = MultiSourceExtractionAgent(
            content_extractor=content_extractor,
            aggregation_session_repo=repo,
        )

        with (
            patch(
                "app.agents.multi_source_extraction_agent.record_aggregation_extraction"
            ) as extraction_metrics,
            patch(
                "app.agents.multi_source_extraction_agent.record_aggregation_bundle"
            ) as bundle_metrics,
        ):
            result = await agent.execute(
                MultiSourceExtractionInput(
                    correlation_id="agg-phase2-1",
                    user_id=user.telegram_user_id,
                    items=[
                        SourceSubmission.from_url("https://x.com/user/status/123"),
                        SourceSubmission.from_url("https://www.threads.net/@user/post/abc"),
                        SourceSubmission.from_url("https://example.com/broken"),
                    ],
                    metadata={"entrypoint": "test"},
                )
            )

        assert result.success is True
        assert result.output is not None
        assert result.output.status == "partial"
        assert result.output.successful_count == 2
        assert result.output.failed_count == 1
        assert [item.source_kind for item in result.output.items] == [
            SourceKind.X_POST,
            SourceKind.THREADS_POST,
            SourceKind.WEB_ARTICLE,
        ]
        assert result.output.items[0].normalized_document is not None
        assert result.output.items[1].normalized_document is not None
        assert result.output.items[2].failure is not None

        session = await repo.async_get_aggregation_session(result.output.session_id)
        assert session is not None
        assert session["status"] == "processing"
        assert session["successful_count"] == 2
        assert session["failed_count"] == 1
        assert session["progress_percent"] == 100
        assert session["started_at"] is not None
        assert session["completed_at"] is None
        assert extraction_metrics.call_count == 3
        bundle_metrics.assert_called_once()


@pytest.mark.asyncio
async def test_multi_source_extraction_agent_skips_duplicates_and_extracts_telegram_media() -> None:
    with temp_db() as db:
        user, repo = _make_user_and_repo(db)
        content_extractor = MagicMock()
        content_extractor.extract_content_pure = AsyncMock(
            return_value=(
                "Article body",
                "markdown",
                {"firecrawl_metadata": {"title": "Example article"}, "detected_lang": "en"},
            )
        )
        agent = MultiSourceExtractionAgent(
            content_extractor=content_extractor,
            aggregation_session_repo=repo,
        )

        message = _make_forward_message_with_photo()
        result = await agent.execute(
            MultiSourceExtractionInput(
                correlation_id="agg-phase2-2",
                user_id=user.telegram_user_id,
                items=[
                    SourceSubmission.from_url("https://example.com/article?utm_source=test"),
                    SourceSubmission.from_url("https://example.com/article"),
                    SourceSubmission.from_telegram_message(message),
                ],
            )
        )

        assert result.success is True
        assert result.output is not None
        assert result.output.status == "completed"
        assert result.output.successful_count == 2
        assert result.output.duplicate_count == 1
        assert content_extractor.extract_content_pure.await_count == 1

        duplicate_item = result.output.items[1]
        telegram_item = result.output.items[2]

        assert duplicate_item.status == "duplicate"
        assert duplicate_item.duplicate_of_item_id == result.output.items[0].item_id
        assert telegram_item.source_kind == SourceKind.TELEGRAM_POST_WITH_IMAGES
        assert telegram_item.normalized_document is not None
        assert telegram_item.normalized_document.media[0].url == "telegram://file/photo-1"
        assert telegram_item.normalized_document.title == "Forwarded Channel"


@pytest.mark.asyncio
async def test_multi_source_extraction_agent_preserves_platform_normalized_documents() -> None:
    with temp_db() as db:
        user, repo = _make_user_and_repo(db)
        content_extractor = MagicMock()
        platform_document = NormalizedSourceDocument(
            source_item_id="src_instagram",
            source_kind=SourceKind.INSTAGRAM_CAROUSEL,
            title="Carousel title",
            text="Carousel caption",
            detected_language="en",
            media=[
                SourceMediaAsset(
                    kind=SourceMediaKind.IMAGE,
                    url="https://cdn.example.com/slide-1.jpg",
                    position=0,
                ),
                SourceMediaAsset(
                    kind=SourceMediaKind.IMAGE,
                    url="https://cdn.example.com/slide-2.jpg",
                    position=1,
                ),
            ],
            provenance=SourceProvenance(
                source_item_id="src_instagram",
                source_kind=SourceKind.INSTAGRAM_CAROUSEL,
                original_value="https://www.instagram.com/p/DApost123/",
                normalized_value="https://www.instagram.com/p/DApost123",
                external_id="DApost123",
                request_id=None,
                extraction_source="markdown",
            ),
        )
        content_extractor.extract_content_pure = AsyncMock(
            return_value=(
                "ignored plain text",
                "markdown",
                {
                    "detected_lang": "en",
                    "normalized_source_document": platform_document.model_dump(mode="json"),
                },
            )
        )
        agent = MultiSourceExtractionAgent(
            content_extractor=content_extractor,
            aggregation_session_repo=repo,
        )

        result = await agent.execute(
            MultiSourceExtractionInput(
                correlation_id="agg-phase3-platform-doc",
                user_id=user.telegram_user_id,
                items=[SourceSubmission.from_url("https://www.instagram.com/p/DApost123/")],
            )
        )

        assert result.success is True
        assert result.output is not None
        assert result.output.items[0].source_kind == SourceKind.INSTAGRAM_CAROUSEL
        assert result.output.items[0].normalized_document is not None
        assert (
            result.output.items[0].normalized_document.source_kind == SourceKind.INSTAGRAM_CAROUSEL
        )
        assert len(result.output.items[0].normalized_document.media) == 2


@pytest.mark.asyncio
async def test_multi_source_extraction_agent_extracts_telegram_album_as_one_item() -> None:
    with temp_db() as db:
        user, repo = _make_user_and_repo(db)
        content_extractor = MagicMock()
        content_extractor.extract_content_pure = AsyncMock()
        agent = MultiSourceExtractionAgent(
            content_extractor=content_extractor,
            aggregation_session_repo=repo,
        )

        album_messages = [
            SimpleNamespace(
                id=601,
                message_id=601,
                text=None,
                caption="Album caption",
                chat=SimpleNamespace(id=-100777),
                media_group_id="album-1",
                photo=[SimpleNamespace(file_id="photo-1", width=1280, height=720)],
                document=None,
                video=None,
                animation=None,
                forward_from_chat=SimpleNamespace(id=-10042, title="Forwarded Channel"),
                forward_from_message_id=88,
                forward_from=None,
                forward_sender_name=None,
            ),
            SimpleNamespace(
                id=602,
                message_id=602,
                text=None,
                caption=None,
                chat=SimpleNamespace(id=-100777),
                media_group_id="album-1",
                photo=[SimpleNamespace(file_id="photo-2", width=1280, height=720)],
                document=None,
                video=None,
                animation=None,
                forward_from_chat=SimpleNamespace(id=-10042, title="Forwarded Channel"),
                forward_from_message_id=88,
                forward_from=None,
                forward_sender_name=None,
            ),
        ]

        result = await agent.execute(
            MultiSourceExtractionInput(
                correlation_id="agg-phase4-album",
                user_id=user.telegram_user_id,
                items=[SourceSubmission.from_telegram_messages(album_messages)],
            )
        )

        assert result.success is True
        assert result.output is not None
        assert result.output.items[0].source_kind == SourceKind.TELEGRAM_ALBUM
        assert result.output.items[0].normalized_document is not None
        assert len(result.output.items[0].normalized_document.media) == 2
        assert result.output.items[0].normalized_document.metadata["message_ids"] == [601, 602]


@pytest.mark.asyncio
async def test_multi_source_extraction_agent_handles_fixture_backed_all_supported_platforms_bundle() -> (
    None
):
    with temp_db() as db:
        user, repo = _make_user_and_repo(db)
        threads_fixture = load_aggregation_fixture("threads_post")
        instagram_fixture = load_aggregation_fixture("instagram_carousel")
        x_fixture = load_aggregation_fixture("x_media_post")
        youtube_fixture = load_aggregation_fixture("youtube_video")
        telegram_fixture = load_aggregation_fixture("telegram_post_with_images")
        instagram_document = NormalizedSourceDocument(
            source_item_id="src_instagram_carousel",
            source_kind=SourceKind.INSTAGRAM_CAROUSEL,
            title=instagram_fixture["metadata_json"]["title"],
            text=instagram_fixture["content_markdown"],
            detected_language="en",
            media=[
                SourceMediaAsset(
                    kind=SourceMediaKind.IMAGE,
                    url=image_url,
                    position=index,
                )
                for index, image_url in enumerate(instagram_fixture["metadata_json"]["images"])
            ],
            provenance=SourceProvenance(
                source_item_id="src_instagram_carousel",
                source_kind=SourceKind.INSTAGRAM_CAROUSEL,
                original_value="https://www.instagram.com/p/DApost123/",
                normalized_value="https://www.instagram.com/p/DApost123",
                external_id="DApost123",
                request_id=None,
                extraction_source="markdown",
            ),
        )

        content_extractor = MagicMock()

        async def _extract(
            url: str, correlation_id: str | None = None, request_id: int | None = None
        ) -> tuple[str, str, dict[str, object]]:
            del correlation_id, request_id
            if "threads.net" in url:
                return (
                    threads_fixture["content_markdown"],
                    "markdown",
                    {
                        "firecrawl_metadata": threads_fixture["metadata_json"],
                        "detected_lang": "en",
                    },
                )
            if "instagram.com" in url:
                return (
                    instagram_fixture["content_markdown"],
                    "markdown",
                    {
                        "detected_lang": "en",
                        "normalized_source_document": instagram_document.model_dump(mode="json"),
                    },
                )
            if "youtube.com" in url:
                return (
                    youtube_fixture["content_text"],
                    youtube_fixture["content_source"],
                    {
                        **youtube_fixture["metadata"],
                        "title": youtube_fixture["title"],
                        "detected_lang": youtube_fixture["detected_lang"],
                    },
                )
            if "example.com/article" in url:
                return (
                    "Generic article body with enough detail to represent the web article path.",
                    "markdown",
                    {
                        "firecrawl_metadata": {"title": "Generic web article"},
                        "detected_lang": "en",
                    },
                )
            return (
                x_fixture["content_text"],
                x_fixture["content_source"],
                {
                    **x_fixture["metadata"],
                    "title": x_fixture["title"],
                    "detected_lang": x_fixture["detected_lang"],
                },
            )

        content_extractor.extract_content_pure = AsyncMock(side_effect=_extract)
        agent = MultiSourceExtractionAgent(
            content_extractor=content_extractor,
            aggregation_session_repo=repo,
        )
        telegram_message = _make_forward_message_with_photo()
        telegram_message.caption = telegram_fixture["caption"]
        telegram_message.photo = [
            SimpleNamespace(
                file_id=telegram_fixture["photos"][0]["file_id"],
                width=telegram_fixture["photos"][0]["width"],
                height=telegram_fixture["photos"][0]["height"],
            )
        ]
        telegram_message.forward_from_chat = SimpleNamespace(
            id=telegram_fixture["forward_from_chat_id"],
            title=telegram_fixture["forward_from_chat_title"],
        )
        telegram_message.forward_from_message_id = telegram_fixture["forward_from_message_id"]

        result = await agent.execute(
            MultiSourceExtractionInput(
                correlation_id="agg-phase9-fixtures",
                user_id=user.telegram_user_id,
                items=[
                    SourceSubmission.from_url("https://x.com/user/status/123"),
                    SourceSubmission.from_url("https://www.threads.net/@user/post/abc"),
                    SourceSubmission.from_url("https://www.instagram.com/p/DApost123/"),
                    SourceSubmission.from_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
                    SourceSubmission.from_url("https://example.com/article"),
                    SourceSubmission.from_telegram_message(telegram_message),
                ],
            )
        )

        assert result.success is True
        assert result.output is not None
        assert [item.source_kind for item in result.output.items] == [
            SourceKind.X_POST,
            SourceKind.THREADS_POST,
            SourceKind.INSTAGRAM_CAROUSEL,
            SourceKind.YOUTUBE_VIDEO,
            SourceKind.WEB_ARTICLE,
            SourceKind.TELEGRAM_POST_WITH_IMAGES,
        ]
        assert result.output.successful_count == 6
        assert result.output.failed_count == 0
        assert result.output.items[2].normalized_document is not None
        assert len(result.output.items[2].normalized_document.media) == 2
        assert result.output.items[4].normalized_document is not None
        assert result.output.items[4].normalized_document.title == "Generic web article"
