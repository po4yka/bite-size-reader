"""Transactional SQLite bookmark import adapter."""

from __future__ import annotations

import datetime as _dt
from typing import TYPE_CHECKING, Any

from app.application.dto.import_bookmarks import BookmarkImportItemResult
from app.core.time_utils import UTC
from app.core.url_utils import compute_dedupe_hash, normalize_url
from app.db.models import Collection, CollectionItem, Request, Summary, SummaryTag, Tag
from app.domain.services.tag_service import normalize_tag_name
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository

if TYPE_CHECKING:
    from app.domain.services.import_parsers.base import ImportedBookmark


class SqliteBookmarkImportAdapter(SqliteBaseRepository):
    """Import one bookmark and all derived records in a single transaction."""

    async def async_import_bookmark(
        self,
        bookmark: ImportedBookmark,
        *,
        user_id: int,
        options: dict[str, Any],
    ) -> BookmarkImportItemResult:
        """Persist a bookmark and its linked summary/tag records."""

        def _import() -> BookmarkImportItemResult:
            now = _dt.datetime.now(UTC)
            created_at = bookmark.created_at or now
            normalized_url = normalize_url(bookmark.url)
            dedupe_hash = compute_dedupe_hash(normalized_url)

            if Request.select().where(Request.dedupe_hash == dedupe_hash).exists():
                return BookmarkImportItemResult(url=bookmark.url, outcome="skipped")

            request = Request.create(
                type="import",
                status="completed",
                user_id=user_id,
                input_url=bookmark.url,
                normalized_url=normalized_url,
                dedupe_hash=dedupe_hash,
                content_text=bookmark.notes,
                created_at=created_at,
                updated_at=now,
                server_version=int(now.timestamp() * 1000),
            )

            summary = Summary.create(
                request=request,
                json_payload={
                    "title": bookmark.title or bookmark.url,
                    "summary_250": bookmark.notes or "",
                    "topic_tags": bookmark.tags,
                },
                lang=None,
                server_version=int(now.timestamp() * 1000),
                created_at=created_at,
                updated_at=now,
            )

            for raw_tag in bookmark.tags:
                normalized = normalize_tag_name(raw_tag)
                if not normalized:
                    continue
                tag, _ = Tag.get_or_create(
                    user_id=user_id,
                    normalized_name=normalized,
                    defaults={"name": raw_tag.strip()},
                )
                SummaryTag.get_or_create(
                    summary=summary,
                    tag=tag,
                    defaults={"source": "import"},
                )

            target_collection_id = options.get("target_collection_id")
            if target_collection_id is not None:
                collection = Collection.get_or_none(
                    (Collection.id == target_collection_id) & (Collection.user == user_id)
                )
                if collection is None:
                    msg = f"collection {target_collection_id} not found or not owned by user"
                    raise ValueError(msg)
                CollectionItem.get_or_create(collection=collection, summary=summary)

            return BookmarkImportItemResult(url=bookmark.url, outcome="created")

        return await self._execute_transaction(
            _import,
            operation_name="import_bookmark",
        )
