import pytest

from app.adapters.external.response_formatter import ResponseFormatter


class DummyMessage:
    def __init__(self) -> None:
        self.replies: list[str] = []

    async def reply_text(self, text: str, parse_mode: str | None = None) -> None:
        self.replies.append(text)


@pytest.mark.asyncio
async def test_labelled_summary_chunks_preserve_content() -> None:
    formatter = ResponseFormatter()
    msg = DummyMessage()
    # Create a body longer than the formatter limit to force chunking.
    body = " ".join(["слово"] * 800)

    await formatter._send_labelled_text(msg, "🧾 Summary 1000", body)

    assert len(msg.replies) > 1
    reconstructed: list[str] = []
    for idx, reply in enumerate(msg.replies, start=1):
        header, _, rest = reply.partition("\n")
        if idx == 1:
            assert header == "🧾 Summary 1000:"
        else:
            assert header.startswith("🧾 Summary 1000 (cont.")
        reconstructed.append(rest)

    original_collapsed = " ".join(body.split())
    combined_collapsed = " ".join(" ".join(reconstructed).split())
    assert combined_collapsed == original_collapsed
