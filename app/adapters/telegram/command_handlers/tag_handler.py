"""Tag management command handlers (/tag, /untag, /tags).

Lets users manage tags on summaries via Telegram reply commands.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.adapters.telegram.command_handlers.base_handler import HandlerDependenciesMixin
from app.adapters.telegram.command_handlers.decorators import combined_handler
from app.core.logging_utils import get_logger
from app.db.models import Request, Summary, SummaryTag, Tag
from app.domain.services.tag_service import normalize_tag_name, validate_tag_name

if TYPE_CHECKING:
    from app.adapters.telegram.command_handlers.execution_context import (
        CommandExecutionContext,
    )

logger = get_logger(__name__)

_MAX_TAG_SUMMARIES = 10


class TagHandler(HandlerDependenciesMixin):
    """Handle /tag, /untag, and /tags commands."""

    @combined_handler("command_tag", "tag")
    async def handle_tag(self, ctx: CommandExecutionContext) -> None:
        """Handle /tag <name> -- add a tag to the replied-to summary."""
        tag_name = _parse_tag_arg(ctx.text, "/tag")
        if not tag_name:
            await ctx.response_formatter.safe_reply(
                ctx.message,
                "Usage: reply to a summary with /tag <name>",
            )
            return

        valid, error = validate_tag_name(tag_name)
        if not valid:
            await ctx.response_formatter.safe_reply(ctx.message, f"Invalid tag: {error}")
            return

        summary = await _find_summary_from_reply(ctx)
        if summary is None:
            return  # helper already replied with an error

        normalized = normalize_tag_name(tag_name)

        # Find or create the tag for this user
        tag, _created = Tag.get_or_create(
            user=ctx.uid,
            normalized_name=normalized,
            defaults={"name": tag_name.strip()},
        )
        # Restore soft-deleted tag if re-used
        if tag.is_deleted:
            tag.is_deleted = False
            tag.deleted_at = None
            tag.save()

        # Create association (ignore if already exists)
        SummaryTag.get_or_create(
            summary=summary,
            tag=tag,
            defaults={"source": "manual"},
        )

        await ctx.response_formatter.safe_reply(
            ctx.message,
            f"Tagged with #{normalized}",
        )

    @combined_handler("command_untag", "untag")
    async def handle_untag(self, ctx: CommandExecutionContext) -> None:
        """Handle /untag <name> -- remove a tag from the replied-to summary."""
        tag_name = _parse_tag_arg(ctx.text, "/untag")
        if not tag_name:
            await ctx.response_formatter.safe_reply(
                ctx.message,
                "Usage: reply to a summary with /untag <name>",
            )
            return

        summary = await _find_summary_from_reply(ctx)
        if summary is None:
            return

        normalized = normalize_tag_name(tag_name)

        tag = (
            Tag.select()
            .where(
                (Tag.user == ctx.uid)
                & (Tag.normalized_name == normalized)
                & (Tag.is_deleted == False)  # noqa: E712
            )
            .first()
        )
        if tag is None:
            await ctx.response_formatter.safe_reply(
                ctx.message,
                f"Tag #{normalized} not found.",
            )
            return

        deleted_count = (
            SummaryTag.delete()
            .where((SummaryTag.summary == summary) & (SummaryTag.tag == tag))
            .execute()
        )

        if deleted_count == 0:
            await ctx.response_formatter.safe_reply(
                ctx.message,
                f"This summary is not tagged with #{normalized}.",
            )
            return

        await ctx.response_formatter.safe_reply(
            ctx.message,
            f"Removed tag #{normalized}",
        )

    @combined_handler("command_tags", "tags")
    async def handle_tags(self, ctx: CommandExecutionContext) -> None:
        """Handle /tags [name].

        No arguments: list all user tags with counts.
        With argument: list summaries for that tag.
        """
        tag_name = _parse_tag_arg(ctx.text, "/tags")

        if tag_name:
            await self._list_tag_summaries(ctx, tag_name)
        else:
            await self._list_all_tags(ctx)

    async def _list_all_tags(self, ctx: CommandExecutionContext) -> None:
        """List all user tags with summary counts."""
        import peewee

        tags = (
            Tag.select(
                Tag.normalized_name,
                peewee.fn.COUNT(SummaryTag.id).alias("cnt"),
            )
            .join(SummaryTag, peewee.JOIN.LEFT_OUTER)
            .where(
                (Tag.user == ctx.uid) & (Tag.is_deleted == False)  # noqa: E712
            )
            .group_by(Tag.id)
            .order_by(peewee.fn.COUNT(SummaryTag.id).desc())
        )

        lines: list[str] = []
        for row in tags:
            lines.append(f"#{row.normalized_name} ({row.cnt})")

        if not lines:
            await ctx.response_formatter.safe_reply(
                ctx.message,
                "No tags yet. Reply to a summary with /tag <name> to create one.",
            )
            return

        text = "Your tags:\n" + "\n".join(lines)
        await ctx.response_formatter.safe_reply(ctx.message, text)

    async def _list_tag_summaries(self, ctx: CommandExecutionContext, tag_name: str) -> None:
        """List summaries for a specific tag."""
        normalized = normalize_tag_name(tag_name)

        tag = (
            Tag.select()
            .where(
                (Tag.user == ctx.uid)
                & (Tag.normalized_name == normalized)
                & (Tag.is_deleted == False)  # noqa: E712
            )
            .first()
        )
        if tag is None:
            await ctx.response_formatter.safe_reply(
                ctx.message,
                f"Tag #{normalized} not found.",
            )
            return

        summaries = (
            Summary.select(Summary, Request)
            .join(SummaryTag)
            .where(SummaryTag.tag == tag)
            .switch(Summary)
            .join(Request)
            .order_by(Summary.created_at.desc())
            .limit(_MAX_TAG_SUMMARIES)
        )

        lines: list[str] = []
        for s in summaries:
            payload = s.json_payload or {}
            title = payload.get("title", "Untitled")
            url = s.request.input_url or s.request.normalized_url or ""
            if url:
                lines.append(f"- {title}\n  {url}")
            else:
                lines.append(f"- {title}")

        if not lines:
            await ctx.response_formatter.safe_reply(
                ctx.message,
                f"No summaries tagged with #{normalized}.",
            )
            return

        text = f"Summaries tagged #{normalized}:\n\n" + "\n".join(lines)
        await ctx.response_formatter.safe_reply(ctx.message, text)


def _parse_tag_arg(text: str, command: str) -> str | None:
    """Extract the argument after the command prefix, e.g. '/tag ml' -> 'ml'."""
    rest = text[len(command) :].strip()
    return rest if rest else None


async def _find_summary_from_reply(ctx: CommandExecutionContext) -> Summary | None:
    """Look up the summary from the message the user replied to.

    Returns None and sends an error reply if no summary is found.
    """
    reply = getattr(ctx.message, "reply_to_message", None)
    if reply is None:
        await ctx.response_formatter.safe_reply(
            ctx.message,
            "Reply to a summary message to use this command.",
        )
        return None

    reply_msg_id = getattr(reply, "id", None) or getattr(reply, "message_id", None)
    if reply_msg_id is None:
        await ctx.response_formatter.safe_reply(
            ctx.message,
            "Could not identify the replied message.",
        )
        return None

    # Look up by bot_reply_message_id first, then fallback to input_message_id
    try:
        summary = (
            Summary.select()
            .join(Request)
            .where((Request.bot_reply_message_id == reply_msg_id) & (Request.user_id == ctx.uid))
            .first()
        )
        if summary is None:
            summary = (
                Summary.select()
                .join(Request)
                .where((Request.input_message_id == reply_msg_id) & (Request.user_id == ctx.uid))
                .first()
            )
    except Exception:
        summary = None

    if summary is None:
        await ctx.response_formatter.safe_reply(
            ctx.message,
            "No summary found for that message. Reply to a summary message.",
        )
        return None

    return summary
