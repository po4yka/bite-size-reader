"""SQLite repository for user-owned goals, digests, highlights, and exports."""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.db.models import (
    Collection,
    CollectionItem,
    CustomDigest,
    Request,
    Summary,
    SummaryHighlight,
    SummaryTag,
    Tag,
    UserGoal,
    model_to_dict,
)
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository


class SqliteUserContentRepositoryAdapter(SqliteBaseRepository):
    """Owns SQLite access for user-content features outside the core summary flow."""

    async def async_list_goals(self, user_id: int) -> list[dict[str, Any]]:
        def _query() -> list[dict[str, Any]]:
            rows = UserGoal.select().where(UserGoal.user == user_id)
            return [model_to_dict(row) or {} for row in rows]

        return await self._execute(_query, operation_name="list_user_goals", read_only=True)

    async def async_upsert_goal(
        self,
        *,
        user_id: int,
        goal_type: str,
        scope_type: str,
        scope_id: int | None,
        target_count: int,
    ) -> dict[str, Any]:
        def _upsert() -> dict[str, Any]:
            goal, created = UserGoal.get_or_create(
                user=user_id,
                goal_type=goal_type,
                scope_type=scope_type,
                scope_id=scope_id,
                defaults={"id": uuid.uuid4(), "target_count": target_count},
            )
            if not created:
                goal.target_count = target_count
                goal.save()
            return model_to_dict(goal) or {}

        return await self._execute(_upsert, operation_name="upsert_user_goal")

    async def async_delete_global_goal(self, *, user_id: int, goal_type: str) -> int:
        def _delete() -> int:
            return (
                UserGoal.delete()
                .where(
                    (UserGoal.user == user_id)
                    & (UserGoal.goal_type == goal_type)
                    & (UserGoal.scope_type == "global")
                )
                .execute()
            )

        return await self._execute(_delete, operation_name="delete_global_user_goal")

    async def async_delete_goal_by_id(self, *, user_id: int, goal_id: str) -> int:
        def _delete() -> int:
            return (
                UserGoal.delete()
                .where((UserGoal.user == user_id) & (UserGoal.id == goal_id))
                .execute()
            )

        return await self._execute(_delete, operation_name="delete_user_goal_by_id")

    async def async_get_scope_name(
        self,
        *,
        user_id: int,
        scope_type: str,
        scope_id: int | None,
    ) -> str | None:
        def _query() -> str | None:
            if scope_type == "tag" and scope_id is not None:
                tag = Tag.get_or_none(
                    (Tag.id == scope_id) & (Tag.user == user_id) & (~Tag.is_deleted)
                )
                return tag.name if tag else None
            if scope_type == "collection" and scope_id is not None:
                collection = Collection.get_or_none(
                    (Collection.id == scope_id)
                    & (Collection.user == user_id)
                    & (~Collection.is_deleted)
                )
                return collection.name if collection else None
            return None

        return await self._execute(_query, operation_name="get_goal_scope_name", read_only=True)

    async def async_count_scoped_summaries_in_period(
        self,
        *,
        user_id: int,
        start: Any,
        end: Any,
        scope_type: str,
        scope_id: int | None,
    ) -> int:
        def _query() -> int:
            query = (
                Summary.select()
                .join(Request, on=(Summary.request == Request.id))
                .where(
                    (Request.user_id == user_id)
                    & (Summary.created_at >= start)
                    & (Summary.created_at < end)
                    & (~Summary.is_deleted)
                )
            )
            if scope_type == "tag" and scope_id is not None:
                query = query.switch(Summary).join(SummaryTag).where(SummaryTag.tag == scope_id)
            elif scope_type == "collection" and scope_id is not None:
                query = (
                    query.switch(Summary)
                    .join(CollectionItem)
                    .where(CollectionItem.collection == scope_id)
                )
            return query.count()

        return await self._execute(
            _query,
            operation_name="count_scoped_summaries_in_period",
            read_only=True,
        )

    async def async_get_owned_summaries(
        self,
        *,
        user_id: int,
        summary_ids: list[int],
    ) -> list[dict[str, Any]]:
        def _query() -> list[dict[str, Any]]:
            if not summary_ids:
                return []
            rows = (
                Summary.select(Summary, Request)
                .join(Request)
                .where(
                    Summary.id.in_(summary_ids),
                    Request.user_id == user_id,
                    Summary.is_deleted == False,  # noqa: E712
                )
            )
            results: list[dict[str, Any]] = []
            for row in rows:
                item = model_to_dict(row) or {}
                item["request"] = model_to_dict(row.request) or {}
                results.append(item)
            return results

        return await self._execute(_query, operation_name="get_owned_summaries", read_only=True)

    async def async_create_custom_digest(
        self,
        *,
        user_id: int,
        title: str,
        summary_ids: list[int],
        format: str,
        content: str,
    ) -> dict[str, Any]:
        def _insert() -> dict[str, Any]:
            digest = CustomDigest.create(
                id=uuid.uuid4(),
                user=user_id,
                title=title,
                summary_ids=json.dumps([str(item) for item in summary_ids]),
                format=format,
                content=content,
                status="ready",
            )
            return model_to_dict(digest) or {}

        return await self._execute(_insert, operation_name="create_custom_digest")

    async def async_list_custom_digests(self, user_id: int) -> list[dict[str, Any]]:
        def _query() -> list[dict[str, Any]]:
            rows = (
                CustomDigest.select()
                .where(CustomDigest.user == user_id)
                .order_by(CustomDigest.created_at.desc())
            )
            return [model_to_dict(row) or {} for row in rows]

        return await self._execute(_query, operation_name="list_custom_digests", read_only=True)

    async def async_get_custom_digest(self, digest_id: str) -> dict[str, Any] | None:
        def _query() -> dict[str, Any] | None:
            try:
                digest = CustomDigest.get_by_id(digest_id)
            except CustomDigest.DoesNotExist:
                return None
            return model_to_dict(digest)

        return await self._execute(_query, operation_name="get_custom_digest", read_only=True)

    async def async_get_owned_summary(
        self,
        *,
        user_id: int,
        summary_id: int,
    ) -> dict[str, Any] | None:
        def _query() -> dict[str, Any] | None:
            row = (
                Summary.select(Summary, Request)
                .join(Request)
                .where((Summary.id == summary_id) & (Request.user_id == user_id))
                .first()
            )
            if row is None:
                return None
            item = model_to_dict(row) or {}
            item["request"] = model_to_dict(row.request) or {}
            return item

        return await self._execute(_query, operation_name="get_owned_summary", read_only=True)

    async def async_list_highlights(
        self,
        *,
        user_id: int,
        summary_id: int,
    ) -> list[dict[str, Any]]:
        def _query() -> list[dict[str, Any]]:
            rows = (
                SummaryHighlight.select()
                .where(
                    (SummaryHighlight.user == user_id) & (SummaryHighlight.summary == summary_id)
                )
                .order_by(SummaryHighlight.created_at.asc())
            )
            return [model_to_dict(row) or {} for row in rows]

        return await self._execute(_query, operation_name="list_summary_highlights", read_only=True)

    async def async_create_highlight(
        self,
        *,
        user_id: int,
        summary_id: int,
        text: str,
        start_offset: int,
        end_offset: int,
        color: str | None,
        note: str | None,
    ) -> dict[str, Any]:
        def _insert() -> dict[str, Any]:
            highlight = SummaryHighlight.create(
                id=uuid.uuid4(),
                user=user_id,
                summary=summary_id,
                text=text,
                start_offset=start_offset,
                end_offset=end_offset,
                color=color,
                note=note,
            )
            return model_to_dict(highlight) or {}

        return await self._execute(_insert, operation_name="create_summary_highlight")

    async def async_get_highlight(
        self,
        *,
        user_id: int,
        summary_id: int,
        highlight_id: str,
    ) -> dict[str, Any] | None:
        def _query() -> dict[str, Any] | None:
            highlight = SummaryHighlight.get_or_none(
                (SummaryHighlight.id == highlight_id)
                & (SummaryHighlight.user == user_id)
                & (SummaryHighlight.summary == summary_id)
            )
            return model_to_dict(highlight)

        return await self._execute(_query, operation_name="get_summary_highlight", read_only=True)

    async def async_update_highlight(
        self,
        *,
        highlight_id: str,
        color: str | None,
        note: str | None,
    ) -> dict[str, Any]:
        def _update() -> dict[str, Any]:
            highlight = SummaryHighlight.get_by_id(highlight_id)
            if color is not None:
                highlight.color = color
            if note is not None:
                highlight.note = note
            highlight.save()
            return model_to_dict(highlight) or {}

        return await self._execute(_update, operation_name="update_summary_highlight")

    async def async_delete_highlight(self, highlight_id: str) -> None:
        def _delete() -> None:
            SummaryHighlight.delete().where(SummaryHighlight.id == highlight_id).execute()

        await self._execute(_delete, operation_name="delete_summary_highlight")

    async def async_export_summaries(
        self,
        *,
        user_id: int,
        tag: str | None,
        collection_id: int | None,
    ) -> list[dict[str, Any]]:
        def _query() -> list[dict[str, Any]]:
            query = (
                Summary.select(Summary, Request)
                .join(Request, on=(Summary.request == Request.id))
                .where((Request.user == user_id) & (Summary.is_deleted == False))  # noqa: E712
            )

            if tag:
                tag_obj = (
                    Tag.select()
                    .where(
                        (Tag.user == user_id) & (Tag.name == tag) & (Tag.is_deleted == False)  # noqa: E712
                    )
                    .first()
                )
                if tag_obj:
                    tagged_summary_ids = [
                        summary_tag.summary_id
                        for summary_tag in SummaryTag.select(SummaryTag.summary).where(
                            SummaryTag.tag == tag_obj.id
                        )
                    ]
                    query = query.where(Summary.id.in_(tagged_summary_ids))
                else:
                    return []

            if collection_id is not None:
                collection_summary_ids = [
                    item.summary_id
                    for item in CollectionItem.select(CollectionItem.summary).where(
                        CollectionItem.collection == collection_id
                    )
                ]
                query = query.where(Summary.id.in_(collection_summary_ids))

            summaries: list[dict[str, Any]] = []
            for row in query:
                summary_dict = model_to_dict(row)
                if summary_dict is None:
                    continue

                request = row.request
                summary_dict["url"] = request.input_url or request.normalized_url or ""
                summary_dict["title"] = ""
                json_payload = summary_dict.get("json_payload")
                if isinstance(json_payload, dict):
                    summary_dict["title"] = json_payload.get("title", "")

                tag_rows = (
                    Tag.select(Tag.name)
                    .join(SummaryTag, on=(SummaryTag.tag == Tag.id))
                    .where((SummaryTag.summary == row.id) & (Tag.is_deleted == False))  # noqa: E712
                )
                summary_dict["tags"] = [{"name": tag_row.name} for tag_row in tag_rows]

                collection_rows = (
                    Collection.select(Collection.name)
                    .join(CollectionItem, on=(CollectionItem.collection == Collection.id))
                    .where(
                        (CollectionItem.summary == row.id) & (Collection.is_deleted == False)  # noqa: E712
                    )
                )
                summary_dict["collections"] = [
                    {"name": collection.name} for collection in collection_rows
                ]
                summaries.append(summary_dict)

            return summaries

        return await self._execute(_query, operation_name="export_query", read_only=True)
