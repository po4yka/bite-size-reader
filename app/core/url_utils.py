from __future__ import annotations

import contextvars
import hashlib
import logging
import re
from contextlib import contextmanager
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlparse, urlunparse

if TYPE_CHECKING:
    from collections.abc import Generator

logger = logging.getLogger(__name__)

# Per-task DNS resolution cache (opt-in via dns_cache_scope()).
# When active, caches socket.getaddrinfo() results so repeated
# normalize_url() calls for the same hostname skip DNS entirely.
_dns_cache: contextvars.ContextVar[dict[str, list] | None] = contextvars.ContextVar(
    "_dns_cache", default=None
)


def extract_domain(url: str | None) -> str | None:
    """Extract normalized domain from URL (lowercase, without ``www.``)."""
    if not url:
        return None
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split("/")[0]
        if domain.startswith("www."):
            domain = domain[4:]
        return domain.lower() if domain else None
    except Exception:
        return None


@contextmanager
def dns_cache_scope() -> Generator[None]:
    """Enable DNS resolution caching for the duration of this scope.

    Within the scope, socket.getaddrinfo() results are cached per hostname
    so that repeated normalize_url() calls avoid redundant DNS lookups.
    The cache is automatically discarded on scope exit.
    """
    token = _dns_cache.set({})
    try:
        yield
    finally:
        _dns_cache.reset(token)


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
}


# Match URLs with explicit protocol
_URL_SEARCH_PATTERN = re.compile(r"https?://[\w\.-]+[\w\./\-?=&%#]*", re.IGNORECASE)
_URL_FINDALL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

# Match URLs starting with www. without protocol (e.g., www.example.com/path)
_WWW_URL_SEARCH_PATTERN = re.compile(r"\bwww\.[\w\.-]+[\w\./\-?=&%#]*", re.IGNORECASE)
_WWW_URL_FINDALL_PATTERN = re.compile(r"\bwww\.[\w\.-]+[^\s<>\"']*", re.IGNORECASE)
_DANGEROUS_URL_SUBSTRINGS: tuple[str, ...] = (
    "<",
    ">",
    '"',
    "'",
    "script",
    "javascript:",
    "data:",
)

# Comprehensive list of allowed URL schemes (only http and https)
_ALLOWED_SCHEMES: frozenset[str] = frozenset(["http", "https"])

# Dangerous schemes that should always be rejected
_DANGEROUS_SCHEMES: frozenset[str] = frozenset(
    [
        "file",
        "ftp",
        "ftps",
        "javascript",
        "data",
        "vbscript",
        "about",
        "blob",
        "filesystem",
        "ws",
        "wss",
        "mailto",
        "tel",
        "sms",
        "ssh",
        "sftp",
        "telnet",
        "gopher",
        "ldap",
        "ldaps",
    ]
)


def _validate_url_input(url: str) -> None:
    """Validate URL input for security.

    Comprehensive validation including:
    - Length limits (RFC 2616)
    - Dangerous content patterns
    - Scheme validation (only http/https)
    - SSRF protection (private IPs, loopback, link-local, etc.)
    - Suspicious domain patterns
    - Control characters and null bytes

    Args:
        url: URL string to validate

    Raises:
        ValueError: If URL is invalid or contains dangerous content

    """
    _validate_url_input_basics(url)

    try:
        parsed = urlparse(url if "://" in url else f"http://{url}")
        hostname = parsed.hostname or parsed.netloc
        if hostname:
            _validate_hostname_security(hostname)

    except ValueError:
        # Re-raise our validation errors
        raise
    except Exception as e:
        # If URL parsing fails for other reasons, log but allow it
        # (will be caught by urlparse in normalize_url)
        logger.debug(
            "url_validation_parse_warning",
            extra={"url": url[:100], "error": str(e)},
        )


def _validate_url_input_basics(url: str) -> None:
    if not url:
        msg = "URL cannot be empty"
        raise ValueError(msg)
    if not isinstance(url, str):
        msg = "URL must be a string"
        raise ValueError(msg)
    if len(url) > 2048:
        msg = "URL too long"
        raise ValueError(msg)

    url_lower = url.lower()
    if any(needle in url_lower for needle in _DANGEROUS_URL_SUBSTRINGS):
        msg = "URL contains potentially dangerous content"
        raise ValueError(msg)
    for dangerous_scheme in _DANGEROUS_SCHEMES:
        if url_lower.startswith(f"{dangerous_scheme}:"):
            msg = f"URL scheme '{dangerous_scheme}' is not allowed"
            raise ValueError(msg)
    if "\x00" in url:
        msg = "URL contains null bytes"
        raise ValueError(msg)
    if any(ord(char) < 32 and char not in ("\t", "\n", "\r") for char in url):
        msg = "URL contains control characters"
        raise ValueError(msg)


