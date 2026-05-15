# Bounded Upload Handling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace unbounded `file.read()` calls in the import and backup-restore endpoints with chunk-limited reads that return 413/400 before exhausting memory.

**Architecture:** A module-private `_read_bounded` helper in each router reads uploads in 64 KB chunks and raises a 413 `APIException` on overflow. A new `ImportConfig` pydantic model holds `IMPORT_MAX_UPLOAD_BYTES` and `IMPORT_MAX_ITEMS`; the existing `BackupConfig.max_restore_bytes` field has its env alias renamed to `BACKUP_RESTORE_MAX_UPLOAD_BYTES`. Both configs are loaded lazily at request time.

**Tech Stack:** FastAPI `UploadFile`, pydantic-settings `BaseModel`, pytest + `unittest.mock`

---

## File Map

| Action | Path | Purpose |
|---|---|---|
| Create | `app/config/import_export.py` | `ImportConfig` with `max_upload_bytes` and `max_items` |
| Modify | `app/config/backup.py` | Rename `validation_alias` on `max_restore_bytes` |
| Modify | `app/config/settings.py` | Wire `ImportConfig` into `AppConfig` and `Settings` |
| Create | `tests/api/test_upload_limits.py` | 4 upload-limit tests (written before implementation) |
| Modify | `app/api/routers/import_export.py` | Add `_read_bounded`, use it, add item-count guard |
| Modify | `app/api/routers/backups.py` | Add `_read_bounded`, use it |

---

## Task 1: Create ImportConfig

**Files:**
- Create: `app/config/import_export.py`

- [ ] **Step 1: Create the file**

```python
# app/config/import_export.py
"""Import upload size and item-count limits configuration."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ImportConfig(BaseModel):
    """Upload size and item-count limits for the import endpoint."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    max_upload_bytes: int = Field(
        default=10 * 1024 * 1024,
        ge=1024,
        validation_alias="IMPORT_MAX_UPLOAD_BYTES",
        description="Maximum upload size in bytes for the import endpoint (default 10 MB).",
    )
    max_items: int = Field(
        default=10_000,
        ge=1,
        validation_alias="IMPORT_MAX_ITEMS",
        description="Maximum number of parsed bookmarks per import (default 10 000).",
    )
```

- [ ] **Step 2: Verify it imports cleanly**

```bash
source .venv/bin/activate && python -c "from app.config.import_export import ImportConfig; c = ImportConfig(); print(c.max_upload_bytes, c.max_items)"
```

Expected output: `10485760 10000`

---

## Task 2: Rename BackupConfig alias and wire both configs into settings

**Files:**
- Modify: `app/config/backup.py` (line ~33)
- Modify: `app/config/settings.py`

- [ ] **Step 1: Rename the validation alias in BackupConfig**

In `app/config/backup.py`, change line ~33:

```python
# Before:
    max_restore_bytes: int = Field(
        default=100 * 1024 * 1024,
        ge=1024,
        validation_alias="BACKUP_MAX_RESTORE_BYTES",
        description="Maximum upload size in bytes for the restore endpoint (default 100 MB).",
    )

# After:
    max_restore_bytes: int = Field(
        default=100 * 1024 * 1024,
        ge=1024,
        validation_alias="BACKUP_RESTORE_MAX_UPLOAD_BYTES",
        description="Maximum upload size in bytes for the restore endpoint (default 100 MB).",
    )
```

- [ ] **Step 2: Add ImportConfig import to settings.py**

In `app/config/settings.py`, after the line `from .backup import BackupConfig` (line ~40), add:

```python
from .import_export import ImportConfig
```

- [ ] **Step 3: Add import_export field to AppConfig dataclass**

In `app/config/settings.py`, in the `AppConfig` dataclass, after `backup: BackupConfig = field(default_factory=BackupConfig)` (line ~197), add:

```python
    import_export: ImportConfig = field(default_factory=ImportConfig)
```

- [ ] **Step 4: Add import_export field to Settings class**

In `app/config/settings.py`, in the `Settings` class, after `backup: BackupConfig = Field(default_factory=BackupConfig)` (line ~254), add:

```python
    import_export: ImportConfig = Field(default_factory=ImportConfig)
```

- [ ] **Step 5: Verify the full config loads without error**

```bash
source .venv/bin/activate && python -c "
from app.config.settings import load_config
cfg = load_config(allow_stub_telegram=True)
print('import max_upload_bytes:', cfg.import_export.max_upload_bytes)
print('import max_items:', cfg.import_export.max_items)
print('backup max_restore_bytes:', cfg.backup.max_restore_bytes)
"
```

Expected output:
```
import max_upload_bytes: 10485760
import max_items: 10000
backup max_restore_bytes: 104857600
```

- [ ] **Step 6: Commit**

```bash
git add app/config/import_export.py app/config/backup.py app/config/settings.py
git commit -m "feat(config): add ImportConfig and rename BACKUP_RESTORE_MAX_UPLOAD_BYTES alias"
```

---

## Task 3: Write the failing tests

**Files:**
- Create: `tests/api/test_upload_limits.py`

- [ ] **Step 1: Create the test file**

```python
# tests/api/test_upload_limits.py
"""Upload size and item-count limit tests for import and backup-restore endpoints."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.api.routers.auth.tokens import create_access_token
from app.db.models import User


def _make_user(telegram_id: int, username: str) -> Any:
    return User.create(  # type: ignore[attr-defined]
        telegram_user_id=telegram_id,
        username=username,
        is_owner=False,
    )


def _auth(telegram_id: int) -> dict[str, str]:
    token = create_access_token(telegram_id, client_id="test_client")
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# import — oversized file
# ---------------------------------------------------------------------------


def test_import_file_too_large(client: TestClient, db):
    user = _make_user(300001, "upload_limit_import_size")
    headers = _auth(user.telegram_user_id)

    mock_cfg = MagicMock()
    mock_cfg.import_export.max_upload_bytes = 10
    mock_cfg.import_export.max_items = 10_000

    with patch("app.api.routers.import_export.load_config", return_value=mock_cfg):
        response = client.post(
            "/v1/import",
            files={"file": ("bookmarks.html", b"x" * 11, "text/html")},
            data={"options": "{}"},
            headers=headers,
        )

    assert response.status_code == 413


# ---------------------------------------------------------------------------
# backup restore — oversized file
# ---------------------------------------------------------------------------


def test_restore_file_too_large(client: TestClient, db):
    user = _make_user(300002, "upload_limit_restore_size")
    headers = _auth(user.telegram_user_id)

    mock_backup_cfg = MagicMock()
    mock_backup_cfg.max_restore_bytes = 10

    with patch("app.api.routers.backups.load_backup_config", return_value=mock_backup_cfg):
        response = client.post(
            "/v1/backups/restore",
            files={"file": ("backup.zip", b"x" * 11, "application/zip")},
            headers=headers,
        )

    assert response.status_code == 413


# ---------------------------------------------------------------------------
# import — too many parsed bookmarks
# ---------------------------------------------------------------------------


def test_import_too_many_bookmarks(client: TestClient, db):
    user = _make_user(300003, "upload_limit_import_items")
    headers = _auth(user.telegram_user_id)

    mock_cfg = MagicMock()
    mock_cfg.import_export.max_upload_bytes = 10_000
    mock_cfg.import_export.max_items = 2  # limit 2; parser returns 3

    fake_bookmarks = [{"url": f"https://example.com/{i}"} for i in range(3)]
    mock_parser_cls = MagicMock()
    mock_parser_cls.return_value.parse.return_value = fake_bookmarks

    with (
        patch("app.api.routers.import_export.load_config", return_value=mock_cfg),
        patch("app.api.routers.import_export.FormatDetector.detect", return_value="html"),
        patch("app.api.routers.import_export.PARSER_REGISTRY", {"html": mock_parser_cls}),
    ):
        response = client.post(
            "/v1/import",
            files={"file": ("bookmarks.html", b"data", "text/html")},
            data={"options": "{}"},
            headers=headers,
        )

    assert response.status_code == 400
    body = response.json()
    assert "3" in body["error"]["message"]
    assert "2" in body["error"]["message"]


# ---------------------------------------------------------------------------
# import — happy path
# ---------------------------------------------------------------------------


def test_import_success(client: TestClient, db):
    user = _make_user(300004, "upload_limit_import_ok")
    headers = _auth(user.telegram_user_id)

    mock_cfg = MagicMock()
    mock_cfg.import_export.max_upload_bytes = 10_000
    mock_cfg.import_export.max_items = 100

    fake_bookmarks = [{"url": "https://example.com/1"}]
    mock_parser_cls = MagicMock()
    mock_parser_cls.return_value.parse.return_value = fake_bookmarks

    mock_job = {"id": 99, "status": "pending", "total_items": 1}

    with (
        patch("app.api.routers.import_export.load_config", return_value=mock_cfg),
        patch("app.api.routers.import_export.FormatDetector.detect", return_value="html"),
        patch("app.api.routers.import_export.PARSER_REGISTRY", {"html": mock_parser_cls}),
        patch(
            "app.api.routers.import_export.ImportExportService.create_import_job",
            new_callable=AsyncMock,
            return_value=mock_job,
        ),
        patch(
            "app.api.routers.import_export._run_import_task",
            new_callable=AsyncMock,
        ),
    ):
        response = client.post(
            "/v1/import",
            files={"file": ("bookmarks.html", b"some data", "text/html")},
            data={"options": "{}"},
            headers=headers,
        )

    assert response.status_code == 201
    assert response.json()["data"]["id"] == 99
```

