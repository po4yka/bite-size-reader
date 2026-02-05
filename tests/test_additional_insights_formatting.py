"""Tests for Additional Research Highlights formatting."""

from __future__ import annotations

import types
import unittest
from unittest.mock import AsyncMock, MagicMock


class _StubTextProcessor:
    def sanitize_summary_text(self, text: str) -> str:
        return text.strip()

    def linkify_urls(self, text: str) -> str:
        return text

    send_long_text = AsyncMock()


class TestAdditionalInsightsFormatting(unittest.IsolatedAsyncioTestCase):
    async def test_insights_sent_as_single_long_text_call(self) -> None:
        from app.adapters.external.formatting.summary_presenter import SummaryPresenterImpl

        response_sender = MagicMock()
        response_sender.safe_reply = AsyncMock()

        text_processor = _StubTextProcessor()
        text_processor.send_long_text = AsyncMock()

        presenter = SummaryPresenterImpl(
            response_sender=response_sender,
            text_processor=text_processor,  # type: ignore[arg-type]
            data_formatter=MagicMock(),
            verbosity_resolver=None,
            progress_tracker=None,
        )

        insights = {
            "topic_overview": "A brief overview.",
            "new_facts": [
                {
                    "fact": "Fact one.",
                    "why_it_matters": "Because.",
                    "source_hint": "https://example.com",
                    "confidence": 0.9,
                }
            ],
            "open_questions": ["What next?"],
            "suggested_sources": ["https://example.com/source"],
            "expansion_topics": ["Deeper topic"],
            "next_exploration": ["Step 1"],
            "caution": "Be careful.",
        }

        message = types.SimpleNamespace(chat=types.SimpleNamespace(id=1), id=10)

        await presenter.send_additional_insights_message(
            message, insights, correlation_id="cid-123"
        )

        text_processor.send_long_text.assert_awaited_once()
        sent_text = text_processor.send_long_text.call_args.args[1]
        assert "Additional Research Highlights" in sent_text
        assert "🧭 Overview" in sent_text
        assert "📌 Fresh Facts" in sent_text
        assert "❓ Open Questions" in sent_text
        assert "🔗 Suggested Follow-up" in sent_text
        assert "🧠 Expansion Topics" in sent_text
        assert "🚀 What to explore next" in sent_text
        assert "⚠️ Caveats" in sent_text
