"""Extract embedded link URLs from a forwarded Telegram post.

A forwarded channel post carries links two ways: as literal URLs in the visible
text, and as ``text_link`` entities (hyperlinked words, where the target lives
in ``entity.url``). ``extract_all_urls`` only sees the former; this helper unions
both sources so the forward-link enricher can fetch every referenced article.
"""

from __future__ import annotations

from typing import Any

from app.core.logging_utils import get_logger
from app.core.urls.extraction import extract_all_urls
from app.core.urls.normalization import normalize_url

logger = get_logger(__name__)


def extract_forward_urls(
    message: Any,
    text: str | None,
    *,
    correlation_id: str | None = None,
) -> list[str]:
    """Return the ordered, deduped URLs embedded in a forwarded post.

    Combines literal URLs in ``text`` with ``text_link`` entity targets exposed
    by ``message.entities`` (aiogram-shaped after ``TelethonMessageAdapter``
    translation). Order-preserving; deduped on the normalized URL. Never raises
    -- returns ``[]`` on any failure.
    """
    try:
        candidates: list[str] = list(extract_all_urls(text or ""))

        for entity in getattr(message, "entities", None) or []:
            # ``text_link`` covers both the translated ``_Entity`` (type is the
            # plain string) and a parsed ``MessageEntity`` (StrEnum compares
            # equal to the string).
            if getattr(entity, "type", None) == "text_link":
                url = getattr(entity, "url", None)
                if url:
                    candidates.append(url)

        seen: set[str] = set()
        ordered: list[str] = []
        for raw in candidates:
            url = (raw or "").strip()
            if not url:
                continue
            try:
                key = normalize_url(url)
            except Exception:  # pragma: no cover - normalize is defensive already
                key = url
            if key in seen:
                continue
            seen.add(key)
            ordered.append(url)

        logger.debug(
            "forward_link_extraction",
            extra={"cid": correlation_id, "count": len(ordered)},
        )
        return ordered
    except Exception as exc:  # pragma: no cover - defensive: never block the flow
        logger.debug(
            "forward_link_extraction_failed",
            extra={"cid": correlation_id, "error": str(exc)},
        )
        return []
