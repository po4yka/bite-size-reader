from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser

# ruff: noqa: E501


try:
    from lxml import html as lxml_html
    from readability import Document

    _HAS_READABILITY = True
except Exception:  # pragma: no cover
    Document = None
    lxml_html = None
    _HAS_READABILITY = False

# Optional textacy / spacy normalization imports
_HAS_TEXTACY = True  # will be validated at runtime in functions


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._buf: list[str] = []
        self._skip_depth = 0  # skip script/style

    def handle_starttag(self, tag: str, attrs):
        if tag in ("script", "style"):
            self._skip_depth += 1
        elif self._skip_depth == 0:
            if tag in ("br",):
                self._buf.append("\n")
            elif tag in ("p", "div", "section", "article", "header", "footer"):
                self._buf.append("\n\n")
            elif tag in ("li",):
                self._buf.append("\n- ")
            elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                self._buf.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip_depth > 0:
            self._skip_depth -= 1
        elif self._skip_depth == 0:
            if tag in ("p", "div"):
                self._buf.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            text = data.strip()
            if text:
                self._buf.append(text)

    def get_text(self) -> str:
        # Collapse excessive blank lines
        text = "".join(self._buf)
        text = unescape(text)
        # Normalize lines: remove 3+ newlines -> 2
        while "\n\n\n" in text:
            text = text.replace("\n\n\n", "\n\n")
        return text.strip()


def html_to_text(html: str) -> str:
    # Prefer readability (main content) + lxml text extraction if available
    if _HAS_READABILITY and Document is not None and lxml_html is not None:
        try:
            doc = Document(html)
            summary_html = doc.summary() or ""
            title = (doc.title() or "").strip()
            if summary_html:
                root = lxml_html.fromstring(summary_html)
                text = root.text_content()
                if title and title not in text:
                    text = f"{title}\n\n{text}"
                # Normalize whitespace
                text = "\n".join(line.strip() for line in text.splitlines())
                while "\n\n\n" in text:
                    text = text.replace("\n\n\n", "\n\n")
                return text.strip()
        except Exception:
            pass

    # Fallback: lightweight HTML parsing
    parser = _TextExtractor()
    try:
        parser.feed(html)
        return parser.get_text()
    except Exception:
        # Fallback: very naive strip
        import re

        txt = re.sub(r"<script[\s\S]*?</script>", "", html, flags=re.I)
        txt = re.sub(r"<style[\s\S]*?</style>", "", txt, flags=re.I)
        txt = re.sub(r"<br\s*/?>", "\n", txt, flags=re.I)
        txt = re.sub(r"</p>", "\n\n", txt, flags=re.I)
        txt = re.sub(r"<[^>]+>", " ", txt)
        txt = unescape(txt)
        lines = [line.strip() for line in txt.splitlines() if line.strip()]
        return "\n".join(lines)


