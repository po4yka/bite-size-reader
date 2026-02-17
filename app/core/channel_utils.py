from __future__ import annotations

import re

CHANNEL_USERNAME_RE: re.Pattern[str] = re.compile(r"^[a-z][a-z0-9_]{4,31}$")

TELEGRAM_LINK_RE: re.Pattern[str] = re.compile(
    r"^(?:https?://)?(?:t\.me|telegram\.me)/([A-Za-z0-9_]+)/?$"
)


def parse_channel_input(raw: str) -> tuple[str | None, str | None]:
    """Parse and validate a Telegram channel username or link."""
    text = raw.strip()
    if not text:
        return None, "Please provide a channel name."

    link_match = TELEGRAM_LINK_RE.match(text)
    username = link_match.group(1) if link_match else text

    username = username.lstrip("@").lower()

    if not CHANNEL_USERNAME_RE.match(username):
        return None, (
            f"Invalid channel username '{username}'. "
            "Must be 5-32 characters, start with a letter, "
            "and contain only letters, digits, or underscores."
        )

    return username, None