- [ ] **Step 2: Run the tests to confirm they all fail**

```bash
source .venv/bin/activate && python -m pytest tests/api/test_upload_limits.py -v 2>&1 | tail -30
```

Expected: 4 FAILs (or ERRORs). At minimum `test_import_file_too_large` and `test_restore_file_too_large` should fail because `_read_bounded` does not exist yet and `load_config` is not imported in the routers.

---

## Task 4: Implement bounded read in import_export.py

**Files:**
- Modify: `app/api/routers/import_export.py`

- [ ] **Step 1: Add `load_config` import**

In `app/api/routers/import_export.py`, add after the existing imports (e.g. after the `app.core.logging_utils` line):

```python
from app.config.settings import load_config
```

- [ ] **Step 2: Add `_read_bounded` helper after the `logger` / `router` declarations**

Insert after `_background_import_tasks: set[asyncio.Task[None]] = set()` (line ~27):

```python

async def _read_bounded(file: UploadFile, max_bytes: int) -> bytes:
    """Read an upload in 64 KB chunks; raise 413 if max_bytes is exceeded."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(65536)
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

- [ ] **Step 3: Replace the unbounded read and add item-count guard in `import_bookmarks`**

Replace the entire `import_bookmarks` function body with:

```python
@router.post("/import", status_code=201)
async def import_bookmarks(
    file: UploadFile = File(...),
    options: str = Form(default="{}"),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Import bookmarks from an uploaded file."""
    cfg = load_config(allow_stub_telegram=True).import_export

    # Parse options
    try:
        opts = json.loads(options)
    except (json.JSONDecodeError, TypeError) as err:
        raise APIException(
            message="Invalid JSON in options field",
            error_code=ErrorCode.VALIDATION_ERROR,
            status_code=400,
        ) from err

    # Read file content with size limit
    content = await _read_bounded(file, cfg.max_upload_bytes)
    if not content:
        raise APIException(
            message="Uploaded file is empty",
            error_code=ErrorCode.VALIDATION_ERROR,
            status_code=400,
        )

    # Detect format
    filename = file.filename or "unknown"
    source_format = FormatDetector.detect(filename, content)
    if source_format == "unknown" or source_format not in PARSER_REGISTRY:
        raise APIException(
            message=f"Unrecognized import format for file: {filename}",
            error_code=ErrorCode.VALIDATION_ERROR,
            status_code=400,
        )

    # Parse bookmarks
    parser_cls = PARSER_REGISTRY[source_format]
    parser = parser_cls()
    bookmarks = parser.parse(content)

    if not bookmarks:
        raise APIException(
            message="No bookmarks found in uploaded file",
            error_code=ErrorCode.VALIDATION_ERROR,
            status_code=400,
        )

    if len(bookmarks) > cfg.max_items:
        raise APIException(
            message=(
                f"Import contains {len(bookmarks)} items; "
                f"maximum allowed is {cfg.max_items}"
            ),
            error_code=ErrorCode.VALIDATION_ERROR,
            status_code=400,
        )

    service = ImportExportService()
    job = await service.create_import_job(
        user_id=user["user_id"],
        source_format=source_format,
        file_name=filename,
        total_items=len(bookmarks),
        options=opts,
    )

    task = asyncio.create_task(
        _run_import_task(
            service,
            job_id=job["id"],
            bookmarks=bookmarks,
            options=opts,
            user_id=user["user_id"],
        )
    )
    _background_import_tasks.add(task)
    task.add_done_callback(_background_import_tasks.discard)

    return success_response(job)
```

- [ ] **Step 4: Run import-related tests**

```bash
source .venv/bin/activate && python -m pytest tests/api/test_upload_limits.py::test_import_file_too_large tests/api/test_upload_limits.py::test_import_too_many_bookmarks tests/api/test_upload_limits.py::test_import_success -v 2>&1 | tail -20
```

Expected: 3 PASSes.

---

## Task 5: Implement bounded read in backups.py

**Files:**
- Modify: `app/api/routers/backups.py`

- [ ] **Step 1: Add `load_backup_config` import**

In `app/api/routers/backups.py`, add to the existing imports block (after the `app.core.logging_utils` line, for example):

```python
from app.config.backup import load_backup_config
```

- [ ] **Step 2: Add `_read_bounded` helper after the `MAX_BACKUPS_PER_HOUR` constant**

Insert after `MAX_BACKUPS_PER_HOUR = 3` (line ~29):

```python

async def _read_bounded(file: UploadFile, max_bytes: int) -> bytes:
    """Read an upload in 64 KB chunks; raise 413 if max_bytes is exceeded."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(65536)
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

- [ ] **Step 3: Replace the unbounded read in `restore_backup`**

Replace the `restore_backup` function body:

```python
@router.post("/restore")
async def restore_backup(
    file: UploadFile,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Restore user data from an uploaded backup ZIP."""
    cfg = load_backup_config()
    content = await _read_bounded(file, cfg.max_restore_bytes)
    if not content:
        raise APIException(
            message="Uploaded file is empty",
            error_code=ErrorCode.VALIDATION_ERROR,
            status_code=400,
        )

    summary = await async_restore_from_archive(user["user_id"], content, db=get_session_manager())
    return success_response(summary)
```

- [ ] **Step 4: Run all four upload-limit tests**

```bash
source .venv/bin/activate && python -m pytest tests/api/test_upload_limits.py -v 2>&1 | tail -20
```

Expected: 4 PASSes.

- [ ] **Step 5: Commit**

```bash
git add tests/api/test_upload_limits.py \
        app/api/routers/import_export.py \
        app/api/routers/backups.py
git commit -m "feat(api): add bounded upload reads with 413/400 limits for import and restore"
```

---

## Task 6: Full regression check

- [ ] **Step 1: Run the broader API test suite**

```bash
source .venv/bin/activate && python -m pytest tests/api/ -x -q 2>&1 | tail -30
```

Expected: no new FAILs vs baseline.

- [ ] **Step 2: Confirm new env vars are documented**

Add to `CLAUDE.md` (Quick Reference: Environment Variables section) and `docs/reference/environment-variables.md` if it exists:

```
IMPORT_MAX_UPLOAD_BYTES=10485760        # Max import upload size (default 10 MB)
IMPORT_MAX_ITEMS=10000                  # Max parsed bookmarks per import
BACKUP_RESTORE_MAX_UPLOAD_BYTES=104857600  # Max backup restore upload size (default 100 MB)
```

- [ ] **Step 3: Final commit**

```bash
git add CLAUDE.md  # (and docs/reference/environment-variables.md if modified)
git commit -m "docs: document IMPORT_MAX_UPLOAD_BYTES, IMPORT_MAX_ITEMS, BACKUP_RESTORE_MAX_UPLOAD_BYTES"
```
