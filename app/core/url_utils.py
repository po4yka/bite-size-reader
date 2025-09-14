from __future__ import annotations

import hashlib
import logging
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

logger = logging.getLogger(__name__)


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
}


def normalize_url(url: str) -> str:
    """Normalize a URL for deduplication as per SPEC.md.

    - Lowercase scheme & host
    - Strip fragment
    - Sort query params and remove common tracking params
    - Collapse trailing slash
    """
    if "://" not in url:
        url = f"http://{url}"
    p = urlparse(url)
    scheme = (p.scheme or "http").lower()
    netloc = p.netloc.lower()
    path = p.path or "/"

    # Remove redundant trailing slash except for root
    if path.endswith("/") and path != "/":
        path = path.rstrip("/")

    # Filter and sort query params
    query_pairs = [
        (k, v)
        for k, v in parse_qsl(p.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS
    ]
    query_pairs.sort(key=lambda x: (x[0], x[1]))
    query = urlencode(query_pairs)

    normalized = urlunparse((scheme, netloc, path, "", query, ""))
    logger.debug("normalize_url", extra={"url": url, "normalized": normalized})
    return normalized


def url_hash_sha256(normalized_url: str) -> str:
    h = hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()
    logger.debug("url_hash", extra={"normalized": normalized_url, "sha256": h})
    return h


def looks_like_url(text: str) -> bool:
    pattern = re.compile(r"https?://[\w\.-]+[\w\./\-?=&%#]*", re.IGNORECASE)
    ok = bool(pattern.search(text))
    logger.debug("looks_like_url", extra={"text_sample": text[:80], "match": ok})
    return ok


def extract_first_url(text: str) -> str | None:
    pattern = re.compile(r"https?://[\w\.-]+[\w\./\-?=&%#]*", re.IGNORECASE)
    m = pattern.search(text)
    val = m.group(0) if m else None
    logger.debug("extract_first_url", extra={"text_sample": text[:80], "url": val})
    return val


def extract_all_urls(text: str) -> list[str]:
    pattern = re.compile(r"https?://[\w\.-]+[\w\./\-?=&%#]*", re.IGNORECASE)
    urls = pattern.findall(text) if text else []
    # Preserve order, dedupe
    seen = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    logger.debug("extract_all_urls", extra={"count": len(out)})
    return out
