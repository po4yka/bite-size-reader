import unittest

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

        self.assertGreater(len(msg.replies), 1)
        reconstructed: list[str] = []
        for idx, reply in enumerate(msg.replies, start=1):
            header, _, rest = reply.partition("\n")
            if idx == 1:
                self.assertEqual(header, "🧾 Summary 1000:")
            else:
                self.assertTrue(header.startswith("🧾 Summary 1000 (cont."))
            reconstructed.append(rest)

        original_collapsed = " ".join(body.split())
        combined_collapsed = " ".join(" ".join(reconstructed).split())
        self.assertEqual(combined_collapsed, original_collapsed)

    def test_sanitize_summary_text_trims_incomplete_tail(self) -> None:
        formatter = ResponseFormatter()
        raw = (
            "Статья объясняет, почему естественный язык становится новым языком программирования."
            " Роль 개발"
        )
        cleaned = formatter._sanitize_summary_text(raw)
        self.assertTrue(cleaned.endswith("программирования."))
        self.assertNotIn("개발", cleaned)

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

        self.assertGreaterEqual(len(recorded_replies), 3)
        header_text, header_mode = recorded_replies[0]
        self.assertEqual(header_mode, "HTML")
        self.assertIn("<b>📝 Local-first &lt;Sync&gt;</b>", header_text)
        self.assertIn("<i>Offline_ready &amp; reliable</i>", header_text)

        # Ensure article body and highlights were relayed
        body_text, _ = recorded_replies[1]
        self.assertIn("## Intro", body_text)
        highlight_texts = [
            text for text, _ in recorded_replies if text.startswith("⭐ Key Highlights")
        ]
        self.assertTrue(highlight_texts)
        self.assertEqual(recorded_json[0], article)


if __name__ == "__main__":
    unittest.main()
