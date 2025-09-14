from __future__ import annotations

from html import unescape
from html.parser import HTMLParser

try:
    from lxml import html as lxml_html
    from readability import Document

    _HAS_READABILITY = True
except Exception:  # pragma: no cover
    Document = None
    lxml_html = None
    _HAS_READABILITY = False


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
    if _HAS_READABILITY:
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
        return "\n".join(line.strip() for line in txt.splitlines() if line.strip())
