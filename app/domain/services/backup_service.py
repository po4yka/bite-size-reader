"""Business logic for backup creation and restoration."""

from __future__ import annotations

import json
import os
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from app.core.logging_utils import get_logger
from app.core.time_utils import UTC

logger = get_logger(__name__)


def create_backup_archive(user_id: int, backup_id: int, data_dir: str) -> None:
    """Create a ZIP backup of all user data. Runs as a background task.

    Queries all user data, serializes each entity type to JSON, builds a
    manifest, and writes a ZIP archive. Updates the UserBackup record with
    the result (completed or failed).
    """
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

    try:
        UserBackup.update(status="processing").where(UserBackup.id == backup_id).execute()

        # --- 1. Query all user data ---
        user_row = User.get_by_id(user_id)
        preferences = user_row.preferences_json

        requests_rows = list(
            Request.select().where(Request.user == user_id).order_by(Request.created_at.asc())
        )
        requests_data = [model_to_dict(r) for r in requests_rows]

        summaries_rows = list(
            Summary.select()
            .join(Request, on=(Summary.request == Request.id))
            .where(
                (Request.user == user_id) & (Summary.is_deleted == False)  # noqa: E712
            )
        )
        summary_ids = [s.id for s in summaries_rows]
        summaries_data = [model_to_dict(s) for s in summaries_rows]

        tags_rows = list(
            Tag.select().where(
                (Tag.user == user_id) & (Tag.is_deleted == False)  # noqa: E712
            )
        )
        tag_ids = [t.id for t in tags_rows]
        tags_data = [model_to_dict(t) for t in tags_rows]

        summary_tags_rows = (
            list(
                SummaryTag.select().where(
                    (SummaryTag.summary.in_(summary_ids)) & (SummaryTag.tag.in_(tag_ids))
                )
            )
            if summary_ids and tag_ids
            else []
        )
        summary_tags_data = [model_to_dict(st) for st in summary_tags_rows]

        collections_rows = list(
            Collection.select().where(
                (Collection.user == user_id) & (Collection.is_deleted == False)  # noqa: E712
            )
        )
        collection_ids = [c.id for c in collections_rows]
        collections_data = [model_to_dict(c) for c in collections_rows]

        collection_items_rows = (
            list(CollectionItem.select().where(CollectionItem.collection.in_(collection_ids)))
            if collection_ids
            else []
        )
        collection_items_data = [model_to_dict(ci) for ci in collection_items_rows]

        highlights_rows = list(SummaryHighlight.select().where(SummaryHighlight.user == user_id))
        highlights_data = [model_to_dict(h) for h in highlights_rows]

        # --- 2. Build manifest ---
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

        # --- 3. Create ZIP ---
        backup_dir = Path(data_dir) / "backups" / str(user_id)
        os.makedirs(backup_dir, exist_ok=True)

        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        zip_filename = f"bsr-backup-{user_id}-{timestamp}.zip"
        zip_path = backup_dir / zip_filename

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, default=str, indent=2))
            zf.writestr("requests.json", json.dumps(requests_data, default=str))
            zf.writestr("summaries.json", json.dumps(summaries_data, default=str))
            zf.writestr("tags.json", json.dumps(tags_data, default=str))
            zf.writestr("summary_tags.json", json.dumps(summary_tags_data, default=str))
            zf.writestr("collections.json", json.dumps(collections_data, default=str))
            zf.writestr("collection_items.json", json.dumps(collection_items_data, default=str))
            zf.writestr("highlights.json", json.dumps(highlights_data, default=str))
            zf.writestr(
                "preferences.json",
                json.dumps(preferences, default=str) if preferences else "{}",
            )

        file_size = zip_path.stat().st_size

        # --- 4. Update backup record ---
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

    except Exception as e:
        logger.exception(
            "backup_creation_failed",
            extra={"backup_id": backup_id, "user_id": user_id, "error": str(e)},
        )
        UserBackup.update(
            status="failed",
            error=str(e)[:1000],
        ).where(UserBackup.id == backup_id).execute()


