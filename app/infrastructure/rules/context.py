"""SQLAlchemy-backed rule evaluation context builder."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.application.dto.rule_execution import RuleEvaluationContextDTO
from app.db.models import Request, Summary, SummaryTag, Tag
from app.domain.services.summary_context import build_summary_context

if TYPE_CHECKING:
    from app.db.session import Database


class SqliteRuleContextAdapter:
    """Build a rule evaluation context from event payloads and persisted records."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def async_build_context(self, event_data: dict[str, Any]) -> RuleEvaluationContextDTO:
        summary_snapshot: dict[str, Any] | None = None
        summary_id = event_data.get("summary_id")

        summary_dict: dict[str, Any] | None = None
        request_dict: dict[str, Any] | None = None
        tag_names: list[str] | None = None

        if summary_id is not None:
            async with self._database.session() as session:
                summary = await session.get(Summary, summary_id)
                if summary is not None:
                    summary_dict = {
                        "json_payload": summary.json_payload or {},
                        "lang": summary.lang,
                    }

                    request = await session.get(Request, summary.request_id)
                    if request is not None:
                        request_dict = {
                            "normalized_url": request.normalized_url,
                            "input_url": request.input_url,
                        }

                    tag_names = list(
                        await session.scalars(
                            select(Tag.normalized_name)
                            .join(SummaryTag, SummaryTag.tag_id == Tag.id)
                            .where(SummaryTag.summary_id == summary_id)
                        )
                    )

                    summary_snapshot = {
                        "id": summary.id,
                        "lang": summary.lang,
                        "is_read": summary.is_read,
                        "is_favorited": summary.is_favorited,
                        "created_at": str(summary.created_at),
                    }

        context = build_summary_context(summary_dict, request_dict, tag_names)

        for key in ("url", "title", "language", "source_type", "content"):
            if event_data.get(key):
                context[key] = event_data[key]
        if event_data.get("tags"):
            context["tags"] = event_data["tags"]
        if event_data.get("reading_time"):
            context["reading_time"] = event_data["reading_time"]

        return RuleEvaluationContextDTO(**context, summary_snapshot=summary_snapshot)
