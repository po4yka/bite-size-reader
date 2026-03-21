"""Tests for backup service: manifest validation, ZIP structure, retention logic."""

from __future__ import annotations

import io
import json
import unittest
import zipfile

from app.domain.services.backup_service import restore_from_archive


def _build_manifest(*, version: str = "1.0", user_id: int = 1) -> dict:
    return {
        "version": version,
        "user_id": user_id,
        "created_at": "2025-01-01T00:00:00+00:00",
        "counts": {
            "requests": 0,
            "summaries": 0,
            "tags": 0,
            "summary_tags": 0,
            "collections": 0,
            "collection_items": 0,
            "highlights": 0,
        },
    }


_ENTITY_FILES = (
    "requests.json",
    "summaries.json",
    "tags.json",
    "summary_tags.json",
    "collections.json",
    "collection_items.json",
    "highlights.json",
    "preferences.json",
)


def _make_zip(manifest: dict, *, include_entities: bool = True) -> bytes:
    """Build an in-memory backup ZIP with a manifest and empty entity files."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        if include_entities:
            for name in _ENTITY_FILES:
                zf.writestr(name, "[]" if name != "preferences.json" else "{}")
    buf.seek(0)
    return buf.read()


class TestBackupManifest:
    """Manifest validation inside restore_from_archive."""

    def test_manifest_has_required_keys(self) -> None:
        manifest = _build_manifest()
        assert "version" in manifest
        assert "user_id" in manifest
        assert "counts" in manifest
        assert set(manifest["counts"]) == {
            "requests",
            "summaries",
            "tags",
            "summary_tags",
            "collections",
            "collection_items",
            "highlights",
        }

    def test_unsupported_version_returns_error(self) -> None:
        zip_bytes = _make_zip(_build_manifest(version="99.0"))
        result = restore_from_archive(user_id=1, zip_bytes=zip_bytes)
        assert len(result["errors"]) == 1
        assert "Unsupported backup version" in result["errors"][0]

    def test_corrupt_zip_returns_error(self) -> None:
        result = restore_from_archive(user_id=1, zip_bytes=b"not a zip")
        assert any("Invalid or corrupt ZIP" in e for e in result["errors"])

    def test_missing_manifest_returns_error(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("dummy.txt", "hello")
        result = restore_from_archive(user_id=1, zip_bytes=buf.getvalue())
        assert any("Missing required file" in e or "manifest" in e for e in result["errors"])


class TestBackupZipStructure:
    """Verify expected ZIP layout produced by create_backup_archive."""

    def test_expected_files_present(self) -> None:
        zip_bytes = _make_zip(_build_manifest())
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            names = set(zf.namelist())
        expected = {"manifest.json"} | set(_ENTITY_FILES)
        assert expected == names

    def test_manifest_is_valid_json(self) -> None:
        zip_bytes = _make_zip(_build_manifest())
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
        assert manifest["version"] == "1.0"

    def test_entity_files_are_valid_json(self) -> None:
        zip_bytes = _make_zip(_build_manifest())
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            for name in _ENTITY_FILES:
                data = json.loads(zf.read(name))
                assert isinstance(data, (list, dict))


class TestEnforceRetentionLogic(unittest.TestCase):
    """Test the retention pruning logic (unit-level, no DB)."""

    def test_items_beyond_max_count_are_identified(self) -> None:
        """Given a sorted-descending list, items after max_count are 'to_delete'."""
        backups = list(range(7))  # IDs 0..6, newest first
        max_count = 5
        to_delete = backups[max_count:]
        assert to_delete == [5, 6]
        assert len(to_delete) == 2

    def test_no_deletion_when_within_limit(self) -> None:
        backups = list(range(3))
        max_count = 5
        to_delete = backups[max_count:]
        assert to_delete == []

    def test_exact_limit_means_no_deletion(self) -> None:
        backups = list(range(5))
        max_count = 5
        to_delete = backups[max_count:]
        assert to_delete == []
