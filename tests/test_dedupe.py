import json
import os
import tempfile
import unittest
from typing import Any, cast
from unittest.mock import AsyncMock, patch

from app.adapters.openrouter.openrouter_client import LLMCallResult
from app.adapters.telegram.telegram_bot import TelegramBot
from app.config import (
    AppConfig,
    FirecrawlConfig,
    OpenRouterConfig,
    RuntimeConfig,
    TelegramConfig,
    YouTubeConfig,
)
from app.core.url_utils import normalize_url, url_hash_sha256
from app.db.database import Database


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


class FakeForwardMessage(FakeMessage):
    def __init__(self, chat_id: int, fwd_chat_id: int, fwd_msg_id: int, text: str, title: str = ""):
        super().__init__()

        class _Chat:
            def __init__(self, cid: int) -> None:
                self.id = cid

        class _User:
            id = 42

        class _FwdChat:
            def __init__(self, cid: int, title: str) -> None:
                self.id = cid
                self.title = title

        self.chat = _Chat(chat_id)
        self.from_user = _User()
        self.forward_from_chat = _FwdChat(fwd_chat_id, title)
        self.forward_from_message_id = fwd_msg_id
        self.text = text


class FakeFirecrawl:
    async def scrape_markdown(self, url: str, request_id=None):
        msg = "Firecrawl should not be called on dedupe hit"
        raise AssertionError(msg)


class FakeOpenRouter:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, request_id=None, **kwargs):
        # return minimal valid JSON content
        self.calls += 1
        content = json.dumps({"summary_250": "ok", "summary_1000": "ok", "tldr": "ok"})
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
                options_json={"formats": ["markdown"], "mobile": True},
                correlation_id="firecrawl-cid",
                content_markdown="# cached",
                content_html=None,
                structured_json={},
                metadata_json={},
                links_json={},
                screenshots_paths_json=None,
                firecrawl_success=True,
                firecrawl_error_code=None,
                firecrawl_error_message=None,
                firecrawl_details_json=None,
                raw_response_json=None,
                latency_ms=1,
                error_text=None,
            )

            # Prepare config with temp DB
            cfg = AppConfig(
                telegram=TelegramConfig(api_id=0, api_hash="", bot_token="", allowed_user_ids=(1,)),
                firecrawl=FirecrawlConfig(api_key="fc-dummy-key"),
                openrouter=OpenRouterConfig(
                    api_key="y",
                    model="m",
                    fallback_models=(),
                    http_referer=None,
                    x_title=None,
                    max_tokens=1024,
                    top_p=1.0,
                    temperature=0.8,
                ),
                youtube=YouTubeConfig(),
                runtime=RuntimeConfig(
                    db_path=db_path,
                    log_level="INFO",
                    request_timeout_sec=5,
                    preferred_lang="en",
                    debug_payloads=False,
                ),
            )

            # Avoid creating real Telegram client
            from app.adapters import telegram_bot as tbmod

            tbmod.Client = object
            tbmod.filters = None

            # Mock the OpenRouter client to avoid API key validation
            with patch("app.adapters.telegram.telegram_bot.OpenRouterClient") as mock_openrouter:
                mock_openrouter.return_value = AsyncMock()
                bot = TelegramBot(cfg=cfg, db=db)
            # Replace external clients with fakes
            bot_any = cast("Any", bot)
            bot_any._firecrawl = FakeFirecrawl()
            fake_or = FakeOpenRouter()
            bot_any._openrouter = fake_or

            msg = FakeMessage()
            # First run: should reuse crawl and insert summary version 1
            await bot._handle_url_flow(msg, url, correlation_id="cid1")
            s1 = db.get_summary_by_request(req_id)
            assert s1 is not None
            assert int(s1["version"]) == 1
            # correlation id updated
            row = db.get_request_by_dedupe_hash(dedupe)
            assert row["correlation_id"] == "cid1"
            first_pass_calls = fake_or.calls
            assert first_pass_calls >= 1  # summarization pipeline made at least one LLM call

            # Second run: dedupe again; summary should be served from cache without a new call
            await bot._handle_url_flow(msg, url, correlation_id="cid2")
            s2 = db.get_summary_by_request(req_id)
            assert s2 is not None
            assert int(s2["version"]) == 1
            row2 = db.get_request_by_dedupe_hash(dedupe)
            assert row2["correlation_id"] == "cid2"
            assert fake_or.calls == first_pass_calls  # cache reuse means no additional LLM calls

    async def test_forward_cached_summary_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "app.db")
            db = Database(db_path)
            db.migrate()

            fwd_chat_id = 777
            fwd_msg_id = 888

            req_id = db.create_request(
                type_="forward",
                status="ok",
                correlation_id="orig",
                chat_id=1,
                user_id=1,
                input_message_id=5,
                fwd_from_chat_id=fwd_chat_id,
                fwd_from_msg_id=fwd_msg_id,
                route_version=1,
            )
            db.insert_summary(
                request_id=req_id,
                lang="en",
                json_payload={"summary_250": "cached", "tldr": "cached"},
            )

            cfg = AppConfig(
                telegram=TelegramConfig(api_id=0, api_hash="", bot_token="", allowed_user_ids=(1,)),
                firecrawl=FirecrawlConfig(api_key="fc-dummy-key"),
                openrouter=OpenRouterConfig(
                    api_key="y",
                    model="m",
                    fallback_models=(),
                    http_referer=None,
                    x_title=None,
                    max_tokens=1024,
                    top_p=1.0,
                    temperature=0.8,
                ),
                youtube=YouTubeConfig(),
                runtime=RuntimeConfig(
                    db_path=db_path,
                    log_level="INFO",
                    request_timeout_sec=5,
                    preferred_lang="en",
                    debug_payloads=False,
                ),
            )

            from app.adapters import telegram_bot as tbmod

            tbmod.Client = object
            tbmod.filters = None

            # Mock the OpenRouter client to avoid API key validation
            with patch("app.adapters.telegram.telegram_bot.OpenRouterClient") as mock_openrouter:
                mock_openrouter.return_value = AsyncMock()
                bot = TelegramBot(cfg=cfg, db=db)

            class FailOpenRouter:
                async def chat(self, *_, **__):
                    msg = "LLM should not run for cached forward summaries"
                    raise AssertionError(msg)

            bot_any = cast("Any", bot)
            bot_any._openrouter = FailOpenRouter()

            msg = FakeForwardMessage(
                chat_id=1,
                fwd_chat_id=fwd_chat_id,
                fwd_msg_id=fwd_msg_id,
                text="Forwarded content",
                title="Channel",
            )

            await bot._handle_forward_flow(msg, correlation_id="newcid")

            cached_summary = db.get_summary_by_request(req_id)
            assert cached_summary is not None
            assert int(cached_summary["version"]) == 1

            existing_request = db.get_request_by_forward(fwd_chat_id, fwd_msg_id)
            assert existing_request is not None
            assert existing_request["correlation_id"] == "newcid"


if __name__ == "__main__":
    unittest.main()
