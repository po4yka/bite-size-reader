"""Message security validation."""

from __future__ import annotations

import asyncio
import re
import time


class MessageValidatorImpl:
    """Implementation of message security validation."""

    def __init__(self, min_message_interval_ms: int = 100) -> None:
        """Initialize the validator with configuration.

        Args:
            min_message_interval_ms: Minimum delay between messages in milliseconds.
        """
        self._min_message_interval_ms = min_message_interval_ms
        self._last_message_time: float = 0.0

    def is_safe_content(self, text: str) -> tuple[bool, str]:
        """Validate content for security issues."""
        # Check for suspicious patterns
        suspicious_patterns = [
            r"<script[^>]*>.*?</script>",
            r"javascript:",
            r"vbscript:",
            r"on\w+\s*=",
            r"alert\(",
            r"confirm\(",
            r"prompt\(",
        ]

        for pattern in suspicious_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return False, f"Suspicious script content detected: {pattern}"

        # Check for dangerous control characters (non-printable ASCII except common ones)
        # Allow: \n (10), \r (13), \t (9) - these are common in text formatting
        dangerous_control_chars = [
            0,  # Null
            1,  # Start of Heading
            2,  # Start of Text
            3,  # End of Text
            4,  # End of Transmission
            5,  # Enquiry
            6,  # Acknowledge
            7,  # Bell
            8,  # Backspace
            11,  # Vertical Tab
            12,  # Form Feed
            14,  # Shift Out
            15,  # Shift In
            16,  # Data Link Escape
            17,  # Device Control 1
            18,  # Device Control 2
            19,  # Device Control 3
            20,  # Device Control 4
            21,  # Negative Acknowledge
            22,  # Synchronous Idle
            23,  # End of Transmission Block
            24,  # Cancel
            25,  # End of Medium
            26,  # Substitute
            27,  # Escape
            28,  # File Separator
            29,  # Group Separator
            30,  # Record Separator
            31,  # Unit Separator
        ]
        dangerous_chars = sum(1 for c in text if ord(c) in dangerous_control_chars)
        if dangerous_chars > 0:
            return False, f"Dangerous control characters detected: {dangerous_chars} found"

        # Check for extremely long lines (potential buffer overflow)
        # Replace newlines with spaces for length checking
        text_for_length_check = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")
        if len(text_for_length_check) > 10000:  # Very long content is suspicious
            return False, f"Content too long: {len(text_for_length_check)} characters"

        return True, ""

    def validate_url(self, url: str) -> tuple[bool, str]:
        """Validate URL for security using consolidated validation from url_utils.

        This method wraps the comprehensive _validate_url_input() function from
        app/core/url_utils.py, which provides:
        - Length limits (RFC 2616)
        - Dangerous content patterns
        - Scheme validation (only http/https)
        - SSRF protection (private IPs, loopback, link-local, etc.)
        - Suspicious domain patterns
        - Control characters and null bytes

        Returns:
            tuple[bool, str]: (is_valid, error_message)
        """
        from app.core.url_utils import _validate_url_input

        try:
            # Use consolidated validation from url_utils
            _validate_url_input(url)
            return True, ""
        except ValueError as e:
            # Validation failed - return error message
            return False, str(e)

    async def check_rate_limit(self) -> bool:
        """Ensure replies respect the minimum delay between Telegram messages."""
        current_time = time.time() * 1000  # Convert to milliseconds
        elapsed = current_time - self._last_message_time

        if elapsed < self._min_message_interval_ms:
            await asyncio.sleep((self._min_message_interval_ms - elapsed) / 1000)
            current_time = time.time() * 1000
            self._last_message_time = current_time
            return False

        self._last_message_time = current_time
        return True
