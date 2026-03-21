"""Pure business logic for webhook HMAC signing, secret generation, URL validation, and payload building."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from ipaddress import ip_address
from urllib.parse import urlparse


def generate_webhook_secret() -> str:
    """Generate a 32-byte hex secret for HMAC signing."""
    return secrets.token_hex(32)


def sign_payload(secret: str, payload_bytes: bytes) -> str:
    """Sign payload with HMAC-SHA256. Returns hex digest."""
    return hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()


def verify_signature(secret: str, payload_bytes: bytes, signature: str) -> bool:
    """Verify HMAC-SHA256 signature using constant-time comparison."""
    expected = sign_payload(secret, payload_bytes)
    return hmac.compare_digest(expected, signature)


def validate_webhook_url(url: str) -> tuple[bool, str | None]:
    """Validate webhook URL.

    Rejects non-HTTPS (except localhost), empty hostnames, and private IPs.
    Returns ``(is_valid, error_message_or_none)``.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Malformed URL"

    scheme = (parsed.scheme or "").lower()
    hostname = (parsed.hostname or "").lower()

    if not hostname:
        return False, "Hostname is empty"

    # Scheme check: https always allowed; http only for localhost
    is_localhost = hostname in ("localhost", "127.0.0.1", "::1")
    if scheme == "http" and not is_localhost:
        return False, "Only HTTPS URLs are allowed (HTTP permitted for localhost only)"
    if scheme not in ("http", "https"):
        return False, f"Unsupported scheme: {scheme}"

    # Port validation
    if parsed.port is not None and not (1 <= parsed.port <= 65535):
        return False, f"Invalid port: {parsed.port}"

    # If hostname looks like an IP address, reject private/reserved ranges
    try:
        addr = ip_address(hostname)
        if addr.is_private or addr.is_reserved or addr.is_loopback:
            # Allow loopback only when scheme is http (localhost exception above)
            if not (addr.is_loopback and is_localhost):
                return False, "Private or reserved IP addresses are not allowed"
    except ValueError:
        # Not an IP literal -- that's fine, it's a regular hostname
        pass

    return True, None


def build_webhook_payload(
    event_type: str,
    data: dict,
    delivery_id: int | None = None,
) -> dict:
    """Build standardized webhook payload envelope."""
    return {
        "event": event_type,
        "timestamp": datetime.now(UTC).isoformat(),
        "delivery_id": delivery_id,
        "data": data,
    }
