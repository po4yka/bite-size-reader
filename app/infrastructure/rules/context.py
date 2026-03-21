"""SQLite-backed rule evaluation context builder."""

from __future__ import annotations

from typing import Any

from app.application.dto.rule_execution import RuleEvaluationContextDTO
from app.db.models import Request, Summary, SummaryTag, Tag
from app.domain.services.summary_context import build_summary_context
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository


class SqliteRuleContextAdapter(SqliteBaseRepository):
    """Build a rule evaluation context from event payloads and persisted records."""

    async def async_build_context(self, event_data: dict[str, Any]) -> RuleEvaluationContextDTO:
        def _build() -> RuleEvaluationContextDTO:
            summary_snapshot: dict[str, Any] | None = None
            summary_id = event_data.get("summary_id")

            summary_dict: dict[str, Any] | None = None
            request_dict: dict[str, Any] | None = None
            tag_names: list[str] | None = None

            if summary_id is not None:
                summary = Summary.get_or_none(Summary.id == summary_id)
                if summary is not None:
                    summary_dict = {
                        "json_payload": summary.json_payload or {},
                        "lang": summary.lang,
                    }

                    request = Request.get_or_none(Request.id == summary.request_id)
                    if request is not None:
                        request_dict = {
                            "normalized_url": request.normalized_url,
                            "input_url": request.input_url,
                        }

                    tag_rows = (
                        SummaryTag.select(SummaryTag, Tag)
                        .join(Tag)
                        .where(SummaryTag.summary == summary_id)
                    )
                    tag_names = [row.tag.normalized_name for row in tag_rows]

                    summary_snapshot = {
                        "id": summary.id,
                        "lang": summary.lang,
                        "is_read": summary.is_read,
                        "is_favorited": summary.is_favorited,
                        "created_at": str(summary.created_at),
                    }

            # Build base context from DB-loaded data.
            context = build_summary_context(summary_dict, request_dict, tag_names)

            # Event data takes priority over DB-derived values.
            for key in ("url", "title", "language", "source_type", "content"):
                if event_data.get(key):
                    context[key] = event_data[key]
            if event_data.get("tags"):
                context["tags"] = event_data["tags"]
            if event_data.get("reading_time"):
                context["reading_time"] = event_data["reading_time"]

            return RuleEvaluationContextDTO(**context, summary_snapshot=summary_snapshot)

        return await self._execute(_build, operation_name="build_rule_context", read_only=True)
