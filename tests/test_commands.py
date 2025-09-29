import json
import os
import tempfile
import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

from app.adapters.telegram.telegram_bot import TelegramBot
from app.config import AppConfig, FirecrawlConfig, OpenRouterConfig, RuntimeConfig, TelegramConfig
from app.db.database import Database


class FakeMessage:
    def __init__(self, text: str, uid: int = 1):
        class _User:
            def __init__(self, id):
                self.id = id

        class _Chat:
            id = 1

        self.text = text
        self.chat = _Chat()
        self.from_user = _User(uid)
        self._replies: list[str] = []
        self.id = 123
        self.message_id = 123

    async def reply_text(self, text: str) -> None:
        self._replies.append(text)


class BotSpy(TelegramBot):
    def __init__(self, *a: Any, **kw: Any) -> None:
        super().__init__(*a, **kw)
        self.seen_urls: list[str] = []

    async def _handle_url_flow(self, message: Any, url_text: str, **_: object) -> None:
        self.seen_urls.append(url_text)
        await self._safe_reply(message, f"OK {url_text}")


def make_bot(tmp_path: str) -> BotSpy:
    db = Database(tmp_path)
    db.migrate()
    cfg = AppConfig(
        telegram=TelegramConfig(api_id=0, api_hash="", bot_token="", allowed_user_ids=(1, 42)),
        firecrawl=FirecrawlConfig(api_key="fc-dummy-key"),
        openrouter=OpenRouterConfig(
            api_key="y",
            model="m",
            fallback_models=tuple(),
            http_referer=None,
            x_title=None,
            max_tokens=None,
            top_p=None,
            temperature=0.2,
        ),
        runtime=RuntimeConfig(
            db_path=tmp_path,
            log_level="INFO",
            request_timeout_sec=5,
            preferred_lang="en",
            debug_payloads=False,
        ),
    )
    from app.adapters import telegram_bot as tbmod

    setattr(tbmod, "Client", object)
    setattr(tbmod, "filters", None)

    # Mock the OpenRouter client to avoid API key validation
    with patch("app.adapters.telegram.telegram_bot.OpenRouterClient") as mock_openrouter:
        mock_openrouter.return_value = AsyncMock()
        return BotSpy(cfg=cfg, db=db)


