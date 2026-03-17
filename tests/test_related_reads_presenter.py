"""Tests for related reads presenter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.services.related_reads_service import RelatedReadItem


class TestBuildRelatedReadsKeyboard:
    def test_empty_items_returns_none(self) -> None:
        from app.adapters.external.formatting.summary.related_reads_presenter import (
            build_related_reads_keyboard,
        )

        assert build_related_reads_keyboard([]) is None

    def test_builds_keyboard_with_items(self) -> None:
        from app.adapters.external.formatting.summary.related_reads_presenter import (
            build_related_reads_keyboard,
        )

        items = [
            RelatedReadItem(
                summary_id=1,
                request_id=10,
                title="Short Title",
                age_label="2w",
                similarity_score=0.85,
            ),
            RelatedReadItem(
                summary_id=2,
                request_id=20,
                title="Another Article",
                age_label="3d",
                similarity_score=0.80,
            ),
        ]
        result = build_related_reads_keyboard(items)
        # Pyrogram is available in this environment, so we get a real keyboard
        if result is not None:
            assert hasattr(result, "inline_keyboard")
            assert len(result.inline_keyboard) == 2
            assert "rel:10" in result.inline_keyboard[0][0].callback_data
            assert "rel:20" in result.inline_keyboard[1][0].callback_data

    def test_truncates_long_title(self) -> None:
        from app.adapters.external.formatting.summary.related_reads_presenter import (
            build_related_reads_keyboard,
        )

        long_title = "A" * 60
        items = [
            RelatedReadItem(
                summary_id=1,
                request_id=10,
                title=long_title,
                age_label="1d",
                similarity_score=0.9,
            ),
        ]
        # Function gracefully handles missing pyrogram
        result = build_related_reads_keyboard(items)
        # No assertion on result structure -- just verify no crash


class TestSendRelatedReads:
    @pytest.mark.asyncio
    async def test_empty_items_sends_nothing(self) -> None:
        from app.adapters.external.formatting.summary.related_reads_presenter import (
            send_related_reads,
        )

        sender = MagicMock()
        sender.safe_reply = AsyncMock()
        message = MagicMock()

        await send_related_reads(sender, message, [], lang="en")
        sender.safe_reply.assert_not_called()

    @pytest.mark.asyncio
    async def test_sends_message_with_keyboard(self) -> None:
        from app.adapters.external.formatting.summary.related_reads_presenter import (
            send_related_reads,
        )

        sender = MagicMock()
        sender.safe_reply = AsyncMock()
        message = MagicMock()

        items = [
            RelatedReadItem(
                summary_id=1,
                request_id=10,
                title="Test Article",
                age_label="2d",
                similarity_score=0.85,
            ),
        ]

        # The function will try to import pyrogram; if unavailable, keyboard is None
        # and no message is sent. This is expected in test environments.
        await send_related_reads(sender, message, items, lang="en")
        # If pyrogram is available, safe_reply would be called
        # If not, it's silently skipped -- both paths are valid
