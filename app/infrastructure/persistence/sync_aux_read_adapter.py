"""Auxiliary SQLAlchemy reads for sync records."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.db.models import Request, Summary, SummaryHighlight, SummaryTag, Tag, model_to_dict

if TYPE_CHECKING:
    from app.db.session import Database


class SyncAuxReadAdapter:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def get_highlights_for_user(self, user_id: int) -> list[dict[str, Any]]:
        async with self._database.session() as session:
            rows = (
                await session.execute(
                    select(SummaryHighlight).where(SummaryHighlight.user_id == user_id)
                )
            ).scalars()
            return [model_to_dict(row) or {} for row in rows]

    async def get_tags_for_user(self, user_id: int) -> list[dict[str, Any]]:
        async with self._database.session() as session:
            rows = (
                await session.execute(select(Tag).where(Tag.user_id == user_id))
            ).scalars()
            return [model_to_dict(row) or {} for row in rows]

    async def get_summary_tags_for_user(self, user_id: int) -> list[dict[str, Any]]:
        async with self._database.session() as session:
            rows = (
                await session.execute(
                    select(SummaryTag)
                    .join(Summary, SummaryTag.summary_id == Summary.id)
                    .join(Request, Summary.request_id == Request.id)
                    .where(Request.user_id == user_id)
                )
            ).scalars()
            return [model_to_dict(row) or {} for row in rows]
