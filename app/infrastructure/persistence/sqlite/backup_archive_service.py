"""SQLite-backed backup archive workflows."""

from __future__ import annotations

import contextlib
import json
import os
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.core.logging_utils import get_logger
from app.core.time_utils import UTC

if TYPE_CHECKING:
    from app.db.session import DatabaseSessionManager

logger = get_logger(__name__)


def _resolve_data_dir(data_dir: str | None, db: DatabaseSessionManager | None) -> Path:
    if data_dir:
        return Path(data_dir)
    if db is None:
        msg = "data_dir is required when db is not provided"
        raise ValueError(msg)
    return Path(db.path).parent


def _connection_context(db: DatabaseSessionManager | None) -> Any:
    if db is None:
        return contextlib.nullcontext()
    return db.connection_context()


def create_backup_archive(
    user_id: int,
    backup_id: int,
    *,
    db: DatabaseSessionManager | None = None,
    data_dir: str | None = None,
) -> None:
    """Create a ZIP backup of all user data."""
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

    backup_dir = _resolve_data_dir(data_dir, db) / "backups" / str(user_id)

    with _connection_context(db):
        try:
            UserBackup.update(status="processing").where(UserBackup.id == backup_id).execute()

            user_row = User.get_by_id(user_id)
            preferences = user_row.preferences_json

            requests_rows = list(
                Request.select().where(Request.user == user_id).order_by(Request.created_at.asc())
            )
            requests_data = [model_to_dict(row) for row in requests_rows]

            summaries_rows = list(
                Summary.select()
                .join(Request, on=(Summary.request == Request.id))
                .where((Request.user == user_id) & (Summary.is_deleted == False))  # noqa: E712
            )
            summary_ids = [summary.id for summary in summaries_rows]
            summaries_data = [model_to_dict(row) for row in summaries_rows]

            tags_rows = list(
                Tag.select().where((Tag.user == user_id) & (Tag.is_deleted == False))  # noqa: E712
            )
            tag_ids = [tag.id for tag in tags_rows]
            tags_data = [model_to_dict(row) for row in tags_rows]

            summary_tags_rows = (
                list(
                    SummaryTag.select().where(
                        (SummaryTag.summary.in_(summary_ids)) & (SummaryTag.tag.in_(tag_ids))
                    )
                )
                if summary_ids and tag_ids
                else []
            )
            summary_tags_data = [model_to_dict(row) for row in summary_tags_rows]

            collections_rows = list(
                Collection.select().where(
                    (Collection.user == user_id) & (Collection.is_deleted == False)  # noqa: E712
                )
            )
            collection_ids = [collection.id for collection in collections_rows]
            collections_data = [model_to_dict(row) for row in collections_rows]

            collection_items_rows = (
                list(CollectionItem.select().where(CollectionItem.collection.in_(collection_ids)))
                if collection_ids
                else []
            )
            collection_items_data = [model_to_dict(row) for row in collection_items_rows]

            highlights_rows = list(
                SummaryHighlight.select().where(SummaryHighlight.user == user_id)
            )
            highlights_data = [model_to_dict(row) for row in highlights_rows]

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
            zip_path = backup_dir / f"bsr-backup-{user_id}-{timestamp}.zip"

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("manifest.json", json.dumps(manifest, default=str, indent=2))
                archive.writestr("requests.json", json.dumps(requests_data, default=str))
                archive.writestr("summaries.json", json.dumps(summaries_data, default=str))
                archive.writestr("tags.json", json.dumps(tags_data, default=str))
                archive.writestr("summary_tags.json", json.dumps(summary_tags_data, default=str))
                archive.writestr("collections.json", json.dumps(collections_data, default=str))
                archive.writestr(
                    "collection_items.json", json.dumps(collection_items_data, default=str)
                )
                archive.writestr("highlights.json", json.dumps(highlights_data, default=str))
                archive.writestr(
                    "preferences.json",
                    json.dumps(preferences, default=str) if preferences else "{}",
                )

            file_size = zip_path.stat().st_size
            UserBackup.update(
                file_path=str(zip_path),
                file_size_bytes=file_size,
                items_count=items_count,
                status="completed",
            ).where(UserBackup.id == backup_id).execute()

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
            UserBackup.update(
                status="failed",
                error=str(exc)[:1000],
            ).where(UserBackup.id == backup_id).execute()


