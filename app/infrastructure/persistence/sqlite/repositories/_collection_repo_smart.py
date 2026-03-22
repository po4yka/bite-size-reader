"""Smart-collection query helpers for the SQLite collection repository."""

from __future__ import annotations

from app.db.models import Collection, Request, Summary, model_to_dict

from ._repository_mixin_base import SqliteRepositoryMixinBase


class CollectionRepositorySmartMixin(SqliteRepositoryMixinBase):
    """Smart-collection listing and summary query helpers."""

    async def async_list_smart_collections_for_user(self, user_id: int) -> list[dict]:
        """Return all smart collections for a user."""

        def _list() -> list[dict]:
            query = (
                Collection.select()
                .where(
                    (Collection.user_id == user_id)
                    & (Collection.collection_type == "smart")
                    & (~Collection.is_deleted)
                )
                .order_by(Collection.created_at)
            )
            return [model_to_dict(collection) or {} for collection in query]

        return await self._execute(
            _list, operation_name="list_smart_collections_for_user", read_only=True
        )

    async def async_list_user_summaries_with_request(
        self, user_id: int, limit: int = 10000
    ) -> list[dict]:
        """List all non-deleted summaries for a user with request data."""

        def _list() -> list[dict]:
            query = (
                Summary.select(Summary, Request)
                .join(Request)
                .where((Request.user_id == user_id) & (~Summary.is_deleted))
                .order_by(Summary.created_at.desc())
                .limit(limit)
            )
            results = []
            for row in query:
                summary_dict = model_to_dict(row) or {}
                request_dict = model_to_dict(row.request) if hasattr(row, "request") else {}
                results.append({"summary": summary_dict, "request": request_dict})
            return results

        return await self._execute(
            _list, operation_name="list_user_summaries_with_request", read_only=True
        )
