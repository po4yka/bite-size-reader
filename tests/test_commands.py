import os
import tempfile
import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

from app.adapters.telegram.telegram_bot import TelegramBot
from app.db.database import Database
from app.services.topic_search import TopicArticle
from tests.conftest import make_test_app_config


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

    async def reply_text(self, text: str, parse_mode: str | None = None) -> None:
        _ = parse_mode
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
    cfg = make_test_app_config(db_path=tmp_path, allowed_user_ids=(1, 42))
    from app.adapters import telegram_bot as tbmod

    tbmod.Client = object
    tbmod.filters = None

    # Mock the OpenRouter client to avoid API key validation
    with patch("app.adapters.telegram.bot_factory.OpenRouterClient") as mock_openrouter:
        mock_openrouter.return_value = AsyncMock()
        return BotSpy(cfg=cfg, db=db)


class TestCommands(unittest.IsolatedAsyncioTestCase):
    async def test_help(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            msg = FakeMessage("/help")
            await bot._on_message(msg)
            assert any("Commands" in r for r in msg._replies)

    async def test_summarize_same_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            url = "https://example.com/a"
            msg = FakeMessage(f"/summarize {url}")
            await bot._on_message(msg)
            assert url in bot.seen_urls

    async def test_summarize_next_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            uid = 42
            await bot._on_message(FakeMessage("/summarize", uid=uid))
            assert uid in bot._awaiting_url_users
            url = "https://example.com/b"
            await bot._on_message(FakeMessage(url, uid=uid))
            assert url in bot.seen_urls
            assert uid not in bot._awaiting_url_users

    async def test_cancel_awaiting_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            bot.response_formatter.MIN_MESSAGE_INTERVAL_MS = 0
            uid = 42

            await bot._on_message(FakeMessage("/summarize", uid=uid))
            assert uid in bot._awaiting_url_users

            cancel_msg = FakeMessage("/cancel", uid=uid)
            await bot._on_message(cancel_msg)

            assert uid not in bot._awaiting_url_users
            assert any(
                "Cancelled your pending URL request" in reply for reply in cancel_msg._replies
            )

    async def test_cancel_pending_multi_links_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            bot.response_formatter.MIN_MESSAGE_INTERVAL_MS = 0
            uid = 42
            multi_text = "https://example.com/a\nhttps://example.com/b"

            await bot._on_message(FakeMessage(multi_text, uid=uid))
            assert uid in bot._pending_multi_links

            cancel_msg = FakeMessage("/cancel", uid=uid)
            await bot._on_message(cancel_msg)

            assert uid not in bot._pending_multi_links
            assert any("pending multi-link confirmation" in reply for reply in cancel_msg._replies)

    async def test_cancel_without_pending_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            bot.response_formatter.MIN_MESSAGE_INTERVAL_MS = 0
            uid = 42

            cancel_msg = FakeMessage("/cancel", uid=uid)
            await bot._on_message(cancel_msg)

            assert any("No pending link requests" in reply for reply in cancel_msg._replies)

    async def test_cancel_includes_active_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            bot.response_formatter.MIN_MESSAGE_INTERVAL_MS = 0
            uid = 42

            bot.message_handler.task_manager.cancel = AsyncMock(return_value=2)

            cancel_msg = FakeMessage("/cancel", uid=uid)
            await bot._on_message(cancel_msg)

            bot.message_handler.task_manager.cancel.assert_awaited_once_with(
                uid, exclude_current=True
            )
            assert any("ongoing requests" in reply for reply in cancel_msg._replies)

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
            assert any("Database Overview" in reply for reply in msg._replies)
            assert any("Requests by status" in reply for reply in msg._replies)
            assert any("Totals" in reply for reply in msg._replies)
            assert not any(db_path in reply for reply in msg._replies)

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
                json_payload=base_summary,
            )
            bot.db.insert_crawl_result(
                request_id=rid_good,
                source_url="https://example.com/good",
                endpoint="/v2/scrape",
                http_status=200,
                status="ok",
                options_json={},
                correlation_id="fc-good",
                content_markdown="# md",
                content_html=None,
                structured_json={},
                metadata_json={},
                links_json=["https://example.com/other"],
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
                json_payload=bad_summary,
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
                json_payload=base_summary,
            )
            bot.db.insert_crawl_result(
                request_id=rid_empty,
                source_url="https://example.com/empty",
                endpoint="/v2/scrape",
                http_status=200,
                status="ok",
                options_json={},
                correlation_id="fc-empty",
                content_markdown="# md",
                content_html=None,
                structured_json={},
                metadata_json={},
                links_json=[],
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

            assert any("Database Verification" in reply for reply in msg._replies)
            assert any("Missing summaries" in reply for reply in msg._replies)
            assert any("Link coverage" in reply for reply in msg._replies)
            assert any("tldr" in reply for reply in msg._replies)
            assert any("Starting automated reprocessing" in reply for reply in msg._replies)
            assert any("Reprocessing complete" in reply for reply in msg._replies)

            expected_urls = {
                "https://example.com/bad",
                "https://example.com/missing",
            }
            assert expected_urls.issubset(set(bot.seen_urls))

    async def test_findweb_command_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            bot.response_formatter.MIN_MESSAGE_INTERVAL_MS = 0

            class FakeSearch:
                def __init__(self) -> None:
                    self.queries: list[tuple[str, str | None]] = []

                async def find_articles(
                    self, topic: str, *, correlation_id: str | None = None
                ) -> list[TopicArticle]:
                    self.queries.append((topic, correlation_id))
                    return [
                        TopicArticle(
                            title="Android System Design Overview",
                            url="https://example.com/android-design",
                            snippet="Key considerations for the Android system architecture.",
                            source="Example Weekly",
                            published_at="2024-04-01",
                        ),
                        TopicArticle(
                            title="Scaling Android Services",
                            url="https://example.com/android-services",
                            snippet="How large teams approach Android service scalability.",
                            source=None,
                            published_at=None,
                        ),
                    ]

            fake_search = FakeSearch()
            bot.topic_searcher = fake_search
            bot.message_handler.command_processor.topic_searcher = fake_search

            msg = FakeMessage("/findweb Android System Design")
            await bot._on_message(msg)

            assert fake_search.queries
            assert fake_search.queries[0][0] == "Android System Design"
            assert any("Online search results" in reply for reply in msg._replies)
            assert any("summarize" in reply.lower() for reply in msg._replies)

    async def test_find_alias_uses_online_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            bot.response_formatter.MIN_MESSAGE_INTERVAL_MS = 0

            class FakeSearch:
                def __init__(self) -> None:
                    self.queries: list[str] = []

                async def find_articles(self, topic: str, *, correlation_id: str | None = None):
                    self.queries.append(topic)
                    return []

            fake_search = FakeSearch()
            bot.topic_searcher = fake_search
            bot.message_handler.command_processor.topic_searcher = fake_search

            msg = FakeMessage("/find Android")
            await bot._on_message(msg)

            assert fake_search.queries == ["Android"]
            assert any("No recent online articles" in reply for reply in msg._replies)

    async def test_finddb_command_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            bot.response_formatter.MIN_MESSAGE_INTERVAL_MS = 0

            class FakeLocalSearch:
                def __init__(self) -> None:
                    self.queries: list[str] = []

                async def find_articles(self, topic: str, *, correlation_id: str | None = None):
                    self.queries.append(topic)
                    return [
                        TopicArticle(
                            title="Saved Android System Design",
                            url="https://example.com/android-design",
                            snippet="Local summary about Android system design.",
                            source="example.com",
                            published_at="2024-04-01",
                        )
                    ]

            fake_local = FakeLocalSearch()
            bot.local_searcher = fake_local
            bot.message_handler.command_processor.local_searcher = fake_local

            msg = FakeMessage("/finddb Android System Design")
            await bot._on_message(msg)

            assert fake_local.queries == ["Android System Design"]
            assert any("Saved library results" in reply for reply in msg._replies)
            assert any("summarize" in reply.lower() for reply in msg._replies)

    async def test_find_commands_require_topic(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            bot.response_formatter.MIN_MESSAGE_INTERVAL_MS = 0

            msg_web = FakeMessage("/findweb")
            await bot._on_message(msg_web)

            class StubLocalSearch:
                async def find_articles(self, topic: str, *, correlation_id: str | None = None):
                    msg = "Should not be called when topic missing"
                    raise AssertionError(msg)

            stub = StubLocalSearch()
            bot.local_searcher = stub
            bot.message_handler.command_processor.local_searcher = stub

            msg_db = FakeMessage("/finddb")
            await bot._on_message(msg_db)

            assert any("Usage" in reply for reply in msg_web._replies)
            assert any("Usage" in reply for reply in msg_db._replies)


if __name__ == "__main__":
    unittest.main()
