import unittest
import tempfile
import os
import json

from app.core.url_utils import normalize_url, url_hash_sha256
from app.db.database import Database
from app.adapters.telegram_bot import TelegramBot
from app.config import AppConfig, TelegramConfig, FirecrawlConfig, OpenRouterConfig, RuntimeConfig
from app.adapters.openrouter_client import LLMCallResult


class FakeMessage:
    def __init__(self):
        class _Chat:
            id = 1

        self.chat = _Chat()
        self.id = 123
        self.message_id = 123
        self._replies = []

    async def reply_text(self, text):
        self._replies.append(text)


class FakeFirecrawl:
    async def scrape_markdown(self, url: str, request_id=None):  # noqa: ARG002
        raise AssertionError("Firecrawl should not be called on dedupe hit")


class FakeOpenRouter:
    async def chat(self, messages, request_id=None):  # noqa: ARG002
        # return minimal valid JSON content
        content = json.dumps({"summary_250": "ok", "summary_1000": "ok"})
        return LLMCallResult(
            status="ok",
            model="m",
            response_text=content,
            response_json={"choices": [{"message": {"content": content}}]},
            tokens_prompt=1,
            tokens_completion=1,
            cost_usd=None,
            latency_ms=1,
            error_text=None,
            request_headers={},
            request_messages=messages,
        )


class TestDedupeReuse(unittest.IsolatedAsyncioTestCase):
    async def test_dedupe_and_summary_version_increment(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "app.db")
            db = Database(db_path)
            db.migrate()

            url = "https://Example.com/Path?a=1&utm_source=x"
            norm = normalize_url(url)
            dedupe = url_hash_sha256(norm)

            # Create initial request and crawl result
            req_id = db.create_request(
                type_="url",
                status="pending",
                correlation_id="initcid",
                chat_id=1,
                user_id=1,
                input_url=url,
                normalized_url=norm,
                dedupe_hash=dedupe,
                route_version=1,
            )
            db.insert_crawl_result(
                request_id=req_id,
                source_url=url,
                endpoint="/v1/scrape",
                http_status=200,
                status="ok",
                options_json=json.dumps({"formats": ["markdown"], "mobile": True}),
                content_markdown="# cached",
                content_html=None,
                structured_json=json.dumps({}),
                metadata_json=json.dumps({}),
                links_json=json.dumps({}),
                screenshots_paths_json=None,
                raw_response_json=json.dumps({}),
                latency_ms=1,
                error_text=None,
            )

            # Prepare config with temp DB
            cfg = AppConfig(
                telegram=TelegramConfig(api_id=0, api_hash="", bot_token="", allowed_user_ids=tuple()),
                firecrawl=FirecrawlConfig(api_key="x"),
                openrouter=OpenRouterConfig(api_key="y", model="m", fallback_models=tuple(), http_referer=None, x_title=None),
                runtime=RuntimeConfig(db_path=db_path, log_level="INFO", request_timeout_sec=5, preferred_lang="en"),
            )

            # Avoid creating real Telegram client
            from app.adapters import telegram_bot as tbmod

            tbmod.Client = object  # type: ignore
            tbmod.filters = None  # type: ignore

            bot = TelegramBot(cfg=cfg, db=db)
            # Replace external clients with fakes
            bot._firecrawl = FakeFirecrawl()  # type: ignore[attr-defined]
            bot._openrouter = FakeOpenRouter()  # type: ignore[attr-defined]

            msg = FakeMessage()
            # First run: should reuse crawl and insert summary version 1
            await bot._handle_url_flow(msg, url, correlation_id="cid1")
            s1 = db.get_summary_by_request(req_id)
            self.assertIsNotNone(s1)
            self.assertEqual(int(s1["version"]), 1)
            # correlation id updated
            row = db.get_request_by_dedupe_hash(dedupe)
            self.assertEqual(row["correlation_id"], "cid1")

            # Second run: dedupe again; summary version should increment
            await bot._handle_url_flow(msg, url, correlation_id="cid2")
            s2 = db.get_summary_by_request(req_id)
            self.assertIsNotNone(s2)
            self.assertEqual(int(s2["version"]), 2)
            row2 = db.get_request_by_dedupe_hash(dedupe)
            self.assertEqual(row2["correlation_id"], "cid2")


if __name__ == "__main__":
    unittest.main()
