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


if __name__ == "__main__":
    unittest.main()
