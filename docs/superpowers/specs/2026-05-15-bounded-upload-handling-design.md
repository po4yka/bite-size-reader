# Bounded Upload Handling — Design Spec

**Date:** 2026-05-15 **Area:** api / config **Status:** approved

---

## Problem

Both upload endpoints (`POST /import` and `POST /backups/restore`) call `await file.read()` with no size cap. A client can stream an arbitrarily large file and exhaust server memory before any rejection occurs.

---

## Goals

- No endpoint reads an arbitrarily sized upload into memory.
- Limits are configurable via environment variables and documented.
- Clear 413 / 400 API errors for oversized files and too-many-items.
- Existing parser behaviour is fully compatible.

---

## Config Changes

### New: `app/config/import_export.py` → `ImportConfig`

Pydantic `BaseModel` (frozen, `populate_by_name=True`) following the project config pattern.

| Field | Env var | Default | Description |
|---|---|---|---|
| `max_upload_bytes` | `IMPORT_MAX_UPLOAD_BYTES` | 10 485 760 (10 MB) | Maximum upload size for the import endpoint |
| `max_items` | `IMPORT_MAX_ITEMS` | 10 000 | Maximum number of parsed bookmarks per import |

### Updated: `app/config/backup.py` → `BackupConfig.max_restore_bytes`

Rename `validation_alias` from `BACKUP_MAX_RESTORE_BYTES` → `BACKUP_RESTORE_MAX_UPLOAD_BYTES`.  
Default remains 100 MB. The old alias was never in a released env var reference, so a clean rename is preferable to `AliasChoices`.

### Wiring

`ImportConfig` added to both `AppConfig` (dataclass field with `default_factory`) and `Settings` (pydantic field with `default_factory`) as `import_export: ImportConfig`, following the same pattern as every other config subsystem.

---

## Bounded-Read Helper

A module-private async function replaces each bare `file.read()` call:

```python
async def _read_bounded(file: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(65536)  # 64 KB
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise APIException(
                message=f"File exceeds maximum allowed size of {max_bytes} bytes",
                error_code=ErrorCode.VALIDATION_ERROR,
                status_code=413,
            )
        chunks.append(chunk)
    return b"".join(chunks)
```

The function is duplicated as a module-level private helper in both routers (`import_export.py` and `backups.py`). The two callers are parallel, not reused, so a shared utility would add coupling without benefit.

---

## Endpoint Changes

### `POST /import` (`app/api/routers/import_export.py`)

1. Replace `content = await file.read()` with `content = await _read_bounded(file, cfg.max_upload_bytes)` where `cfg` is loaded from `load_config().import_export`.
2. After `bookmarks = parser.parse(content)`, add:
   ```python
   if len(bookmarks) > cfg.max_items:
       raise APIException(
           message=f"Import contains {len(bookmarks)} items; maximum is {cfg.max_items}",
           error_code=ErrorCode.VALIDATION_ERROR,
           status_code=400,
       )
   ```

### `POST /backups/restore` (`app/api/routers/backups.py`)

1. Replace `content = await file.read()` with `content = await _read_bounded(file, cfg.max_restore_bytes)` where `cfg` is loaded from `load_backup_config()` (already used elsewhere in the backup module).

---

## Error Responses

| Condition | HTTP status | `error_code` |
|---|---|---|
| Upload exceeds `max_upload_bytes` / `max_restore_bytes` | 413 | `VALIDATION_ERROR` |
| Parsed item count exceeds `max_items` | 400 | `VALIDATION_ERROR` |

---

## Tests

New file: `tests/api/test_upload_limits.py`

| Test | Setup | Expected |
|---|---|---|
| `test_import_file_too_large` | POST a file of `max_upload_bytes + 1` bytes | 413 |
| `test_restore_file_too_large` | POST a file of `max_restore_bytes + 1` bytes | 413 |
| `test_import_too_many_bookmarks` | Mock parser to return `max_items + 1` items | 400 |
| `test_import_success` | POST minimal valid HTML bookmark file; mock `ImportExportService` | 201 |

All tests use `TestClient` + JWT token (`create_access_token`). Size-limit tests (413) patch the loaded config to a small sentinel (e.g. 10 bytes) and send a file one byte over the limit — no service or DB calls occur. The too-many-items test (400) patches `max_items` to 2 and mocks the parser to return 3 items. The success test patches `ImportExportService.create_import_job` and `process_import` to avoid DB writes.

The `max_upload_bytes` and `max_items` limits are patched to small sentinel values (e.g. 10 bytes, 2 items) so tests do not need to allocate large buffers.

---

## Out of Scope

- Streaming the upload directly to disk before parsing (not required; bounded in-memory is sufficient for the stated limits).
- Per-user or per-tier limits.
- Multipart chunk uploads.