def _validate_hostname_security(hostname: str) -> None:
    hostname_lower = hostname.lower()
    if hostname_lower in ("localhost", "localhost.localdomain"):
        msg = "Localhost access not allowed"
        raise ValueError(msg)

    ip_obj = _parse_hostname_ip(hostname, hostname_lower)
    if ip_obj is not None:
        _validate_blocked_ip(ip_obj)
        return

    _validate_suspicious_domain_pattern(hostname_lower)
    resolved = _resolve_hostname_to_addrs(hostname, hostname_lower)
    _validate_resolved_addresses(resolved, hostname_lower)


def _parse_hostname_ip(hostname: str, hostname_lower: str) -> object | None:
    import ipaddress

    try:
        return ipaddress.ip_address(hostname)
    except ValueError:
        logger.debug("url_hostname_not_ip_address", extra={"hostname": hostname_lower})
        return None


def _validate_blocked_ip(ip_obj: object) -> None:
    if getattr(ip_obj, "is_private", False):
        msg = f"Private IP address not allowed: {ip_obj}"
        raise ValueError(msg)
    if getattr(ip_obj, "is_loopback", False):
        msg = f"Loopback address not allowed: {ip_obj}"
        raise ValueError(msg)
    if getattr(ip_obj, "is_link_local", False):
        msg = f"Link-local address not allowed: {ip_obj}"
        raise ValueError(msg)
    if getattr(ip_obj, "is_multicast", False):
        msg = f"Multicast address not allowed: {ip_obj}"
        raise ValueError(msg)
    if getattr(ip_obj, "is_reserved", False):
        msg = f"Reserved IP address not allowed: {ip_obj}"
        raise ValueError(msg)
    if getattr(ip_obj, "is_unspecified", False):
        msg = f"Unspecified address not allowed: {ip_obj}"
        raise ValueError(msg)


def _validate_suspicious_domain_pattern(hostname_lower: str) -> None:
    suspicious_patterns = (".local", ".internal", ".lan", ".corp", ".test", ".invalid")
    for pattern in suspicious_patterns:
        if hostname_lower.endswith(pattern):
            msg = f"Suspicious domain pattern: {pattern}"
            raise ValueError(msg)


def _resolve_hostname_to_addrs(hostname: str, hostname_lower: str) -> list:
    import socket

    cache = _dns_cache.get()
    if cache is not None and hostname_lower in cache:
        return cache[hostname_lower]

    try:
        resolved = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except OSError:
        resolved = []
    if cache is not None:
        cache[hostname_lower] = resolved
    return resolved


def _validate_resolved_addresses(resolved: list, hostname_lower: str) -> None:
    import ipaddress

    for info in resolved:
        try:
            ip_candidate = ipaddress.ip_address(info[4][0])
        except ValueError:
            logger.debug(
                "url_resolved_ip_parse_failed",
                extra={"hostname": hostname_lower, "candidate": str(info[4][0])},
            )
            continue
        if (
            ip_candidate.is_private
            or ip_candidate.is_loopback
            or ip_candidate.is_link_local
            or ip_candidate.is_multicast
            or ip_candidate.is_reserved
            or ip_candidate.is_unspecified
        ):
            msg = f"Hostname resolves to blocked IP address: {ip_candidate}"
            raise ValueError(msg)


