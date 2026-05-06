"""PostgreSQL-backed backup archive workflows."""

from __future__ import annotations

import asyncio
import json
import os
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import select, update

from app.core.logging_utils import get_logger
from app.core.time_utils import UTC
from app.db.models import (
    Collection,
    CollectionItem,
    Request,
    Summary,
    SummaryHighlight,
    SummaryTag,
    Tag,
    User,
    UserBackup,
    model_to_dict,
)
from app.db.types import _utcnow

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.db.session import Database

logger = get_logger(__name__)


def _database(db: Database | None) -> Database:
    if db is not None:
        return db

    from app.api.dependencies.database import get_session_manager

    return get_session_manager()


def _resolve_data_dir(data_dir: str | None) -> Path:
    return Path(data_dir or os.getenv("DATA_DIR", "/data"))


def _dump_rows(rows: Sequence[object]) -> list[dict[str, Any]]:
    return [row for row in (model_to_dict(item) for item in rows) if row is not None]


def _read_json(archive: zipfile.ZipFile, name: str) -> Any:
    return json.loads(archive.read(name))


def _old_id(row: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = row.get(key)
        if value is not None:
            return int(value)
    return None


async def async_create_backup_archive(
    user_id: int,
    backup_id: int,
    *,
    db: Database | None = None,
    data_dir: str | None = None,
) -> None:
    """Create a ZIP backup of all user data."""
    database = _database(db)
    backup_dir = _resolve_data_dir(data_dir) / "backups" / str(user_id)

    try:
        async with database.transaction() as session:
            await session.execute(
                update(UserBackup)
                .where(UserBackup.id == backup_id)
                .values(status="processing", updated_at=_utcnow())
            )

            user_row = await session.get(User, user_id)
            if user_row is None:
                msg = f"User {user_id} not found"
                raise ValueError(msg)
            preferences = user_row.preferences_json

            requests_rows = list(
                (
                    await session.execute(
                        select(Request)
                        .where(Request.user_id == user_id)
                        .order_by(Request.created_at.asc())
                    )
                )
                .scalars()
                .all()
            )
            requests_data = _dump_rows(requests_rows)

            summaries_rows = list(
                (
                    await session.execute(
                        select(Summary)
                        .join(Request, Summary.request_id == Request.id)
                        .where(Request.user_id == user_id, Summary.is_deleted.is_(False))
                    )
                )
                .scalars()
                .all()
            )
            summary_ids = [summary.id for summary in summaries_rows]
            summaries_data = _dump_rows(summaries_rows)

            tags_rows = list(
                (
                    await session.execute(
                        select(Tag).where(Tag.user_id == user_id, Tag.is_deleted.is_(False))
                    )
                )
                .scalars()
                .all()
            )
            tag_ids = [tag.id for tag in tags_rows]
            tags_data = _dump_rows(tags_rows)

            summary_tags_rows = (
                list(
                    (
                        await session.execute(
                            select(SummaryTag).where(
                                SummaryTag.summary_id.in_(summary_ids),
                                SummaryTag.tag_id.in_(tag_ids),
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                if summary_ids and tag_ids
                else []
            )
            summary_tags_data = _dump_rows(summary_tags_rows)

            collections_rows = list(
                (
                    await session.execute(
                        select(Collection).where(
                            Collection.user_id == user_id,
                            Collection.is_deleted.is_(False),
                        )
                    )
                )
                .scalars()
                .all()
            )
            collection_ids = [collection.id for collection in collections_rows]
            collections_data = _dump_rows(collections_rows)

            collection_items_rows = (
                list(
                    (
                        await session.execute(
                            select(CollectionItem).where(
                                CollectionItem.collection_id.in_(collection_ids)
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                if collection_ids
                else []
            )
            collection_items_data = _dump_rows(collection_items_rows)

            highlights_rows = list(
                (
                    await session.execute(
                        select(SummaryHighlight).where(SummaryHighlight.user_id == user_id)
                    )
                )
                .scalars()
                .all()
            )
            highlights_data = _dump_rows(highlights_rows)

            items_count = (
                len(summaries_data) + len(tags_data) + len(collections_data) + len(highlights_data)
            )
            manifest = {
                "version": "1.0",
                "user_id": user_id,
                "created_at": datetime.now(UTC).isoformat(),
                "counts": {
                    "requests": len(requests_data),
                    "summaries": len(summaries_data),
                    "tags": len(tags_data),
                    "summary_tags": len(summary_tags_data),
                    "collections": len(collections_data),
                    "collection_items": len(collection_items_data),
                    "highlights": len(highlights_data),
                },
            }

        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        zip_path = backup_dir / f"ratatoskr-backup-{user_id}-{timestamp}.zip"

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, default=str, indent=2))
            archive.writestr("requests.json", json.dumps(requests_data, default=str))
            archive.writestr("summaries.json", json.dumps(summaries_data, default=str))
            archive.writestr("tags.json", json.dumps(tags_data, default=str))
            archive.writestr("summary_tags.json", json.dumps(summary_tags_data, default=str))
            archive.writestr("collections.json", json.dumps(collections_data, default=str))
            archive.writestr("collection_items.json", json.dumps(collection_items_data, default=str))
            archive.writestr("highlights.json", json.dumps(highlights_data, default=str))
            archive.writestr(
                "preferences.json",
                json.dumps(preferences, default=str) if preferences else "{}",
            )

        file_size = zip_path.stat().st_size
        async with database.transaction() as session:
            await session.execute(
                update(UserBackup)
                .where(UserBackup.id == backup_id)
                .values(
                    file_path=str(zip_path),
                    file_size_bytes=file_size,
                    items_count=items_count,
                    status="completed",
                    updated_at=_utcnow(),
                )
            )
        logger.info(
            "backup_created",
            extra={
                "backup_id": backup_id,
                "user_id": user_id,
                "file_size": file_size,
                "items_count": items_count,
            },
        )
    except Exception as exc:
        logger.exception(
            "backup_creation_failed",
            extra={"backup_id": backup_id, "user_id": user_id, "error": str(exc)},
        )
        async with database.transaction() as session:
            await session.execute(
                update(UserBackup)
                .where(UserBackup.id == backup_id)
                .values(status="failed", error=str(exc)[:1000], updated_at=_utcnow())
            )


async def async_restore_from_archive(
    user_id: int,
    zip_bytes: bytes,
    *,
    db: Database | None = None,
) -> dict[str, Any]:
    """Restore user data from a backup ZIP and return a summary."""
    restored: dict[str, int] = {
        "requests": 0,
        "summaries": 0,
        "tags": 0,
        "summary_tags": 0,
        "collections": 0,
        "collection_items": 0,
        "highlights": 0,
    }
    skipped: dict[str, int] = {
        "requests": 0,
        "summaries": 0,
        "tags": 0,
        "collections": 0,
    }
    errors: list[str] = []

    try:
        with zipfile.ZipFile(BytesIO(zip_bytes), "r") as archive:
            manifest = _read_json(archive, "manifest.json")
            archive_version = manifest.get("version", "unknown")
            if archive_version not in ("1.0",):
                return {
                    "restored": restored,
                    "skipped": skipped,
                    "errors": [f"Unsupported backup version: {archive_version}"],
                }

            requests_data = _read_json(archive, "requests.json")
            summaries_data = _read_json(archive, "summaries.json")
            tags_data = _read_json(archive, "tags.json")
            summary_tags_data = _read_json(archive, "summary_tags.json")
            collections_data = _read_json(archive, "collections.json")
            collection_items_data = _read_json(archive, "collection_items.json")
            highlights_data = _read_json(archive, "highlights.json")

        database = _database(db)
        async with database.transaction() as session:
            request_id_map: dict[int, int] = {}
            summary_id_map: dict[int, int] = {}
            tag_id_map: dict[int, int] = {}
            collection_id_map: dict[int, int] = {}

            for request in requests_data:
                try:
                    dedupe = request.get("dedupe_hash")
                    old_request_id = int(request["id"])
                    if dedupe:
                        existing = await session.scalar(
                            select(Request).where(
                                Request.user_id == user_id,
                                Request.dedupe_hash == dedupe,
                            )
                        )
                        if existing:
                            request_id_map[old_request_id] = existing.id
                            skipped["requests"] += 1
                            continue

                    new_request = Request(
                        type=request.get("type", "url"),
                        status=request.get("status", "completed"),
                        user_id=user_id,
                        input_url=request.get("input_url"),
                        normalized_url=request.get("normalized_url"),
                        dedupe_hash=request.get("dedupe_hash"),
                        lang_detected=request.get("lang_detected"),
                    )
                    session.add(new_request)
                    await session.flush()
                    request_id_map[old_request_id] = new_request.id
                    restored["requests"] += 1
                except Exception as exc:
                    errors.append(f"request {request.get('id')}: {exc}")

            for summary in summaries_data:
                try:
                    old_request_id = _old_id(summary, "request_id", "request")
                    new_request_id = request_id_map.get(old_request_id or -1)
                    if new_request_id is None:
                        skipped["summaries"] += 1
                        continue

                    existing_summary = await session.scalar(
                        select(Summary).where(Summary.request_id == new_request_id)
                    )
                    old_summary_id = int(summary["id"])
                    if existing_summary:
                        summary_id_map[old_summary_id] = existing_summary.id
                        skipped["summaries"] += 1
                        continue

                    new_summary = Summary(
                        request_id=new_request_id,
                        lang=summary.get("lang", "en"),
                        json_payload=summary.get("json_payload"),
                        is_read=bool(summary.get("is_read", False)),
                        is_deleted=bool(summary.get("is_deleted", False)),
                    )
                    session.add(new_summary)
                    await session.flush()
                    summary_id_map[old_summary_id] = new_summary.id
                    restored["summaries"] += 1
                except Exception as exc:
                    errors.append(f"summary {summary.get('id')}: {exc}")

            for tag in tags_data:
                try:
                    normalized_name = tag.get("normalized_name") or tag.get("name", "").strip().lower()
                    existing_tag = await session.scalar(
                        select(Tag).where(
                            Tag.user_id == user_id,
                            Tag.normalized_name == normalized_name,
                            Tag.is_deleted.is_(False),
                        )
                    )
                    old_tag_id = int(tag["id"])
                    if existing_tag:
                        tag_id_map[old_tag_id] = existing_tag.id
                        skipped["tags"] += 1
                        continue
                    new_tag = Tag(
                        user_id=user_id,
                        name=tag.get("name", normalized_name),
                        normalized_name=normalized_name,
                        color=tag.get("color"),
                    )
                    session.add(new_tag)
                    await session.flush()
                    tag_id_map[old_tag_id] = new_tag.id
                    restored["tags"] += 1
                except Exception as exc:
                    errors.append(f"tag {tag.get('id')}: {exc}")

            for summary_tag in summary_tags_data:
                try:
                    new_summary_id = summary_id_map.get(
                        _old_id(summary_tag, "summary_id", "summary") or -1
                    )
                    new_tag_id = tag_id_map.get(_old_id(summary_tag, "tag_id", "tag") or -1)
                    if new_summary_id is None or new_tag_id is None:
                        continue
                    existing = await session.scalar(
                        select(SummaryTag).where(
                            SummaryTag.summary_id == new_summary_id,
                            SummaryTag.tag_id == new_tag_id,
                        )
                    )
                    if existing is not None:
                        continue
                    session.add(
                        SummaryTag(
                            summary_id=new_summary_id,
                            tag_id=new_tag_id,
                            source=summary_tag.get("source", "manual"),
                        )
                    )
                    await session.flush()
                    restored["summary_tags"] += 1
                except Exception as exc:
                    errors.append(f"summary_tag {summary_tag.get('id')}: {exc}")

            for collection in collections_data:
                try:
                    existing_collection = await session.scalar(
                        select(Collection).where(
                            Collection.user_id == user_id,
                            Collection.name == collection.get("name"),
                            Collection.is_deleted.is_(False),
                        )
                    )
                    old_collection_id = int(collection["id"])
                    if existing_collection:
                        collection_id_map[old_collection_id] = existing_collection.id
                        skipped["collections"] += 1
                        continue
                    new_collection = Collection(
                        user_id=user_id,
                        name=collection.get("name", "Imported collection"),
                        description=collection.get("description"),
                        position=collection.get("position"),
                        collection_type=collection.get("collection_type", "manual"),
                        query_conditions_json=collection.get("query_conditions_json"),
                        query_match_mode=collection.get("query_match_mode", "all"),
                    )
                    session.add(new_collection)
                    await session.flush()
                    collection_id_map[old_collection_id] = new_collection.id
                    restored["collections"] += 1
                except Exception as exc:
                    errors.append(f"collection {collection.get('id')}: {exc}")

            for item in collection_items_data:
                try:
                    new_collection_id = collection_id_map.get(
                        _old_id(item, "collection_id", "collection") or -1
                    )
                    new_summary_id = summary_id_map.get(_old_id(item, "summary_id", "summary") or -1)
                    if new_collection_id is None or new_summary_id is None:
                        continue
                    existing = await session.scalar(
                        select(CollectionItem).where(
                            CollectionItem.collection_id == new_collection_id,
                            CollectionItem.summary_id == new_summary_id,
                        )
                    )
                    if existing is not None:
                        continue
                    session.add(
                        CollectionItem(
                            collection_id=new_collection_id,
                            summary_id=new_summary_id,
                            position=item.get("position"),
                        )
                    )
                    await session.flush()
                    restored["collection_items"] += 1
                except Exception as exc:
                    errors.append(f"collection_item {item.get('id')}: {exc}")

            for highlight in highlights_data:
                try:
                    new_summary_id = summary_id_map.get(
                        _old_id(highlight, "summary_id", "summary") or -1
                    )
                    if new_summary_id is None:
                        continue
                    session.add(
                        SummaryHighlight(
                            user_id=user_id,
                            summary_id=new_summary_id,
                            text=highlight.get("text", ""),
                            start_offset=highlight.get("start_offset"),
                            end_offset=highlight.get("end_offset"),
                            color=highlight.get("color"),
                            note=highlight.get("note"),
                        )
                    )
                    restored["highlights"] += 1
                except Exception as exc:
                    errors.append(f"highlight {highlight.get('id')}: {exc}")
    except KeyError as exc:
        errors.append(f"Missing required file in backup archive: {exc}")
    except zipfile.BadZipFile:
        errors.append("Invalid or corrupt ZIP archive")
    except Exception as exc:
        errors.append(str(exc))

    return {"restored": restored, "skipped": skipped, "errors": errors}


def create_backup_archive(
    user_id: int,
    backup_id: int,
    *,
    db: Database | None = None,
    data_dir: str | None = None,
) -> None:
    """Synchronous compatibility wrapper for backup archive creation."""
    asyncio.run(
        async_create_backup_archive(
            user_id=user_id,
            backup_id=backup_id,
            db=db,
            data_dir=data_dir,
        )
    )


def restore_from_archive(
    user_id: int,
    zip_bytes: bytes,
    *,
    db: Database | None = None,
) -> dict[str, Any]:
    """Synchronous compatibility wrapper for backup archive restore."""
    return asyncio.run(async_restore_from_archive(user_id=user_id, zip_bytes=zip_bytes, db=db))