class TestCommands(unittest.IsolatedAsyncioTestCase):
    async def test_help(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            msg = FakeMessage("/help")
            await bot._on_message(msg)
            self.assertTrue(any("Commands" in r for r in msg._replies))

    async def test_summarize_same_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            url = "https://example.com/a"
            msg = FakeMessage(f"/summarize {url}")
            await bot._on_message(msg)
            self.assertIn(url, bot.seen_urls)

    async def test_summarize_next_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            uid = 42
            await bot._on_message(FakeMessage("/summarize", uid=uid))
            self.assertIn(uid, bot._awaiting_url_users)
            url = "https://example.com/b"
            await bot._on_message(FakeMessage(url, uid=uid))
            self.assertIn(url, bot.seen_urls)
            self.assertNotIn(uid, bot._awaiting_url_users)

    async def test_cancel_awaiting_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            bot.response_formatter.MIN_MESSAGE_INTERVAL_MS = 0
            uid = 42

            await bot._on_message(FakeMessage("/summarize", uid=uid))
            self.assertIn(uid, bot._awaiting_url_users)

            cancel_msg = FakeMessage("/cancel", uid=uid)
            await bot._on_message(cancel_msg)

            self.assertNotIn(uid, bot._awaiting_url_users)
            self.assertTrue(
                any("Cancelled your pending URL request" in reply for reply in cancel_msg._replies)
            )

    async def test_cancel_pending_multi_links_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            bot.response_formatter.MIN_MESSAGE_INTERVAL_MS = 0
            uid = 42
            multi_text = "https://example.com/a\nhttps://example.com/b"

            await bot._on_message(FakeMessage(multi_text, uid=uid))
            self.assertIn(uid, bot._pending_multi_links)

            cancel_msg = FakeMessage("/cancel", uid=uid)
            await bot._on_message(cancel_msg)

            self.assertNotIn(uid, bot._pending_multi_links)
            self.assertTrue(
                any("pending multi-link confirmation" in reply for reply in cancel_msg._replies)
            )

    async def test_cancel_without_pending_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            bot.response_formatter.MIN_MESSAGE_INTERVAL_MS = 0
            uid = 42

            cancel_msg = FakeMessage("/cancel", uid=uid)
            await bot._on_message(cancel_msg)

            self.assertTrue(
                any("No pending link requests" in reply for reply in cancel_msg._replies)
            )

    async def test_dbinfo_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "app.db")
            bot = make_bot(db_path)
            request_id = bot.db.create_request(
                type_="url",
                status="completed",
                correlation_id="cid",
                chat_id=1,
                user_id=1,
                input_url="https://example.com",
            )
            bot.db.insert_summary(request_id=request_id, lang="en", json_payload="{}")
            bot.db.insert_audit_log(level="INFO", event="test", details_json="{}")

            msg = FakeMessage("/dbinfo")
            await bot._on_message(msg)
            self.assertTrue(any("Database Overview" in reply for reply in msg._replies))
            self.assertTrue(any("Requests by status" in reply for reply in msg._replies))
            self.assertTrue(any("Totals" in reply for reply in msg._replies))
            self.assertFalse(any(db_path in reply for reply in msg._replies))

    async def test_dbverify_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            bot.response_formatter.MIN_MESSAGE_INTERVAL_MS = 0

            base_summary = {
                "summary_250": "Short summary.",
                "summary_1000": "Medium summary.",
                "tldr": "Long summary.",
                "key_ideas": ["Idea"],
                "topic_tags": ["#tag"],
                "entities": {"people": [], "organizations": [], "locations": []},
                "estimated_reading_time_min": 5,
                "key_stats": [],
                "answered_questions": [],
                "readability": {"method": "FK", "score": 50.0, "level": "Standard"},
                "seo_keywords": [],
                "metadata": {
                    "title": "Title",
                    "canonical_url": "https://example.com/article",
                    "domain": "example.com",
                    "author": "Author",
                    "published_at": "2024-01-01",
                    "last_updated": "2024-01-01",
                },
                "extractive_quotes": [],
                "highlights": [],
                "questions_answered": [],
                "categories": [],
                "topic_taxonomy": [],
                "hallucination_risk": "low",
                "confidence": 1.0,
                "forwarded_post_extras": None,
                "key_points_to_remember": [],
            }

            rid_good = bot.db.create_request(
                type_="url",
                status="ok",
                correlation_id="good",
                chat_id=1,
                user_id=1,
                input_url="https://example.com/good",
                normalized_url="https://example.com/good",
                route_version=1,
            )
            bot.db.insert_summary(
                request_id=rid_good,
                lang="en",
                json_payload=json.dumps(base_summary),
            )
            bot.db.insert_crawl_result(
                request_id=rid_good,
                source_url="https://example.com/good",
                endpoint="/v1/scrape",
                http_status=200,
                status="ok",
                options_json=json.dumps({}),
                correlation_id="fc-good",
                content_markdown="# md",
                content_html=None,
                structured_json=json.dumps({}),
                metadata_json=json.dumps({}),
                links_json=json.dumps(["https://example.com/other"]),
                screenshots_paths_json=None,
                firecrawl_success=True,
                firecrawl_error_code=None,
                firecrawl_error_message=None,
                firecrawl_details_json=None,
                raw_response_json=None,
                latency_ms=100,
                error_text=None,
            )

            bad_summary = dict(base_summary)
            bad_summary.pop("summary_1000", None)
            bad_summary.pop("tldr", None)

            rid_bad = bot.db.create_request(
                type_="url",
                status="ok",
                correlation_id="bad",
                chat_id=1,
                user_id=1,
                input_url="https://example.com/bad",
                normalized_url="https://example.com/bad",
                route_version=1,
            )
            bot.db.insert_summary(
                request_id=rid_bad,
                lang="en",
                json_payload=json.dumps(bad_summary),
            )

            rid_empty = bot.db.create_request(
                type_="url",
                status="ok",
                correlation_id="empty",
                chat_id=1,
                user_id=1,
                input_url="https://example.com/empty",
                normalized_url="https://example.com/empty",
                route_version=1,
            )
            bot.db.insert_summary(
                request_id=rid_empty,
                lang="en",
                json_payload=json.dumps(base_summary),
            )
            bot.db.insert_crawl_result(
                request_id=rid_empty,
                source_url="https://example.com/empty",
                endpoint="/v1/scrape",
                http_status=200,
                status="ok",
                options_json=json.dumps({}),
                correlation_id="fc-empty",
                content_markdown="# md",
                content_html=None,
                structured_json=json.dumps({}),
                metadata_json=json.dumps({}),
                links_json=json.dumps([]),
                screenshots_paths_json=None,
                firecrawl_success=True,
                firecrawl_error_code=None,
                firecrawl_error_message=None,
                firecrawl_details_json=None,
                raw_response_json=None,
                latency_ms=100,
                error_text=None,
            )

            bot.db.create_request(
                type_="url",
                status="pending",
                correlation_id="missing",
                chat_id=1,
                user_id=1,
                input_url="https://example.com/missing",
                normalized_url="https://example.com/missing",
                route_version=1,
            )

            msg = FakeMessage("/dbverify")
            await bot._on_message(msg)

            self.assertTrue(any("Database Verification" in reply for reply in msg._replies))
            self.assertTrue(any("Missing summaries" in reply for reply in msg._replies))
            self.assertTrue(any("Link coverage" in reply for reply in msg._replies))
            self.assertTrue(any("tldr" in reply for reply in msg._replies))
            self.assertTrue(
                any("Starting automated reprocessing" in reply for reply in msg._replies)
            )
            self.assertTrue(any("Reprocessing complete" in reply for reply in msg._replies))

            expected_urls = {
                "https://example.com/bad",
                "https://example.com/missing",
            }
            self.assertTrue(expected_urls.issubset(set(bot.seen_urls)))


if __name__ == "__main__":
    unittest.main()
