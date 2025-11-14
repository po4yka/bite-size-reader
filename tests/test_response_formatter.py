import unittest
from unittest.mock import AsyncMock, MagicMock

from app.adapters.external.response_formatter import ResponseFormatter


class DummyMessage:
    def __init__(self) -> None:
        self.replies: list[str] = []

    async def reply_text(self, text: str, parse_mode: str | None = None) -> None:
        self.replies.append(text)


class TestResponseFormatter(unittest.IsolatedAsyncioTestCase):
    async def test_labelled_summary_chunks_preserve_content(self) -> None:
        formatter = ResponseFormatter()
        msg = DummyMessage()
        # Create a body longer than the formatter limit to force chunking.
        body = " ".join(["слово"] * 800)

        # Disable rate limiting for the test
        formatter.MIN_MESSAGE_INTERVAL_MS = 0

        await formatter._send_labelled_text(msg, "🧾 Summary 1000", body)

        assert len(msg.replies) > 1
        reconstructed: list[str] = []
        for idx, reply in enumerate(msg.replies, start=1):
            header, _, rest = reply.partition("\n")
            if idx == 1:
                assert header == "\U0001f9fe Summary 1000:"
            else:
                assert header.startswith("\U0001f9fe Summary 1000 (cont.")
            reconstructed.append(rest)

        original_collapsed = " ".join(body.split())
        combined_collapsed = " ".join(" ".join(reconstructed).split())
        assert combined_collapsed == original_collapsed

    def test_sanitize_summary_text_trims_incomplete_tail(self) -> None:
        formatter = ResponseFormatter()
        raw = (
            "Статья объясняет, почему естественный язык становится новым языком программирования."
            " Роль 개발"
        )
        cleaned = formatter._sanitize_summary_text(raw)
        assert cleaned.endswith("программирования.")
        assert "개발" not in cleaned

    async def test_custom_article_header_uses_html_formatting(self) -> None:
        recorded_replies: list[tuple[str, str | None]] = []

        class Recorder:
            async def __call__(
                self, message: DummyMessage, text: str, parse_mode: str | None = None
            ) -> None:
                message.replies.append(text)
                recorded_replies.append((text, parse_mode))

        recorded_json: list[dict] = []

        async def record_json(_: DummyMessage, payload: dict) -> None:
            recorded_json.append(payload)

        formatter = ResponseFormatter(
            safe_reply_func=Recorder(),
            reply_json_func=record_json,
        )
        formatter.MIN_MESSAGE_INTERVAL_MS = 0

        msg = DummyMessage()
        article = {
            "title": "Local-first <Sync>",
            "subtitle": "Offline_ready & reliable",
            "article_markdown": "## Intro\nBody text",
            "highlights": ["Fast", "Offline"],
        }

        await formatter.send_custom_article(msg, article)

        assert len(recorded_replies) >= 3
        header_text, header_mode = recorded_replies[0]
        assert header_mode == "HTML"
        assert "<b>📝 Local-first &lt;Sync&gt;</b>" in header_text
        assert "<i>Offline_ready &amp; reliable</i>" in header_text

        # Ensure article body and highlights were relayed
        body_text, _ = recorded_replies[1]
        assert "## Intro" in body_text
        highlight_texts = [
            text for text, _ in recorded_replies if text.startswith("⭐ Key Highlights")
        ]
        assert highlight_texts
        assert recorded_json[0] == article

    async def test_edit_message_returns_true_on_success(self) -> None:
        """Test that edit_message returns True when edit succeeds."""
        # Create mock telegram client
        mock_client = MagicMock()
        mock_client.edit_message_text = AsyncMock()

        mock_telegram_client = MagicMock()
        mock_telegram_client.client = mock_client

        formatter = ResponseFormatter()
        formatter._telegram_client = mock_telegram_client
        formatter.MIN_MESSAGE_INTERVAL_MS = 0

        result = await formatter.edit_message(chat_id=12345, message_id=67890, text="Updated text")

        assert result is True
        mock_client.edit_message_text.assert_called_once_with(
            chat_id=12345, message_id=67890, text="Updated text"
        )

    async def test_edit_message_returns_false_on_empty_text(self) -> None:
        """Test that edit_message returns False for empty text."""
        formatter = ResponseFormatter()

        result = await formatter.edit_message(chat_id=12345, message_id=67890, text="")

        assert result is False

    async def test_edit_message_returns_false_on_whitespace_text(self) -> None:
        """Test that edit_message returns False for whitespace-only text."""
        formatter = ResponseFormatter()

        result = await formatter.edit_message(chat_id=12345, message_id=67890, text="   \n\t  ")

        assert result is False

    async def test_edit_message_returns_false_on_too_long_text(self) -> None:
        """Test that edit_message returns False when text exceeds max length."""
        formatter = ResponseFormatter()
        formatter.MIN_MESSAGE_INTERVAL_MS = 0

        # Create text longer than MAX_MESSAGE_CHARS (4096)
        long_text = "x" * 5000

        result = await formatter.edit_message(chat_id=12345, message_id=67890, text=long_text)

        assert result is False

    async def test_edit_message_returns_false_on_invalid_params(self) -> None:
        """Test that edit_message returns False for invalid parameters."""
        mock_client = MagicMock()
        mock_telegram_client = MagicMock()
        mock_telegram_client.client = mock_client

        formatter = ResponseFormatter()
        formatter._telegram_client = mock_telegram_client
        formatter.MIN_MESSAGE_INTERVAL_MS = 0

        # Invalid chat_id (not an int) - intentionally testing bad input
        result = await formatter.edit_message(chat_id="invalid", message_id=67890, text="Test")  # type: ignore[arg-type]

        assert result is False

    async def test_edit_message_returns_false_on_no_client(self) -> None:
        """Test that edit_message returns False when no Telegram client is available."""
        formatter = ResponseFormatter()
        formatter.MIN_MESSAGE_INTERVAL_MS = 0

        result = await formatter.edit_message(chat_id=12345, message_id=67890, text="Test")

        assert result is False

    async def test_edit_message_returns_false_on_exception(self) -> None:
        """Test that edit_message returns False when an exception occurs."""
        mock_client = MagicMock()
        mock_client.edit_message_text = AsyncMock(side_effect=Exception("Network error"))

        mock_telegram_client = MagicMock()
        mock_telegram_client.client = mock_client

        formatter = ResponseFormatter()
        formatter._telegram_client = mock_telegram_client
        formatter.MIN_MESSAGE_INTERVAL_MS = 0

        result = await formatter.edit_message(chat_id=12345, message_id=67890, text="Test")

        assert result is False

    async def test_edit_message_returns_false_on_unsafe_content(self) -> None:
        """Test that edit_message returns False for unsafe content."""
        formatter = ResponseFormatter()
        formatter.MIN_MESSAGE_INTERVAL_MS = 0

        # Content with control characters should be blocked
        unsafe_text = "Test\x00message"

        result = await formatter.edit_message(chat_id=12345, message_id=67890, text=unsafe_text)

        assert result is False


if __name__ == "__main__":
    unittest.main()