def normalize_url(url: str) -> str:
    """Normalize a URL for deduplication as per SPEC.md.

    - Lowercase scheme & host
    - Strip fragment
    - Sort query params and remove common tracking params
    - Collapse trailing slash

    Args:
        url: URL to normalize

    Returns:
        Normalized URL string

    Raises:
        ValueError: If URL is invalid or uses disallowed scheme

    Security:
        - Only allows http:// and https:// schemes
        - Rejects file://, javascript:, data:, and other dangerous schemes
        - Validates hostname presence
        - Checks for malicious content patterns

    """
    # First pass validation - catches obvious security issues
    _validate_url_input(url)

    # Add protocol if missing (only http or https)
    if "://" not in url:
        url = f"http://{url}"

    try:
        p = urlparse(url)

        # Validate parsed components
        if not p.netloc:
            msg = "Invalid URL: missing hostname"
            raise ValueError(msg)

        # Security: strict scheme validation
        # Reject if scheme exists but is not in allowed list
        if p.scheme:
            scheme_lower = p.scheme.lower()
            # Explicitly check against dangerous schemes first
            if scheme_lower in _DANGEROUS_SCHEMES:
                msg = f"URL scheme '{p.scheme}' is not allowed. Only http and https are supported."
                raise ValueError(msg)
            # Then validate against allowed list
            if scheme_lower not in _ALLOWED_SCHEMES:
                msg = f"Unsupported URL scheme: {p.scheme}. Only http and https are allowed."
                raise ValueError(msg)
            scheme = scheme_lower
        else:
            # If no scheme after parsing, default to http
            scheme = "http"

        # Additional security: validate netloc doesn't contain suspicious characters
        if any(char in p.netloc for char in ["@", "<", ">", '"', "'"]):
            # '@' can be used for credential injection: http://user:pass@malicious.com
            msg = "URL hostname contains suspicious characters"
            raise ValueError(msg)

        netloc = p.netloc.lower()
        path = p.path or "/"

        # Normalize path encoding to prevent false duplicates
        # Decode path first (handles %20, %2F, etc.)
        # Then re-encode consistently using quote()
        # This ensures "hello%20world" and "hello world" both become "hello%20world"
        try:
            # Decode existing encoding
            decoded_path = unquote(path)
            # Re-encode consistently (safe chars: unreserved + /@:)
            # Don't encode / to preserve path structure
            path = quote(decoded_path, safe="/@:")
        except Exception as e:
            # If path encoding fails, use as-is and log warning
            logger.warning(
                "path_encoding_normalization_failed",
                extra={"path": path[:100], "error": str(e)},
            )

        # Remove redundant trailing slash except for root
        if path.endswith("/") and path != "/":
            path = path.rstrip("/")

        # Filter and sort query params (urlencode handles encoding consistently)
        query_pairs = [
            (k, v)
            for k, v in parse_qsl(p.query, keep_blank_values=True)
            if k.lower() not in TRACKING_PARAMS
        ]
        query_pairs.sort(key=lambda x: (x[0], x[1]))
        query = urlencode(query_pairs)

        normalized = urlunparse((scheme, netloc, path, "", query, ""))
        logger.debug("normalize_url", extra={"url": url[:100], "normalized": normalized[:100]})
        return normalized
    except Exception as e:
        logger.exception("url_normalization_failed", extra={"url": url[:100], "error": str(e)})
        msg = f"URL normalization failed: {e}"
        raise ValueError(msg) from e


def url_hash_sha256(normalized_url: str) -> str:
    """Generate SHA256 hash of normalized URL.

    Args:
        normalized_url: Normalized URL string to hash

    Returns:
        Lowercase hexadecimal SHA256 hash (exactly 64 characters)

    Raises:
        ValueError: If normalized_url is empty, invalid, or too long

    Note:
        - Always returns a valid 64-character hexadecimal string
        - Uses UTF-8 encoding
        - Result is suitable for database dedupe_hash field (unique constraint)
        - Validates hash format before returning (defensive programming)
    """
    if not normalized_url or not isinstance(normalized_url, str):
        msg = "Normalized URL is required"
        raise ValueError(msg)

    # Additional validation: ensure URL is not just whitespace
    if not normalized_url.strip():
        msg = "Normalized URL cannot be whitespace-only"
        raise ValueError(msg)

    if len(normalized_url) > 2048:
        msg = "Normalized URL too long"
        raise ValueError(msg)

    try:
        h = hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()

        # Validate hash format (defensive check)
        # SHA256 hash should always be 64 lowercase hex characters
        if len(h) != 64:
            msg = f"Generated hash has invalid length: {len(h)} (expected 64)"
            raise ValueError(msg)

        if not all(c in "0123456789abcdef" for c in h):
            msg = "Generated hash contains non-hexadecimal characters"
            raise ValueError(msg)

        logger.debug("url_hash", extra={"normalized": normalized_url[:100], "sha256": h})
        return h
    except ValueError:
        # Re-raise our validation errors
        raise
    except Exception as e:
        logger.exception("url_hash_failed", extra={"error": str(e)})
        msg = f"URL hashing failed: {e}"
        raise ValueError(msg) from e


