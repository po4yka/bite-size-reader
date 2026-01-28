from __future__ import annotations

import hashlib
import logging
import re
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlparse, urlunparse

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
    if not url:
        msg = "URL cannot be empty"
        raise ValueError(msg)
    if not isinstance(url, str):
        msg = "URL must be a string"
        raise ValueError(msg)
    if len(url) > 2048:  # RFC 2616 limit
        msg = "URL too long"
        raise ValueError(msg)

    # Basic security: no obvious injection attempts
    url_lower = url.lower()
    if any(needle in url_lower for needle in _DANGEROUS_URL_SUBSTRINGS):
        msg = "URL contains potentially dangerous content"
        raise ValueError(msg)

    # Check for dangerous schemes early (before parsing)
    # This catches schemes even if they're not properly formatted
    for dangerous_scheme in _DANGEROUS_SCHEMES:
        if url_lower.startswith(f"{dangerous_scheme}:"):
            msg = f"URL scheme '{dangerous_scheme}' is not allowed"
            raise ValueError(msg)

    # Additional validation: check for null bytes and control characters
    if "\x00" in url:
        msg = "URL contains null bytes"
        raise ValueError(msg)
    if any(ord(char) < 32 and char not in ("\t", "\n", "\r") for char in url):
        msg = "URL contains control characters"
        raise ValueError(msg)

    # SSRF Protection: Validate hostname and IP addresses
    # Import here to avoid circular dependencies
    import ipaddress
    import socket

    try:
        # Parse URL to extract hostname for IP validation
        parsed = urlparse(url if "://" in url else f"http://{url}")
        hostname = parsed.hostname or parsed.netloc

        if hostname:
            hostname_lower = hostname.lower()

            # Block localhost variants (additional to loopback IP check)
            if hostname_lower in ("localhost", "localhost.localdomain"):
                msg = "Localhost access not allowed"
                raise ValueError(msg)

            # Try to parse as IP address
            ip_obj = None
            try:
                ip_obj = ipaddress.ip_address(hostname)
            except ValueError:
                # Not a valid IP address - will check domain patterns below
                pass

            if ip_obj is not None:
                # Valid IP address - check if it's blocked
                # Block all private IP ranges (RFC 1918: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
                # Also blocks RFC 4193 IPv6 private (fc00::/7)
                if ip_obj.is_private:
                    msg = f"Private IP address not allowed: {ip_obj}"
                    raise ValueError(msg)

                # Block loopback (127.0.0.0/8, ::1)
                if ip_obj.is_loopback:
                    msg = f"Loopback address not allowed: {ip_obj}"
                    raise ValueError(msg)

                # Block link-local (169.254.0.0/16, fe80::/10)
                if ip_obj.is_link_local:
                    msg = f"Link-local address not allowed: {ip_obj}"
                    raise ValueError(msg)

                # Block multicast (224.0.0.0/4, ff00::/8)
                if ip_obj.is_multicast:
                    msg = f"Multicast address not allowed: {ip_obj}"
                    raise ValueError(msg)

                # Block reserved IPs
                if ip_obj.is_reserved:
                    msg = f"Reserved IP address not allowed: {ip_obj}"
                    raise ValueError(msg)

                # Block unspecified (0.0.0.0, ::)
                if ip_obj.is_unspecified:
                    msg = f"Unspecified address not allowed: {ip_obj}"
                    raise ValueError(msg)
            else:
                # Not a valid IP - check for suspicious domain patterns (internal networks)
                suspicious_patterns = (
                    ".local",
                    ".internal",
                    ".lan",
                    ".corp",
                    ".test",
                    ".invalid",
                )
                for pattern in suspicious_patterns:
                    if hostname_lower.endswith(pattern):
                        msg = f"Suspicious domain pattern: {pattern}"
                        raise ValueError(msg)

                # Resolve hostname to IPs and block if any resolve to private ranges
                try:
                    resolved = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
                except OSError:
                    resolved = []
                for info in resolved:
                    try:
                        ip_candidate = ipaddress.ip_address(info[4][0])
                    except ValueError:
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
    return url_hash_sha256(normalized)


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
