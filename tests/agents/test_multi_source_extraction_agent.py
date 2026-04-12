from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

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

        result = await agent.execute(
            MultiSourceExtractionInput(
                correlation_id="agg-phase2-1",
                user_id=user.telegram_user_id,
                items=[
                    SourceSubmission.from_url("https://x.com/user/status/123"),
                    SourceSubmission.from_url("https://www.threads.net/@user/post/abc"),
                    SourceSubmission.from_url("https://example.com/broken"),
                ],
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
        assert session["status"] == "partial"
        assert session["successful_count"] == 2
        assert session["failed_count"] == 1


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