def compute_dedupe_hash(url: str) -> str:
    """Compute deduplication hash for a URL.

    This function normalizes the URL and computes its SHA256 hash,
    which is used for identifying duplicate URLs in the database.

    Args:
        url: URL to compute hash for (will be normalized first)

    Returns:
        SHA256 hash of the normalized URL

    Raises:
        ValueError: If URL is invalid
    """
    normalized = normalize_url(url)
    twitter_canonical = canonicalize_twitter_url(normalized)
    return url_hash_sha256(twitter_canonical or normalized)


def looks_like_url(text: str, max_text_length_kb: int = 50) -> bool:
    """Check if text contains what looks like a URL.

    Args:
        text: Text to check for URL patterns
        max_text_length_kb: Maximum text length in kilobytes (default: 50)

    Returns:
        True if text appears to contain a URL, False otherwise

    Note:
        Text length is limited to prevent regex DoS attacks.
        Longer text should be rejected at the message routing level.
    """
    if not text or not isinstance(text, str):
        return False

    # Defense in depth: Limit text length to prevent regex DoS
    # This matches the MAX_TEXT_LENGTH in message_router.py
    max_text_length = max_text_length_kb * 1024
    if len(text) > max_text_length:
        logger.warning(
            "looks_like_url_text_too_long",
            extra={"text_length": len(text), "max_allowed": max_text_length},
        )
        return False

    try:
        # Check for URLs with explicit protocol (https?://)
        ok = bool(_URL_SEARCH_PATTERN.search(text))
        if not ok:
            # Also check for URLs starting with www. (no protocol)
            ok = bool(_WWW_URL_SEARCH_PATTERN.search(text))
        logger.debug("looks_like_url", extra={"text_sample": text[:80], "match": ok})
        return ok
    except Exception as e:
        logger.exception("looks_like_url_failed", extra={"error": str(e)})
        return False


def extract_all_urls(text: str, max_text_length_kb: int = 50) -> list[str]:
    """Extract all URLs from text with optimized performance.

    Args:
        text: Text to extract URLs from
        max_text_length_kb: Maximum text length in kilobytes (default: 50)

    Returns:
        List of validated URLs found in text

    Note:
        Text length is limited to prevent regex DoS attacks.
        Longer text should be rejected at the message routing level.
        URLs are validated and deduplicated before being returned.
    """
    if not text or not isinstance(text, str):
        return []

    # Defense in depth: Limit text length to prevent regex DoS
    # This matches the MAX_TEXT_LENGTH in message_router.py
    max_text_length = max_text_length_kb * 1024
    if len(text) > max_text_length:
        logger.warning(
            "extract_all_urls_text_too_long",
            extra={"text_length": len(text), "max_allowed": max_text_length},
        )
        return []

    try:
        # Find URLs with explicit protocol (https?://)
        urls = _URL_FINDALL_PATTERN.findall(text)

        # Also find URLs starting with www. (no protocol)
        www_urls = _WWW_URL_FINDALL_PATTERN.findall(text)

        # Deduplicate URLs (validation happens later in security checks)
        valid_urls = []
        seen: set[str] = set()

        # Process URLs with explicit protocol first
        for url in urls:
            if url in seen:
                continue
            valid_urls.append(url)
            seen.add(url)

        # Process www. URLs (normalize by adding https://)
        for url in www_urls:
            normalized_url = f"https://{url}"
            # Skip if we already have this URL (with or without protocol)
            if normalized_url in seen or url in seen:
                continue
            valid_urls.append(normalized_url)
            seen.add(normalized_url)

        logger.debug("extract_all_urls", extra={"count": len(valid_urls), "input_len": len(text)})
        return valid_urls
    except Exception as e:
        logger.exception("extract_all_urls_failed", extra={"error": str(e)})
        return []


