"""SQLite implementation of tag repository.

This adapter handles persistence for user tags and summary-tag associations.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import peewee

from app.core.logging_utils import get_logger
from app.core.time_utils import UTC
from app.db.models import Request, Summary, SummaryTag, Tag, model_to_dict
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository

logger = get_logger(__name__)


class SqliteTagRepositoryAdapter(SqliteBaseRepository):
    """Adapter for tag CRUD and summary-tag association operations."""

    async def async_get_user_tags(self, user_id: int) -> list[dict[str, Any]]:
        """Return all non-deleted tags owned by a user, with summary counts."""

        def _query() -> list[dict[str, Any]]:
            count_subq = SummaryTag.select(peewee.fn.COUNT(SummaryTag.id)).where(
                SummaryTag.tag == Tag.id
            )
            rows = (
                Tag.select(Tag, count_subq.alias("summary_count"))
                .where((Tag.user == user_id) & (Tag.is_deleted == False))  # noqa: E712
                .order_by(Tag.created_at.asc())
            )
            result: list[dict[str, Any]] = []
            for row in rows:
                d = model_to_dict(row)
                if d is not None:
                    d["summary_count"] = row.summary_count
                    result.append(d)
            return result

        return await self._execute(_query, operation_name="get_user_tags", read_only=True)

    async def async_get_tag_by_id(self, tag_id: int) -> dict[str, Any] | None:
        """Return tag by ID."""

        def _query() -> dict[str, Any] | None:
            try:
                tag = Tag.get_by_id(tag_id)
            except Tag.DoesNotExist:
                return None
            return model_to_dict(tag)

        return await self._execute(_query, operation_name="get_tag_by_id", read_only=True)

    async def async_create_tag(
        self,
        user_id: int,
        name: str,
        normalized_name: str,
        color: str | None,
    ) -> dict[str, Any]:
        """Create a tag and return the created record."""

        def _insert() -> dict[str, Any]:
            tag = Tag.create(
                user=user_id,
                name=name,
                normalized_name=normalized_name,
                color=color,
            )
            d = model_to_dict(tag)
            assert d is not None
            d["summary_count"] = 0
            return d

        return await self._execute(_insert, operation_name="create_tag")

    async def async_update_tag(
        self,
        tag_id: int,
        name: str | None,
        color: str | None,
    ) -> dict[str, Any]:
        """Update a tag and return the updated record."""

        def _update() -> dict[str, Any]:
            tag = Tag.get_by_id(tag_id)
            if name is not None:
                tag.name = name
                from app.domain.services.tag_service import normalize_tag_name

                tag.normalized_name = normalize_tag_name(name)
            if color is not None:
                tag.color = color
            tag.save()
            d = model_to_dict(tag)
            assert d is not None
            return d

        return await self._execute(_update, operation_name="update_tag")

    async def async_delete_tag(self, tag_id: int) -> None:
        """Soft-delete a tag."""

        def _delete() -> None:
            Tag.update(
                {
                    Tag.is_deleted: True,
                    Tag.deleted_at: datetime.now(UTC),
                }
            ).where(Tag.id == tag_id).execute()

        await self._execute(_delete, operation_name="delete_tag")

    async def async_attach_tag(
        self,
        summary_id: int,
        tag_id: int,
        source: str,
    ) -> dict[str, Any]:
        """Attach a tag to a summary. Ignore if already exists."""

        def _attach() -> dict[str, Any]:
            try:
                st = SummaryTag.create(
                    summary=summary_id,
                    tag=tag_id,
                    source=source,
                )
            except peewee.IntegrityError:
                st = SummaryTag.get((SummaryTag.summary == summary_id) & (SummaryTag.tag == tag_id))
            d = model_to_dict(st)
            assert d is not None
            return d

        return await self._execute(_attach, operation_name="attach_tag")

    async def async_detach_tag(self, summary_id: int, tag_id: int) -> None:
        """Detach a tag from a summary."""

        def _detach() -> None:
            SummaryTag.delete().where(
                (SummaryTag.summary == summary_id) & (SummaryTag.tag == tag_id)
            ).execute()

        await self._execute(_detach, operation_name="detach_tag")

    async def async_restore_tag(self, tag_id: int, *, name: str | None = None) -> dict[str, Any]:
        """Restore a previously soft-deleted tag."""

        def _restore() -> dict[str, Any]:
            tag = Tag.get_by_id(tag_id)
            tag.is_deleted = False
            tag.deleted_at = None
            if name is not None:
                tag.name = name
            tag.save()
            d = model_to_dict(tag)
            assert d is not None
            return d

        return await self._execute(_restore, operation_name="restore_tag")

    async def async_get_tags_for_summary(self, summary_id: int) -> list[dict[str, Any]]:
        """Return all tags attached to a summary with source info."""

        def _query() -> list[dict[str, Any]]:
            rows = (
                Tag.select(Tag, SummaryTag.source, SummaryTag.created_at.alias("attached_at"))
                .join(SummaryTag, on=(SummaryTag.tag == Tag.id))
                .where(
                    (SummaryTag.summary == summary_id) & (Tag.is_deleted == False)  # noqa: E712
                )
                .order_by(SummaryTag.created_at.asc())
            )
            result: list[dict[str, Any]] = []
            for row in rows:
                d = model_to_dict(row)
                if d is not None:
                    d["source"] = row.summarytag.source
                    d["attached_at"] = row.attached_at
                    result.append(d)
            return result

        return await self._execute(_query, operation_name="get_tags_for_summary", read_only=True)

    async def async_get_tagged_summaries(
        self,
        *,
        user_id: int,
        tag_id: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Return recent summaries for a tag owned by the user."""

        def _query() -> list[dict[str, Any]]:
            rows = (
                Summary.select(Summary, Request)
                .join(SummaryTag)
                .where(SummaryTag.tag == tag_id)
                .switch(Summary)
                .join(Request)
                .where(
                    (Request.user_id == user_id) & (Summary.is_deleted == False)  # noqa: E712
                )
                .order_by(Summary.created_at.desc())
                .limit(limit)
            )
            result: list[dict[str, Any]] = []
            for row in rows:
                data = model_to_dict(row) or {}
                if hasattr(row, "request") and row.request is not None:
                    data["request"] = model_to_dict(row.request)
                result.append(data)
            return result

        return await self._execute(_query, operation_name="get_tagged_summaries", read_only=True)

    async def async_merge_tags(self, source_tag_ids: list[int], target_tag_id: int) -> None:
        """Merge source tags into target: re-point associations, soft-delete sources."""

        def _merge() -> None:
            # Re-point SummaryTag rows, skipping duplicates
            for src_id in source_tag_ids:
                existing_summary_ids = {
                    st.summary_id
                    for st in SummaryTag.select(SummaryTag.summary).where(
                        SummaryTag.tag == target_tag_id
                    )
                }
                SummaryTag.update({SummaryTag.tag: target_tag_id}).where(
                    (SummaryTag.tag == src_id) & (SummaryTag.summary.not_in(existing_summary_ids))
                ).execute()
                # Delete remaining duplicates
                SummaryTag.delete().where(SummaryTag.tag == src_id).execute()

            # Soft-delete source tags
            now = datetime.now(UTC)
            Tag.update({Tag.is_deleted: True, Tag.deleted_at: now}).where(
                Tag.id.in_(source_tag_ids)
            ).execute()

        await self._execute(_merge, operation_name="merge_tags")

    async def async_get_tag_by_normalized_name(
        self,
        user_id: int,
        normalized_name: str,
        *,
        include_deleted: bool = False,
    ) -> dict[str, Any] | None:
        """Return tag by normalized name within a user scope."""

        def _query() -> dict[str, Any] | None:
            query = Tag.select().where(
                (Tag.user == user_id) & (Tag.normalized_name == normalized_name)
            )
            if not include_deleted:
                query = query.where(Tag.is_deleted == False)  # noqa: E712
            tag = query.first()
            if tag is None:
                return None
            return model_to_dict(tag)

        return await self._execute(
            _query, operation_name="get_tag_by_normalized_name", read_only=True
        )
