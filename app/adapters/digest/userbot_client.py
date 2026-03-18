"""Pyrogram userbot client for reading Telegram channel histories."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from app.core.logging_utils import get_logger
from app.core.time_utils import UTC

if TYPE_CHECKING:
    from pathlib import Path

    from app.config import AppConfig

logger = get_logger(__name__)


class UserbotClient:
    """Thin wrapper around a Pyrogram userbot session for channel reading.

    Uses the same API credentials as the main bot but authenticates as a user
    (no bot_token) so it can read channel histories via get_chat_history().
    """

    def __init__(self, cfg: AppConfig, session_dir: Path) -> None:
        self._cfg = cfg
        self._session_dir = session_dir
        self._client: Any = None  # pyrogram.Client

    async def start(self) -> None:
        """Start the userbot Pyrogram session.

        Raises:
            FileNotFoundError: If the session file does not exist.
                The user must run ``/init_session`` first.
        """
        from pyrogram import Client

        session_path = self._session_dir / self._cfg.digest.session_name
        session_file = session_path.with_suffix(".session")
        if not session_file.exists():
            msg = (
                f"Userbot session file not found: {session_file}\n"
                "Run /init_session first to authenticate the userbot."
            )
            raise FileNotFoundError(msg)

        self._client = Client(
            name=str(session_path),
            api_id=self._cfg.telegram.api_id,
            api_hash=self._cfg.telegram.api_hash,
            # No bot_token -- this is a user session
        )
        await self._client.start()
        logger.info("digest_userbot_started", extra={"session": self._cfg.digest.session_name})

    async def stop(self) -> None:
        """Stop the userbot Pyrogram session."""
        if self._client:
            await self._client.stop()
            self._client = None
            logger.info("digest_userbot_stopped")

    async def fetch_channel_posts(
        self,
        channel_username: str,
        hours_lookback: int = 24,
        min_length: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch recent posts from a public channel.

        Args:
            channel_username: Channel username (without @).
            hours_lookback: How many hours back to fetch.
            min_length: Minimum text length to include a post.

        Returns:
            List of post dicts with keys: message_id, text, date, views,
            forwards, media_type, url.
        """
        if not self._client:
            msg = "UserbotClient not started"
            raise RuntimeError(msg)

        cutoff = datetime.now(UTC) - timedelta(hours=hours_lookback)
        posts: list[dict[str, Any]] = []

        try:
            async for message in self._client.get_chat_history(channel_username):
                msg_date = message.date
                if msg_date and msg_date.tzinfo is None:
                    msg_date = msg_date.replace(tzinfo=UTC)

                if msg_date and msg_date < cutoff:
                    break  # Messages are in reverse chronological order

                text = message.text or message.caption or ""
                if len(text) < min_length:
                    continue

                media_type = None
                if message.photo:
                    media_type = "photo"
                elif message.video:
                    media_type = "video"
                elif message.document:
                    media_type = "document"
                elif message.audio:
                    media_type = "audio"

                posts.append(
                    {
                        "message_id": message.id,
                        "text": text,
                        "date": msg_date,
                        "views": getattr(message, "views", None),
                        "forwards": getattr(message, "forwards", None),
                        "media_type": media_type,
                        "url": f"https://t.me/{channel_username}/{message.id}",
                    }
                )

        except Exception:
            logger.exception(
                "digest_fetch_channel_failed",
                extra={"channel": channel_username},
            )
            raise

        logger.info(
            "digest_channel_posts_fetched",
            extra={"channel": channel_username, "count": len(posts)},
        )
        return posts

    async def resolve_channel(self, username: str) -> dict[str, Any]:
        """Resolve a Telegram channel by username and return its metadata.

        Returns:
            Dict with keys: username, title, description, member_count.

        Raises:
            ValueError: If the channel cannot be found.
        """
        if not self._client:
            msg = "UserbotClient not started"
            raise RuntimeError(msg)

        try:
            chat = await self._client.get_chat(username)
        except Exception as exc:
            logger.warning(
                "digest_resolve_channel_failed",
                extra={"channel": username, "error": str(exc)},
            )
            msg = f"Could not resolve channel @{username}"
            raise ValueError(msg) from exc

        return {
            "username": getattr(chat, "username", username) or username,
            "title": getattr(chat, "title", None),
            "description": getattr(chat, "description", None),
            "member_count": getattr(chat, "members_count", None),
        }

    @property
    def is_connected(self) -> bool:
        """Check if the userbot client is currently connected."""
        return self._client is not None and self._client.is_connected