# YouTube URL patterns
# Ordered from most specific to least specific for optimal matching
_YOUTUBE_PATTERNS = [
    # Standard watch URLs with v= anywhere in query string (handles ?feature=share&v=ID)
    re.compile(
        r"(?:https?://)?(?:(?:www|m)\.)?youtube\.com/watch\?(?:[^&]+&)*v=([a-zA-Z0-9_-]{11})",
        re.IGNORECASE,
    ),
    # Short URLs with optional timestamp
    re.compile(r"(?:https?://)?youtu\.be/([a-zA-Z0-9_-]{11})", re.IGNORECASE),
    # Embed URLs
    re.compile(
        r"(?:https?://)?(?:www\.)?youtube(?:-nocookie)?\.com/embed/([a-zA-Z0-9_-]{11})",
        re.IGNORECASE,
    ),
    # Legacy v URLs
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/v/([a-zA-Z0-9_-]{11})", re.IGNORECASE),
    # Shorts
    re.compile(
        r"(?:https?://)?(?:(?:www|m)\.)?youtube\.com/shorts/([a-zA-Z0-9_-]{11})",
        re.IGNORECASE,
    ),
    # YouTube Music
    re.compile(
        r"(?:https?://)?music\.youtube\.com/watch\?(?:[^&]+&)*v=([a-zA-Z0-9_-]{11})",
        re.IGNORECASE,
    ),
    # Live URLs (same as watch but explicitly listed for clarity)
    re.compile(
        r"(?:https?://)?(?:(?:www|m)\.)?youtube\.com/live/([a-zA-Z0-9_-]{11})",
        re.IGNORECASE,
    ),
]


# Twitter/X URL patterns
_TWITTER_HOSTS: frozenset[str] = frozenset(
    {
        "x.com",
        "twitter.com",
        "www.x.com",
        "www.twitter.com",
        "mobile.x.com",
        "mobile.twitter.com",
    }
)
_TWEET_STATUS_PATH_RE = re.compile(
    r"^/(?P<user>[^/]+)/status/(?P<id>\d+)(?:/.*)?$",
    re.IGNORECASE,
)
_TWEET_I_WEB_STATUS_PATH_RE = re.compile(r"^/i/web/status/(?P<id>\d+)(?:/.*)?$", re.IGNORECASE)
_ARTICLE_PATH_RE = re.compile(r"^/i/article/(?P<id>\d+)(?:/.*)?$", re.IGNORECASE)


def _parse_twitter_url_host_path(url: str) -> tuple[str, str] | None:
    """Parse a URL and return normalized ``(host, path)`` for Twitter matching."""
    if not url or not isinstance(url, str):
        return None
    candidate = url.strip()
    if not candidate:
        return None
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    host = (parsed.hostname or "").lower()
    if not host:
        return None
    path = (parsed.path or "/").rstrip("/") or "/"
    return host, path


def is_twitter_url(url: str) -> bool:
    """Check if URL is a Twitter/X tweet or article.

    Supports:
    - x.com/user/status/ID
    - twitter.com/user/status/ID
    - x.com/i/web/status/ID
    - x.com/i/article/ID
    - mobile.x.com, www.x.com variants

    Args:
        url: URL string to check

    Returns:
        True if URL is a Twitter/X URL, False otherwise
    """
    try:
        return extract_tweet_id(url) is not None or extract_twitter_article_id(url) is not None
    except Exception as e:
        logger.exception("is_twitter_url_failed", extra={"error": str(e), "url": url[:100]})
        return False


def extract_tweet_id(url: str) -> str | None:
    """Extract tweet ID from a Twitter/X status URL.

    Args:
        url: Twitter/X URL

    Returns:
        Tweet ID string or None if not found
    """
    tweet_id = extract_twitter_status_id(url)
    if tweet_id:
        return tweet_id
    parts = extract_twitter_status_parts(url)
    return parts[1] if parts else None


def extract_twitter_status_parts(url: str) -> tuple[str, str] | None:
    """Extract ``(username, tweet_id)`` from a Twitter/X status URL.

    Args:
        url: Twitter/X URL

    Returns:
        Tuple ``(username, tweet_id)`` when matched, else ``None``
    """
    try:
        parsed = _parse_twitter_url_host_path(url)
        if not parsed:
            return None
        host, path = parsed
        if host not in _TWITTER_HOSTS:
            return None
        m = _TWEET_STATUS_PATH_RE.match(path)
        if m:
            return m.group("user"), m.group("id")
        return None
    except Exception as e:
        logger.exception(
            "extract_twitter_status_parts_failed",
            extra={"error": str(e), "url": url[:100]},
        )
        return None