def restore_from_archive(user_id: int, zip_bytes: bytes) -> dict[str, Any]:
    """Restore user data from a backup ZIP. Returns a restore summary.

    For requests: skips duplicates by dedupe_hash.
    For tags: find-or-create by normalized_name.
    For collections: find-or-create by name.
    """

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
        with zipfile.ZipFile(BytesIO(zip_bytes), "r") as zf:
            # Validate manifest
            manifest_raw = zf.read("manifest.json")
            manifest = json.loads(manifest_raw)
            archive_version = manifest.get("version", "unknown")
            if archive_version not in ("1.0",):
                return {
                    "restored": restored,
                    "skipped": skipped,
                    "errors": [f"Unsupported backup version: {archive_version}"],
                }

            # Build ID mapping tables (old_id -> new_id) for relational linking
            request_id_map: dict[int, int] = {}
            summary_id_map: dict[int, int] = {}
            tag_id_map: dict[int, int] = {}
            collection_id_map: dict[int, int] = {}

            # --- Requests ---
            requests_data = json.loads(zf.read("requests.json"))
            for req in requests_data:
                try:
                    dedupe = req.get("dedupe_hash")
                    if dedupe:
                        existing = (
                            Request.select(Request.id)
                            .where((Request.user == user_id) & (Request.dedupe_hash == dedupe))
                            .first()
                        )
                        if existing:
                            request_id_map[req["id"]] = existing.id
                            skipped["requests"] += 1
                            continue

                    new_req = Request.create(
                        type=req.get("type", "url"),
                        status=req.get("status", "completed"),
                        user=user_id,
                        input_url=req.get("input_url"),
                        normalized_url=req.get("normalized_url"),
                        dedupe_hash=req.get("dedupe_hash"),
                        lang_detected=req.get("lang_detected"),
                    )
                    request_id_map[req["id"]] = new_req.id
                    restored["requests"] += 1
                except Exception as exc:
                    errors.append(f"request {req.get('id')}: {exc}")

            # --- Summaries ---
            summaries_data = json.loads(zf.read("summaries.json"))
            for s in summaries_data:
                try:
                    old_req_id = s.get("request")
                    new_req_id = request_id_map.get(old_req_id)
                    if new_req_id is None:
                        skipped["summaries"] += 1
                        continue
                    # Check if summary already exists for this request
                    existing = (
                        Summary.select(Summary.id).where(Summary.request == new_req_id).first()
                    )
                    if existing:
                        summary_id_map[s["id"]] = existing.id
                        skipped["summaries"] += 1
                        continue

                    new_summary = Summary.create(
                        request=new_req_id,
                        lang=s.get("lang"),
                        json_payload=s.get("json_payload"),
                        insights_json=s.get("insights_json"),
                    )
                    summary_id_map[s["id"]] = new_summary.id
                    restored["summaries"] += 1
                except Exception as exc:
                    errors.append(f"summary {s.get('id')}: {exc}")

            # --- Tags (find-or-create by normalized_name) ---
            tags_data = json.loads(zf.read("tags.json"))
            for t in tags_data:
                try:
                    normalized = t.get("normalized_name", "")
                    existing = (
                        Tag.select()
                        .where(
                            (Tag.user == user_id)
                            & (Tag.normalized_name == normalized)
                            & (Tag.is_deleted == False)  # noqa: E712
                        )
                        .first()
                    )
                    if existing:
                        tag_id_map[t["id"]] = existing.id
                        skipped["tags"] += 1
                    else:
                        new_tag = Tag.create(
                            user=user_id,
                            name=t.get("name", ""),
                            normalized_name=normalized,
                            color=t.get("color"),
                        )
                        tag_id_map[t["id"]] = new_tag.id
                        restored["tags"] += 1
                except Exception as exc:
                    errors.append(f"tag {t.get('id')}: {exc}")

            # --- SummaryTags ---
            summary_tags_data = json.loads(zf.read("summary_tags.json"))
            for st in summary_tags_data:
                try:
                    new_summary_id = summary_id_map.get(st.get("summary"))
                    new_tag_id = tag_id_map.get(st.get("tag"))
                    if new_summary_id is None or new_tag_id is None:
                        continue
                    # Skip if association already exists
                    existing = (
                        SummaryTag.select()
                        .where(
                            (SummaryTag.summary == new_summary_id) & (SummaryTag.tag == new_tag_id)
                        )
                        .first()
                    )
                    if existing:
                        continue
                    SummaryTag.create(
                        summary=new_summary_id,
                        tag=new_tag_id,
                        source=st.get("source", "backup_restore"),
                    )
                    restored["summary_tags"] += 1
                except Exception as exc:
                    errors.append(f"summary_tag: {exc}")

            # --- Collections (find-or-create by name) ---
            collections_data = json.loads(zf.read("collections.json"))
            for c in collections_data:
                try:
                    existing = (
                        Collection.select()
                        .where(
                            (Collection.user == user_id)
                            & (Collection.name == c.get("name"))
                            & (Collection.is_deleted == False)  # noqa: E712
                        )
                        .first()
                    )
                    if existing:
                        collection_id_map[c["id"]] = existing.id
                        skipped["collections"] += 1
                    else:
                        new_coll = Collection.create(
                            user=user_id,
                            name=c.get("name", ""),
                            description=c.get("description"),
                            icon=c.get("icon"),
                            color=c.get("color"),
                        )
                        collection_id_map[c["id"]] = new_coll.id
                        restored["collections"] += 1
                except Exception as exc:
                    errors.append(f"collection {c.get('id')}: {exc}")

            # --- CollectionItems ---
            collection_items_data = json.loads(zf.read("collection_items.json"))
            for ci in collection_items_data:
                try:
                    new_coll_id = collection_id_map.get(ci.get("collection"))
                    new_summary_id = summary_id_map.get(ci.get("summary"))
                    if new_coll_id is None or new_summary_id is None:
                        continue
                    existing = (
                        CollectionItem.select()
                        .where(
                            (CollectionItem.collection == new_coll_id)
                            & (CollectionItem.summary == new_summary_id)
                        )
                        .first()
                    )
                    if existing:
                        continue
                    CollectionItem.create(
                        collection=new_coll_id,
                        summary=new_summary_id,
                        position=ci.get("position", 0),
                    )
                    restored["collection_items"] += 1
                except Exception as exc:
                    errors.append(f"collection_item: {exc}")

            # --- Highlights ---
            highlights_data = json.loads(zf.read("highlights.json"))
            for h in highlights_data:
                try:
                    new_summary_id = summary_id_map.get(h.get("summary"))
                    if new_summary_id is None:
                        continue
                    import uuid

                    SummaryHighlight.create(
                        id=uuid.uuid4(),
                        user=user_id,
                        summary=new_summary_id,
                        text=h.get("text", ""),
                        start_offset=h.get("start_offset"),
                        end_offset=h.get("end_offset"),
                        color=h.get("color"),
                        note=h.get("note"),
                    )
                    restored["highlights"] += 1
                except Exception as exc:
                    errors.append(f"highlight: {exc}")

    except zipfile.BadZipFile:
        errors.append("Invalid or corrupt ZIP file")
    except KeyError as e:
        errors.append(f"Missing required file in archive: {e}")
    except Exception as e:
        errors.append(f"Restore failed: {e}")

    return {
        "restored": restored,
        "skipped": skipped,
        "errors": errors,
    }


def enforce_retention(user_id: int, max_count: int) -> int:
    """Delete oldest backups beyond retention limit. Returns count deleted."""
    from app.db.models import UserBackup

    backups = list(
        UserBackup.select(UserBackup.id, UserBackup.file_path)
        .where(UserBackup.user == user_id)
        .order_by(UserBackup.created_at.desc())
    )

    if len(backups) <= max_count:
        return 0

    to_delete = backups[max_count:]
    deleted = 0
    for backup in to_delete:
        # Remove file from disk if it exists
        if backup.file_path:
            try:
                os.remove(backup.file_path)
            except OSError:
                pass
        UserBackup.delete().where(UserBackup.id == backup.id).execute()
        deleted += 1

    if deleted:
        logger.info(
            "backup_retention_enforced",
            extra={"user_id": user_id, "deleted": deleted, "max_count": max_count},
        )

    return deleted
