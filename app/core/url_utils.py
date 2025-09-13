from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode


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
        if k not in TRACKING_PARAMS
    ]
    query_pairs.sort(key=lambda x: (x[0], x[1]))
    query = urlencode(query_pairs)

    normalized = urlunparse((scheme, netloc, path, "", query, ""))
    return normalized


def url_hash_sha256(normalized_url: str) -> str:
    return hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()


def looks_like_url(text: str) -> bool:
    pattern = re.compile(r"https?://[\w\.-]+[\w\./\-?=&%#]*", re.IGNORECASE)
    return bool(pattern.search(text))