def extract_twitter_status_id(url: str) -> str | None:
    """Extract tweet ID from a Twitter/X status URL.

    Supports:
    - /<user>/status/<id>
    - /i/web/status/<id>
    """
    if not url or not isinstance(url, str):
        return None
    try:
        parts = extract_twitter_status_parts(url)
        if parts:
            return parts[1]
        parsed = _parse_twitter_url_host_path(url)
        if not parsed:
            return None
        host, path = parsed
        if host not in _TWITTER_HOSTS:
            return None
        match = _TWEET_I_WEB_STATUS_PATH_RE.match(path)
        return match.group("id") if match else None
    except Exception:
        return None


def extract_twitter_article_id(url: str) -> str | None:
    """Extract article ID from an X/Twitter article URL.

    Args:
        url: X/Twitter URL

    Returns:
        Article ID string if URL points to an article, else ``None``
    """
    try:
        parsed = _parse_twitter_url_host_path(url)
        if not parsed:
            return None
        host, path = parsed
        if host not in _TWITTER_HOSTS:
            return None
        m = _ARTICLE_PATH_RE.match(path)
        return m.group("id") if m else None
    except Exception:
        return None


def canonicalize_twitter_url(url: str) -> str | None:
    """Canonicalize supported Twitter/X URLs for stable dedupe hashing."""
    tweet_id = extract_twitter_status_id(url)
    if tweet_id:
        return f"https://x.com/i/web/status/{tweet_id}"

    article_id = extract_twitter_article_id(url)
    if article_id:
        return f"https://x.com/i/article/{article_id}"

    return None


def is_twitter_article_url(url: str) -> bool:
    """Check if URL points to an X Article (long-form content).

    Args:
        url: URL string to check

    Returns:
        True if URL is an X Article URL
    """
    return extract_twitter_article_id(url) is not None


def is_youtube_url(url: str) -> bool:
    """Check if URL is a YouTube video.

    Supports various YouTube URL formats:
    - youtube.com/watch?v=VIDEO_ID (with any query parameter order)
    - youtube.com/watch?feature=share&v=VIDEO_ID
    - youtu.be/VIDEO_ID
    - youtube.com/embed/VIDEO_ID
    - youtube-nocookie.com/embed/VIDEO_ID
    - youtube.com/v/VIDEO_ID
    - youtube.com/shorts/VIDEO_ID
    - youtube.com/live/VIDEO_ID
    - m.youtube.com/watch?v=VIDEO_ID (mobile)
    - music.youtube.com/watch?v=VIDEO_ID

    Args:
        url: URL string to check

    Returns:
        True if URL is a YouTube video URL, False otherwise
    """
    if not url or not isinstance(url, str):
        return False

    try:
        # Check against all YouTube patterns
        return any(pattern.search(url) for pattern in _YOUTUBE_PATTERNS)
    except Exception as e:
        logger.exception("is_youtube_url_failed", extra={"error": str(e), "url": url[:100]})
        return False


def extract_youtube_video_id(url: str) -> str | None:
    """Extract YouTube video ID from URL.

    Args:
        url: YouTube URL

    Returns:
        11-character video ID or None if not found

    Examples:
        >>> extract_youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        'dQw4w9WgXcQ'
        >>> extract_youtube_video_id("https://youtu.be/dQw4w9WgXcQ")
        'dQw4w9WgXcQ'
    """
    if not url or not isinstance(url, str):
        return None

    try:
        # Try each pattern
        for pattern in _YOUTUBE_PATTERNS:
            match = pattern.search(url)
            if match:
                video_id = match.group(1)
                # Validate video ID format (11 characters, alphanumeric + - and _)
                if len(video_id) == 11 and re.match(r"^[a-zA-Z0-9_-]{11}$", video_id):
                    logger.debug(
                        "extract_youtube_video_id", extra={"url": url[:100], "video_id": video_id}
                    )
                    return video_id

        logger.debug("extract_youtube_video_id_not_found", extra={"url": url[:100]})
        return None

    except Exception as e:
        logger.exception(
            "extract_youtube_video_id_failed", extra={"error": str(e), "url": url[:100]}
        )
        return None
