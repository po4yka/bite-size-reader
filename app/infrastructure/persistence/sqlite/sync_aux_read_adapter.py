"""Auxiliary sync reads that still rely on ORM joins."""

from __future__ import annotations

from typing import Any


class SqliteSyncAuxReadAdapter:
    def get_highlights_for_user(self, user_id: int) -> list[dict[str, Any]]:
        from app.db.models import SummaryHighlight, model_to_dict

        rows = SummaryHighlight.select().where(SummaryHighlight.user == user_id)
        return [d for row in rows if (d := model_to_dict(row)) is not None]

    def get_tags_for_user(self, user_id: int) -> list[dict[str, Any]]:
        from app.db.models import Tag, model_to_dict

        rows = Tag.select().where(Tag.user == user_id)
        return [d for row in rows if (d := model_to_dict(row)) is not None]

    def get_summary_tags_for_user(self, user_id: int) -> list[dict[str, Any]]:
        from app.db.models import Request, Summary, SummaryTag, model_to_dict

        rows = (
            SummaryTag.select()
            .join(Summary, on=(SummaryTag.summary == Summary.id))
            .join(Request, on=(Summary.request == Request.id))
            .where(Request.user_id == user_id)
        )
        return [d for row in rows if (d := model_to_dict(row)) is not None]
