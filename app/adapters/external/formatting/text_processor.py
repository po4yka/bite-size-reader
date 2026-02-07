"""Text processing and chunking operations."""

from __future__ import annotations

import html
import logging
import re
import unicodedata
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.adapters.external.formatting.response_sender import ResponseSenderImpl


class TextProcessorImpl:
    """Implementation of text processing and chunking operations."""

    def __init__(
        self,
        response_sender: ResponseSenderImpl,
        *,
        max_message_chars: int = 3500,
    ) -> None:
        """Initialize the text processor.

        Args:
            response_sender: Response sender for sending messages.
            max_message_chars: Maximum characters per message.
        """
        self._response_sender = response_sender
        self._max_message_chars = max_message_chars

    def chunk_text(self, text: str, *, max_len: int) -> list[str]:
        """Split text into chunks respecting Telegram's message length limit."""
        text = text.strip()
        if not text:
            return []

        chunks: list[str] = []
        remaining = text
        while len(remaining) > max_len:
            split_idx = self._find_split_index(remaining, max_len)
            chunk = remaining[:split_idx].rstrip("\n")
            if not chunk:
                chunk = remaining[:max_len]
                split_idx = max_len
            chunks.append(chunk)
            remaining = remaining[split_idx:]
            remaining = remaining.lstrip(" \n\r")
        if remaining:
            chunks.append(remaining)
        return chunks

    def _find_split_index(self, text: str, limit: int) -> int:
        """Find a sensible split index before the limit."""
        min_split = max(20, limit // 4)
        delimiters = [
            "\n\n",
            "\n",
            ". ",
            "! ",
            "? ",
            "; ",
            ": ",
            ", ",
            " ",
        ]
        for delim in delimiters:
            idx = text.rfind(delim, 0, limit)
            if idx >= min_split:
                return min(limit, idx + len(delim))
        return limit

    def sanitize_summary_text(self, text: str) -> str:
        """Normalize and clean summary text for safe sending.

        - Normalize to NFC
        - Remove control characters
        - Drop trailing isolated CJK run (1-3 chars) that looks like a stray token
        """
        try:
            s = unicodedata.normalize("NFC", text)
        except Exception:
            logger.debug("unicode_normalization_failed", exc_info=True)
            s = text
        # Remove control and non-printable chars
        s = "".join(ch for ch in s if unicodedata.category(ch)[0] != "C")

        # If string ends with 1-3 CJK chars and preceding 15 chars have no CJK, drop the tail
        tail_match = re.search(r"([\u4E00-\u9FFF]{1,3})$", s)
        if tail_match:
            start = max(0, len(s) - 20)
            window = s[start : len(s) - len(tail_match.group(1))]
            if not re.search(r"[\u4E00-\u9FFF]", window):
                s = s[: -len(tail_match.group(1))].rstrip("-—")

        s = s.strip()

        if s and s[-1] not in ".!?…":
            last_sentence_end = max(s.rfind("."), s.rfind("!"), s.rfind("?"), s.rfind("…"))
            if last_sentence_end != -1 and last_sentence_end >= len(s) // 3:
                s = s[: last_sentence_end + 1].rstrip()
            else:
                s = s.rstrip("-—")
                if s and s[-1] not in ".!?…":
                    s = s + "."

        return s

    def slugify(self, text: str, *, max_len: int = 60) -> str:
        """Create a filesystem-friendly slug from text."""
        text = text.strip().lower()
        # Replace non-word characters with hyphens
        text = re.sub(r"[^\w\-\s]", "", text)
        text = re.sub(r"[\s_]+", "-", text)
        text = re.sub(r"-+", "-", text).strip("-")
        if len(text) > max_len:
            text = text[:max_len].rstrip("-")
        return text or "summary"

    def build_json_filename(self, obj: dict) -> str:
        """Build a descriptive filename for the JSON attachment."""
        # Prefer SEO keywords; fallback to first words of TL;DR
        seo = obj.get("seo_keywords") or []
        base: str | None = None
        if isinstance(seo, list) and seo:
            base = "-".join(self.slugify(str(x)) for x in seo[:3] if str(x).strip())
        if not base:
            tl = str(obj.get("summary_250", "")).strip()
            if tl:
                # Use first 6 words
                words = re.findall(r"\w+", tl)[:6]
                base = self.slugify("-".join(words))
        if not base:
            base = "summary"
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        return f"{base}-{timestamp}.json"

    def markdown_to_telegram_html(self, text: str) -> str:
        """Convert Markdown to Telegram-supported HTML.

        Handles:
        - H2 headers (## ) → bold with 📌 emoji prefix
        - H3 headers (### ) → plain bold
        - Bold (**text**) → <b>text</b>
        - Italic (*text*) → <i>text</i>
        - Inline code (`code`) → <code>code</code>
        - Code blocks (```) → <pre>code</pre> or <pre><code class="language-X">code</code></pre>
        - Bullet lists (- item) → • item

        Code blocks with language hints preserve the syntax hint in a class attribute:
        - ```python\ncode``` → <pre><code class="language-python">code</code></pre>
        - ```\ncode``` → <pre>code</pre>
        """
        # Escape HTML entities first to prevent injection
        text = html.escape(text)

        # Code blocks (triple backticks) - must be before other transforms
        # Handle ```language\ncode``` and ```\ncode``` with language preservation
        def replace_code_block(match: re.Match[str]) -> str:
            lang = match.group(1) or ""
            code = match.group(2)
            if lang:
                return f'<pre><code class="language-{lang}">{code}</code></pre>'
            return f"<pre>{code}</pre>"

        text = re.sub(
            r"```(\w+)?\n(.*?)```",
            replace_code_block,
            text,
            flags=re.DOTALL,
        )

        # Headers (must be before bold to avoid conflicts with **)
        # H3: ### Header → bold (no emoji)
        text = re.sub(r"^### (.+)$", r"\n<b>\1</b>\n", text, flags=re.MULTILINE)
        # H2: ## Header → bold with 📌 emoji
        text = re.sub(r"^## (.+)$", r"\n<b>📌 \1</b>\n", text, flags=re.MULTILINE)
        # H1: # Header → bold with section marker (rarely used in articles)
        text = re.sub(r"^# (.+)$", r"\n<b>▶ \1</b>\n", text, flags=re.MULTILINE)

        # Bold: **text** → <b>text</b>
        text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)

        # Italic: *text* → <i>text</i> (but not ** which is bold)
        # Use negative lookbehind/lookahead to avoid matching ** patterns
        text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)

        # Inline code: `code` → <code>code</code>
        text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)

        # Bullet lists: - item → • item (at start of line)
        text = re.sub(r"^- ", "• ", text, flags=re.MULTILINE)
        # Also handle * as bullet (common in Markdown)
        text = re.sub(r"^\* ", "• ", text, flags=re.MULTILINE)

        # Clean up excessive newlines (more than 2 consecutive)
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    def linkify_urls(self, text: str) -> str:
        """Convert bare URLs in text to clickable HTML links.

        Only linkifies URLs that aren't already inside href attributes.
        Long URLs are truncated for display but full URL is preserved in href.

        Args:
            text: Text that may contain bare URLs.

        Returns:
            Text with bare URLs converted to <a href="...">...</a> links.
        """
        # Pattern to match URLs not already in href="..."
        # Negative lookbehind for href=" to avoid double-linking
        url_pattern = r'(?<!href=")(?<!">)(https?://[^\s<>"\']+)'

        def replace_url(match: re.Match[str]) -> str:
            url = match.group(1)
            # Escape URL for href attribute
            escaped_url = html.escape(url, quote=True)
            # Truncate display text for long URLs
            display = url[:47] + "..." if len(url) > 50 else url
            display_escaped = html.escape(display)
            return f'<a href="{escaped_url}">{display_escaped}</a>'

        return re.sub(url_pattern, replace_url, text)

    async def send_long_text(
        self, message: Any, text: str, *, parse_mode: str | None = None
    ) -> None:
        """Send text, splitting into multiple messages if too long for Telegram."""
        for chunk in self.chunk_text(text, max_len=self._max_message_chars):
            if chunk:
                await self._response_sender.safe_reply(message, chunk, parse_mode=parse_mode)

    async def send_labelled_text(self, message: Any, label: str, body: str) -> None:
        """Send labelled text, splitting into continuation messages when needed."""
        body = body.strip()
        if not body:
            return
        label_clean = label.rstrip(":")
        primary_title = f"{label_clean}:"
        chunk_limit = max(200, self._max_message_chars - len(primary_title) - 20)
        chunks = self.chunk_text(body, max_len=chunk_limit)
        if not chunks:
            return

        await self._response_sender.safe_reply(message, f"{primary_title}\n{chunks[0]}")
        for idx, chunk in enumerate(chunks[1:], start=2):
            continuation_title = f"{label_clean} (cont. {idx}):"
            await self._response_sender.safe_reply(message, f"{continuation_title}\n{chunk}")