def clean_markdown_article_text(markdown: str) -> str:
    """Best-effort cleaning to extract only article text from markdown.

    - Removes code blocks and images
    - Converts links to plain text (keeps anchor text)
    - Drops common boilerplate/UI lines (share, login, embeds, etc.)
    - Collapses excessive whitespace
    """
    if not isinstance(markdown, str):
        markdown = str(markdown) if markdown is not None else ""

    text = markdown
    # Remove fenced code blocks
    text = re.sub(r"```[\s\S]*?```", "", text)
    # Remove inline code spans
    text = re.sub(r"`[^`]*`", "", text)
    # Remove images ![alt](url)
    text = re.sub(r"!\[[^\]]*\]\([^\)]+\)", "", text)
    # Convert links [text](url) -> text
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    # Remove reference-style link definitions and bare image refs
    text = re.sub(r"^\s*\[[^\]]+\]:\s*\S+\s*$", "", text, flags=re.M)

    # Line-level filtering of boilerplate
    lines = [ln.rstrip() for ln in text.splitlines()]
    drop_prefixes = (
        "share",
        "watch later",
        "copy link",
        "include playlist",
        "tap to unmute",
        "you're signed out",
        "videos you watch",
        "search",
        "info",
        "shopping",
        "cancel",
        "confirm",
        "subscribe",
        "sign in",
        "login",
        "comments",
        "комментарии",
        "поделиться",
    )
    drop_exact = {"—", "-", "•", "* * *", "— — —"}

    filtered: list[str] = []
    for ln in lines:
        raw = ln.strip()
        if not raw:
            filtered.append("")
            continue
        low = raw.lower()
        if any(low.startswith(pfx) for pfx in drop_prefixes):
            continue
        if raw in drop_exact:
            continue
        # Drop plain URLs
        if re.fullmatch(r"https?://\S+", raw):
            continue
        # Drop lines that are mostly punctuation bullets
        if len(raw) <= 3 and raw.strip("•-*_") == "":
            continue
        filtered.append(raw)

    # Collapse multiple blank lines
    out_lines: list[str] = []
    prev_blank = False
    for ln in filtered:
        if ln == "":
            if not prev_blank:
                out_lines.append("")
            prev_blank = True
        else:
            out_lines.append(ln)
            prev_blank = False

    cleaned = "\n".join(out_lines).strip()
    # Normalize excessive spaces within lines
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    # Final collapse of triple newlines if any remain
    while "\n\n\n" in cleaned:
        cleaned = cleaned.replace("\n\n\n", "\n\n")
    return cleaned


def normalize_with_textacy(text: str) -> str:
    """Apply lightweight normalization using textacy if available.

    Operations:
    - normalize unicode quotes/dashes
    - replace URLs/emails with placeholders
    - collapse repeated whitespace
    - strip control characters
    Fallbacks to simple regex-based cleanup if textacy isn't installed.
    """
    if not isinstance(text, str):
        text = str(text) if text is not None else ""

    try:
        import textacy.preprocessing as tprep

        normalized = text
        normalized = tprep.normalize.unicode(normalized)
        normalized = tprep.replace.urls(normalized, repl=" ")
        normalized = tprep.replace.emails(normalized, repl=" ")
        normalized = tprep.replace.phone_numbers(normalized, repl=" ")
        normalized = tprep.normalize.whitespace(normalized)
        return normalized.strip()
    except Exception:
        pass

    # Fallbacks without textacy
    out = text
    out = re.sub(r"https?://\S+", " ", out)
    out = re.sub(r"\S+@\S+", " ", out)
    out = re.sub(r"[\u0000-\u001F\u007F]", " ", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    while "\n\n\n" in out:
        out = out.replace("\n\n\n", "\n\n")
    return out.strip()


def split_sentences(text: str, lang: str = "en") -> list[str]:
    """Split text into sentences using spaCy if available, else regex fallback.

    Uses a lightweight blank pipeline with a sentencizer to avoid heavy models.
    """
    if not isinstance(text, str):
        text = str(text) if text is not None else ""
    text = text.strip()
    if not text:
        return []

    try:  # pragma: no cover - optional dependency
        import spacy

        nlp = spacy.blank(lang)
        if "sentencizer" not in nlp.pipe_names:
            nlp.add_pipe("sentencizer")
        doc = nlp(text)
        return [sent.text.strip() for sent in doc.sents if sent.text.strip()]
    except Exception:
        pass

    # Regex fallback: split on sentence punctuation followed by space/cap
    parts = re.split(r"(?<=[\.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def chunk_sentences(sentences: list[str], max_chars: int = 2000) -> list[str]:
    """Group sentences into chunks under max_chars, preserving boundaries."""
    if not isinstance(sentences, list):
        return []
    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for sent in sentences:
        s = (sent or "").strip()
        if not s:
            continue
        if size + len(s) + (1 if buf else 0) > max_chars and buf:
            chunks.append(" ".join(buf))
            buf = [s]
            size = len(s)
        else:
            if buf:
                size += 1  # space
            buf.append(s)
            size += len(s)
    if buf:
        chunks.append(" ".join(buf))
    return chunks
