"""Export command handler (/export).

Lets users export all their summaries as JSON, CSV, or HTML file.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

from app.adapters.telegram.command_handlers.base_handler import HandlerDependenciesMixin
from app.adapters.telegram.command_handlers.decorators import combined_handler
from app.core.logging_utils import get_logger
from app.db.models import Request, Summary, SummaryTag, Tag
from app.domain.services.import_export.export_serializers import (
    CsvExporter,
    JsonExporter,
    NetscapeHtmlExporter,
)

if TYPE_CHECKING:
    from app.adapters.telegram.command_handlers.execution_context import (
        CommandExecutionContext,
    )

logger = get_logger(__name__)

_VALID_FORMATS = {"json", "csv", "html"}
_DEFAULT_FORMAT = "json"

_MIME_TYPES = {
    "json": "application/json",
    "csv": "text/csv",
    "html": "text/html",
}

_FILE_EXTENSIONS = {
    "json": "json",
    "csv": "csv",
    "html": "html",
}


class ExportHandler(HandlerDependenciesMixin):
    """Handle /export command."""

    @combined_handler("command_export", "export", include_text=True)
    async def handle_export(self, ctx: CommandExecutionContext) -> None:
        """Handle /export [json|csv|html] -- export all summaries as a file."""
        fmt = _parse_format(ctx.text)

        summaries = _query_user_summaries(ctx.uid)

        if not summaries:
            await ctx.response_formatter.safe_reply(
                ctx.message,
                "No summaries to export.",
            )
            return

        summary_dicts = [_summary_to_dict(s) for s in summaries]

        if fmt == "json":
            content = JsonExporter.serialize(summary_dicts)
        elif fmt == "csv":
            content = CsvExporter.serialize(summary_dicts)
        else:
            content = NetscapeHtmlExporter.serialize(summary_dicts)

        filename = f"summaries.{_FILE_EXTENSIONS[fmt]}"
        file_bytes = content.encode("utf-8")
        buf = io.BytesIO(file_bytes)
        buf.name = filename

        try:
            await ctx.message.reply_document(
                document=buf,
                file_name=filename,
            )
        except Exception:
            logger.exception(
                "export_send_failed",
                extra={"uid": ctx.uid, "format": fmt},
            )
            await ctx.response_formatter.safe_reply(
                ctx.message,
                "Failed to send the export file. Please try again.",
            )


def _parse_format(text: str) -> str:
    """Extract format argument from command text, defaulting to json."""
    parts = text.strip().split()
    if len(parts) >= 2:
        candidate = parts[1].lower()
        if candidate in _VALID_FORMATS:
            return candidate
    return _DEFAULT_FORMAT


def _query_user_summaries(uid: int) -> list:
    """Query all summaries for a user, ordered by creation date."""
    return list(
        Summary.select(Summary, Request)
        .join(Request)
        .where(Request.user_id == uid)
        .order_by(Summary.created_at.desc())
    )


def _summary_to_dict(summary: Summary) -> dict:
    """Convert a Summary ORM object to a dict suitable for exporters."""
    payload = summary.json_payload or {}
    url = ""
    if hasattr(summary, "request"):
        url = summary.request.input_url or summary.request.normalized_url or ""

    tags: list[str] = []
    try:
        tag_rows = (
            Tag.select(Tag.normalized_name).join(SummaryTag).where(SummaryTag.summary == summary)
        )
        tags = [t.normalized_name for t in tag_rows]
    except Exception:
        pass

    return {
        "url": url,
        "title": payload.get("title", "Untitled"),
        "tags": tags,
        "language": payload.get("language", ""),
        "created_at": str(summary.created_at) if summary.created_at else "",
        "is_read": getattr(summary, "is_read", False),
        "is_favorited": getattr(summary, "is_favorited", False),
        "summary_json": payload,
    }