def restore_from_archive(
    user_id: int,
    zip_bytes: bytes,
    *,
    db: DatabaseSessionManager | None = None,
) -> dict[str, Any]:
    """Restore user data from a backup ZIP and return a summary."""
    from app.db.models import (
        Collection,
        CollectionItem,
        Request,
        Summary,
        SummaryHighlight,
        SummaryTag,
        Tag,
    )

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
            manifest_raw = archive.read("manifest.json")
            manifest = json.loads(manifest_raw)
            archive_version = manifest.get("version", "unknown")
            if archive_version not in ("1.0",):
                return {
                    "restored": restored,
                    "skipped": skipped,
                    "errors": [f"Unsupported backup version: {archive_version}"],
                }

            with _connection_context(db):
                request_id_map: dict[int, int] = {}
                summary_id_map: dict[int, int] = {}
                tag_id_map: dict[int, int] = {}
                collection_id_map: dict[int, int] = {}

                requests_data = json.loads(archive.read("requests.json"))
                for request in requests_data:
                    try:
                        dedupe = request.get("dedupe_hash")
                        if dedupe:
                            existing = (
                                Request.select(Request.id)
                                .where((Request.user == user_id) & (Request.dedupe_hash == dedupe))
                                .first()
                            )
                            if existing:
                                request_id_map[request["id"]] = existing.id
                                skipped["requests"] += 1
                                continue

                        new_request = Request.create(
                            type=request.get("type", "url"),
                            status=request.get("status", "completed"),
                            user=user_id,
                            input_url=request.get("input_url"),
                            normalized_url=request.get("normalized_url"),
                            dedupe_hash=request.get("dedupe_hash"),
                            lang_detected=request.get("lang_detected"),
                        )
                        request_id_map[request["id"]] = new_request.id
                        restored["requests"] += 1
                    except Exception as exc:
                        errors.append(f"request {request.get('id')}: {exc}")

                summaries_data = json.loads(archive.read("summaries.json"))
                for summary in summaries_data:
                    try:
                        old_request_id = summary.get("request")
                        new_request_id = request_id_map.get(old_request_id)
                        if new_request_id is None:
                            skipped["summaries"] += 1
                            continue

                        existing_summary = (
                            Summary.select(Summary.id)
                            .where(Summary.request == new_request_id)
                            .first()
                        )
                        if existing_summary:
                            summary_id_map[summary["id"]] = existing_summary.id
                            skipped["summaries"] += 1
                            continue

                        new_summary = Summary.create(
                            request=new_request_id,
                            lang=summary.get("lang", "en"),
                            json_payload=summary.get("json_payload"),
                            is_read=bool(summary.get("is_read", False)),
                            is_deleted=bool(summary.get("is_deleted", False)),
                        )
                        summary_id_map[summary["id"]] = new_summary.id
                        restored["summaries"] += 1
                    except Exception as exc:
                        errors.append(f"summary {summary.get('id')}: {exc}")

                tags_data = json.loads(archive.read("tags.json"))
                for tag in tags_data:
                    try:
                        normalized_name = (
                            tag.get("normalized_name") or tag.get("name", "").strip().lower()
                        )
                        existing_tag = Tag.get_or_none(
                            (Tag.user == user_id)
                            & (Tag.normalized_name == normalized_name)
                            & (~Tag.is_deleted)
                        )
                        if existing_tag:
                            tag_id_map[tag["id"]] = existing_tag.id
                            skipped["tags"] += 1
                            continue

                        new_tag = Tag.create(
                            user=user_id,
                            name=tag.get("name", normalized_name),
                            normalized_name=normalized_name,
                            color=tag.get("color"),
                        )
                        tag_id_map[tag["id"]] = new_tag.id
                        restored["tags"] += 1
                    except Exception as exc:
                        errors.append(f"tag {tag.get('id')}: {exc}")

                summary_tags_data = json.loads(archive.read("summary_tags.json"))
                for summary_tag in summary_tags_data:
                    try:
                        new_summary_id = summary_id_map.get(summary_tag.get("summary"))
                        new_tag_id = tag_id_map.get(summary_tag.get("tag"))
                        if new_summary_id is None or new_tag_id is None:
                            continue
                        SummaryTag.get_or_create(
                            summary=new_summary_id,
                            tag=new_tag_id,
                            defaults={"source": summary_tag.get("source", "manual")},
                        )
                        restored["summary_tags"] += 1
                    except Exception as exc:
                        errors.append(f"summary_tag {summary_tag.get('id')}: {exc}")

                collections_data = json.loads(archive.read("collections.json"))
                for collection in collections_data:
                    try:
                        existing_collection = Collection.get_or_none(
                            (Collection.user == user_id)
                            & (Collection.name == collection.get("name"))
                            & (~Collection.is_deleted)
                        )
                        if existing_collection:
                            collection_id_map[collection["id"]] = existing_collection.id
                            skipped["collections"] += 1
                            continue

                        new_collection = Collection.create(
                            user=user_id,
                            name=collection.get("name", "Imported collection"),
                            description=collection.get("description"),
                            position=collection.get("position"),
                            collection_type=collection.get("collection_type", "manual"),
                            query_conditions_json=collection.get("query_conditions_json"),
                            query_match_mode=collection.get("query_match_mode", "all"),
                        )
                        collection_id_map[collection["id"]] = new_collection.id
                        restored["collections"] += 1
                    except Exception as exc:
                        errors.append(f"collection {collection.get('id')}: {exc}")

                collection_items_data = json.loads(archive.read("collection_items.json"))
                for item in collection_items_data:
                    try:
                        new_collection_id = collection_id_map.get(item.get("collection"))
                        new_summary_id = summary_id_map.get(item.get("summary"))
                        if new_collection_id is None or new_summary_id is None:
                            continue
                        CollectionItem.get_or_create(
                            collection=new_collection_id,
                            summary=new_summary_id,
                            defaults={"position": item.get("position")},
                        )
                        restored["collection_items"] += 1
                    except Exception as exc:
                        errors.append(f"collection_item {item.get('id')}: {exc}")

                highlights_data = json.loads(archive.read("highlights.json"))
                for highlight in highlights_data:
                    try:
                        new_summary_id = summary_id_map.get(highlight.get("summary"))
                        if new_summary_id is None:
                            continue
                        SummaryHighlight.create(
                            id=highlight.get("id"),
                            user=user_id,
                            summary=new_summary_id,
                            text=highlight.get("text", ""),
                            start_offset=highlight.get("start_offset"),
                            end_offset=highlight.get("end_offset"),
                            color=highlight.get("color"),
                            note=highlight.get("note"),
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
