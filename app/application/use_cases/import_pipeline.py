"""Background import pipeline for processing uploaded bookmark files."""

from __future__ import annotations

import datetime as _dt
from typing import TYPE_CHECKING, Any

from app.core.logging_utils import get_logger
from app.core.time_utils import UTC
from app.core.url_utils import compute_dedupe_hash, normalize_url
from app.db.models import (
    CollectionItem,
    ImportJob,
    Request,
    Summary,
    SummaryTag,
    Tag,
)

if TYPE_CHECKING:
    from app.domain.services.import_parsers.base import ImportedBookmark
from app.domain.services.tag_service import normalize_tag_name

logger = get_logger(__name__)

# How often to flush progress counters to the DB.
_PROGRESS_FLUSH_INTERVAL = 10


async def process_import(
    job_id: int,
    bookmarks: list[ImportedBookmark],
    user_id: int,
    options: dict[str, Any],
) -> None:
    """Process imported bookmarks in background.

    For each bookmark:
    1. Normalize URL, compute dedupe_hash
    2. Skip if dedupe_hash already exists (duplicate)
    3. Create Request record (type="import", status="completed")
    4. Create a minimal Summary so the item appears in the library
    5. Create/attach tags with source="import"
    6. Optionally add to target collection
    7. Update ImportJob progress counters
    """
    created = 0
    skipped = 0
    failed = 0
    errors: list[dict[str, str]] = []

    try:
        job = ImportJob.get_by_id(job_id)
        job.status = "processing"
        job.total_items = len(bookmarks)
        job.save()

        for idx, bookmark in enumerate(bookmarks, start=1):
            try:
                _process_single_bookmark(
                    bookmark,
                    user_id,
                    options,
                )
                created += 1
            except _DuplicateBookmarkError:
                skipped += 1
            except Exception as exc:
                failed += 1
                errors.append({"url": bookmark.url, "error": str(exc)})
                logger.warning(
                    "import_bookmark_failed",
                    extra={"job_id": job_id, "url": bookmark.url[:200], "error": str(exc)},
                )

            # Flush progress periodically to reduce DB writes.
            if idx % _PROGRESS_FLUSH_INTERVAL == 0:
                _flush_progress(job_id, idx, created, skipped, failed, errors)

        # Determine final status.
        final_status = "failed" if created == 0 and failed > 0 else "completed"

        _flush_progress(
            job_id, len(bookmarks), created, skipped, failed, errors, status=final_status
        )

        logger.info(
            "import_job_finished",
            extra={
                "job_id": job_id,
                "status": final_status,
                "created": created,
                "skipped": skipped,
                "failed": failed,
            },
        )
    except Exception:
        logger.exception("import_job_crashed", extra={"job_id": job_id})
        # Best-effort status update so the job never stays stuck in "processing".
        try:
            _flush_progress(job_id, 0, created, skipped, failed, errors, status="failed")
        except Exception:
            logger.exception("import_job_status_update_failed", extra={"job_id": job_id})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class _DuplicateBookmarkError(Exception):
    """Raised when a bookmark's URL already exists in the database."""


def _process_single_bookmark(
    bookmark: ImportedBookmark,
    user_id: int,
    options: dict[str, Any],
) -> None:
    """Process one bookmark: create Request, Summary, tags, collection link."""
    now = _dt.datetime.now(UTC)

    normalized_url = normalize_url(bookmark.url)
    dedupe_hash = compute_dedupe_hash(bookmark.url)

    # Duplicate check.
    if Request.select().where(Request.dedupe_hash == dedupe_hash).exists():
        raise _DuplicateBookmarkError(dedupe_hash)

    request = Request.create(
        type="import",
        status="completed",
        user_id=user_id,
        input_url=bookmark.url,
        normalized_url=normalized_url,
        dedupe_hash=dedupe_hash,
        content_text=bookmark.notes,
        created_at=bookmark.created_at or now,
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
        created_at=bookmark.created_at or now,
        updated_at=now,
    )

    # Attach tags.
    for raw_tag in bookmark.tags:
        _attach_tag(summary, raw_tag, user_id)

    # Optionally link to a collection.
    target_collection_id = options.get("target_collection_id")
    if target_collection_id is not None:
        CollectionItem.get_or_create(
            collection=target_collection_id,
            summary=summary,
        )


def _attach_tag(summary: Summary, raw_name: str, user_id: int) -> None:
    """Find-or-create a Tag by user + normalized name, then link via SummaryTag."""
    normalized = normalize_tag_name(raw_name)
    if not normalized:
        return

    tag, _created = Tag.get_or_create(
        user_id=user_id,
        normalized_name=normalized,
        defaults={"name": raw_name.strip()},
    )

    SummaryTag.get_or_create(
        summary=summary,
        tag=tag,
        defaults={"source": "import"},
    )


def _flush_progress(
    job_id: int,
    processed: int,
    created: int,
    skipped: int,
    failed: int,
    errors: list[dict[str, str]],
    *,
    status: str | None = None,
) -> None:
    """Persist current counters to the ImportJob row."""
    job = ImportJob.get_by_id(job_id)
    job.processed_items = processed
    job.created_items = created
    job.skipped_items = skipped
    job.failed_items = failed
    job.errors_json = errors
    if status is not None:
        job.status = status
    job.save()
