# Backup Hardening Design

**Date:** 2026-05-15 **Status:** Approved **Scope:** Encrypt backup archives at rest; enforce strict restore safety limits.

---

## Problem

The current backup subsystem has three categories of exposure:

1. **No upload size limit.** `restore_backup` calls `await file.read()` unconditionally. A multi-gigabyte upload exhausts worker memory before any validation runs.

2. **No ZIP safety checks.** `async_restore_from_archive` opens ZIP entries without checking entry count, total compressed size, decompressed size, compression ratio, or entry names. A zip bomb or path-traversal archive is accepted and processed.

3. **No encryption at rest.** Backup ZIPs are written and served as plaintext. An operator who copies or exposes `data/backups/` exposes all user data.

---

## Goals

- Encrypt backup archives at rest using Fernet (AES-128-CBC + HMAC). No new dependencies; `cryptography` is already installed.
- Gate restore uploads at the router level before loading content into memory.
- Validate ZIP safety against the central directory metadata before extracting a single byte.
- Auto-detect encrypted vs plaintext uploads in restore so existing backups remain restorable.
- Keep all safety limits configurable via env vars.

---

## Non-goals

- Streaming encryption (archives are JSON-only and typically small).
- ZIP password protection (pyzipper) — Fernet wrapping is simpler and consistent with the existing GitHub token crypto pattern.
- Key rotation infrastructure (operator can use MultiFernet manually if needed; same note as `app/security/token_crypto.py`).

---

## Architecture

```
app/config/backup.py                     # BackupConfig (new)
app/infrastructure/persistence/
  backup_crypto.py                       # encrypt_backup / decrypt_backup (new)
  backup_safety.py                       # validate_zip_safety (new)
  backup_archive_service.py             # updated: encrypt on write, decrypt+validate on restore
app/api/routers/backups.py              # updated: stream-read with byte cap; correct content-type
tests/test_backup_hardening.py          # new unit tests
docs/guides/backup-and-restore.md       # new Backup Encryption section
```

---

## Component Details

### `app/config/backup.py` — `BackupConfig`

```python
class BackupConfig(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    encryption_key: SecretStr | None = Field(
        default=None,
        validation_alias="BACKUP_ENCRYPTION_KEY",
    )
    encryption_enabled: bool | None = Field(
        default=None,
        validation_alias="BACKUP_ENCRYPTION_ENABLED",
    )

    max_restore_bytes: int = Field(
        default=100 * 1024 * 1024,   # 100 MB
        validation_alias="BACKUP_MAX_RESTORE_BYTES",
    )
    max_zip_entries: int = Field(
        default=100,
        validation_alias="BACKUP_MAX_ZIP_ENTRIES",
    )
    max_compressed_bytes: int = Field(
        default=100 * 1024 * 1024,   # 100 MB
        validation_alias="BACKUP_MAX_COMPRESSED_BYTES",
    )
    max_decompressed_bytes: int = Field(
        default=500 * 1024 * 1024,   # 500 MB
        validation_alias="BACKUP_MAX_DECOMPRESSED_BYTES",
    )
    max_compression_ratio: float = Field(
        default=100.0,
        validation_alias="BACKUP_MAX_COMPRESSION_RATIO",
    )

    @property
    def is_encryption_enabled(self) -> bool:
        if self.encryption_enabled is not None:
            return self.encryption_enabled
        return self.encryption_key is not None
```

`is_encryption_enabled` resolves to `True` automatically when `BACKUP_ENCRYPTION_KEY` is set, so operators who add a key get encryption without a second env var. Setting `BACKUP_ENCRYPTION_ENABLED=false` explicitly disables it even when a key is present.

`BackupConfig` is wired into `AppConfig` in `app/config/settings.py` the same way as other sub-configs (e.g., `GitHubConfig`).

---

### `app/infrastructure/persistence/backup_crypto.py`

```python
FERNET_MAGIC = b"gAAAAA"   # all Fernet tokens begin with this prefix

def is_fernet_ciphertext(data: bytes) -> bool: ...

def encrypt_backup(zip_bytes: bytes, key: SecretStr) -> bytes:
    """Fernet-encrypt a ZIP payload. Returns opaque ciphertext bytes."""

def decrypt_backup(data: bytes, key: SecretStr) -> bytes:
    """Decrypt Fernet ciphertext. Raises InvalidBackupCiphertextError on bad key/corruption."""

class InvalidBackupCiphertextError(ValueError): ...
class MissingBackupEncryptionKeyError(RuntimeError): ...
```

No module-level cache; the caller passes the key from `BackupConfig`. This avoids the `reset_key_cache()` ceremony needed in tests for the GitHub token module.

---

### `app/infrastructure/persistence/backup_safety.py`

```python
class ZipSafetyViolation(ValueError): ...

def validate_zip_safety(
    data: bytes,
    *,
    max_entries: int,
    max_compressed_bytes: int,
    max_decompressed_bytes: int,
    max_ratio: float,
) -> None:
    """
    Parse the ZIP central directory and reject the archive if any limit is exceeded.
    No entry data is decompressed during validation.

    Checks (in order):
      1. Entry count > max_entries
      2. sum(info.compress_size) > max_compressed_bytes
      3. sum(info.file_size)     > max_decompressed_bytes
      4. Any entry: file_size / max(compress_size, 1) > max_ratio  (zip bomb)
      5. Any entry name starting with "/"              (absolute path)
      6. Any entry name containing ".." after normalization (path traversal)
      7. Zero entries                                   (empty archive)
    """
```

Validation reads only the central directory, which `zipfile.ZipFile` parses on `__enter__` without inflating entry content.

---

### `backup_archive_service.py` — create path

```python
# Build ZIP into in-memory buffer (existing logic, unchanged)
buf = BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
    archive.writestr("manifest.json", ...)
    ...

zip_bytes = buf.getvalue()

if cfg.is_encryption_enabled:
    payload = encrypt_backup(zip_bytes, cfg.encryption_key)
    suffix = ".zip.enc"
else:
    payload = zip_bytes
    suffix = ".zip"

zip_path = backup_dir / f"ratatoskr-backup-{user_id}-{timestamp}{suffix}"
zip_path.write_bytes(payload)
```

`async_create_backup_archive` gains an optional `cfg: BackupConfig | None` parameter (defaults to `load_backup_config()`).

---

### `backup_archive_service.py` — restore path

```python
async def async_restore_from_archive(user_id, zip_bytes, *, db=None, cfg=None):
    cfg = cfg or load_backup_config()

    # 1. Decrypt if needed
    if is_fernet_ciphertext(zip_bytes):
        if cfg.encryption_key is None:
            errors.append("Encrypted backup but BACKUP_ENCRYPTION_KEY is not configured")
            return {"restored": ..., "skipped": ..., "errors": errors}
        try:
            zip_bytes = decrypt_backup(zip_bytes, cfg.encryption_key)
        except InvalidBackupCiphertextError:
            errors.append("Could not decrypt backup (wrong key or corrupted archive)")
            return {"restored": ..., "skipped": ..., "errors": errors}
    else:
        logger.warning("restore_unencrypted_backup", extra={"user_id": user_id})

    # 2. ZIP safety — raises ZipSafetyViolation before any extraction
    try:
        validate_zip_safety(
            zip_bytes,
            max_entries=cfg.max_zip_entries,
            max_compressed_bytes=cfg.max_compressed_bytes,
            max_decompressed_bytes=cfg.max_decompressed_bytes,
            max_ratio=cfg.max_compression_ratio,
        )
    except ZipSafetyViolation as exc:
        return {"restored": ..., "skipped": ..., "errors": [str(exc)]}

    # 3. Existing extraction + import logic — unchanged
    with zipfile.ZipFile(BytesIO(zip_bytes), "r") as archive:
        ...
```

---

### `app/api/routers/backups.py` — restore endpoint

Replace unbounded `file.read()` with a capped async-iterator read:

```python
@router.post("/restore")
async def restore_backup(file: UploadFile, user=Depends(get_current_user)) -> dict:
    cfg = get_backup_config()
    limit = cfg.max_restore_bytes
    chunks: list[bytes] = []
    received = 0
    async for chunk in file:
        received += len(chunk)
        if received > limit:
            raise APIException(
                message=f"Upload exceeds {limit // 1024 // 1024} MB limit",
                error_code=ErrorCode.VALIDATION_ERROR,
                status_code=413,
            )
        chunks.append(chunk)
    content = b"".join(chunks)
    if not content:
        raise APIException("Uploaded file is empty", ...)
    summary = await async_restore_from_archive(user["user_id"], content, db=..., cfg=cfg)
    return success_response(summary)
```

### `app/api/routers/backups.py` — download endpoint

```python
media_type = "application/zip" if filename.endswith(".zip") else "application/octet-stream"
return FileResponse(path=file_path, filename=filename, media_type=media_type)
```

---

## Tests (`tests/test_backup_hardening.py`)

All unit tests; no DB or filesystem required.

| Test | Covers |
|---|---|
| `test_encrypted_backup_roundtrip` | `encrypt_backup` → `decrypt_backup` round-trips correctly |
| `test_wrong_key_raises` | Wrong key → `InvalidBackupCiphertextError` |
| `test_restore_accepts_encrypted_archive` | Restore decrypts + returns correct counts |
| `test_restore_accepts_unencrypted_archive` | Plaintext ZIP accepted (auto-detect) |
| `test_zip_bomb_rejected` | Entry ratio > max_ratio → `ZipSafetyViolation` |
| `test_too_many_entries_rejected` | Entry count > max_entries → `ZipSafetyViolation` |
| `test_oversized_decompressed_rejected` | file_size sum > limit → `ZipSafetyViolation` |
| `test_path_traversal_rejected` | `../../etc/passwd` entry → `ZipSafetyViolation` |
| `test_absolute_path_rejected` | `/etc/passwd` entry → `ZipSafetyViolation` |
| `test_empty_archive_rejected` | Zero entries → `ZipSafetyViolation` |
| `test_oversized_upload_rejected` | Router returns 413 when upload > limit |

---

## Environment Variables (new)

| Variable | Default | Description |
|---|---|---|
| `BACKUP_ENCRYPTION_KEY` | — | Fernet key (44-char base64). Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `BACKUP_ENCRYPTION_ENABLED` | auto (true if key set) | Explicit override to force-disable encryption even when a key is present |
| `BACKUP_MAX_RESTORE_BYTES` | 104857600 (100 MB) | Upload gate for restore endpoint |
| `BACKUP_MAX_ZIP_ENTRIES` | 100 | Max entries in restore archive |
| `BACKUP_MAX_COMPRESSED_BYTES` | 104857600 (100 MB) | Max sum of compressed entry sizes |
| `BACKUP_MAX_DECOMPRESSED_BYTES` | 524288000 (500 MB) | Max sum of uncompressed entry sizes |
| `BACKUP_MAX_COMPRESSION_RATIO` | 100.0 | Max per-entry compression ratio |

---

## Acceptance Criteria

- [ ] Restore rejects unsafe ZIPs (zip bomb, too many entries, oversized, path traversal) before any extraction or DB write.
- [ ] Backups are encrypted by default when `BACKUP_ENCRYPTION_KEY` is set.
- [ ] Unencrypted backup creation is only available when no key is set or `BACKUP_ENCRYPTION_ENABLED=false`.
- [ ] Restore auto-detects encrypted vs plaintext input; old unencrypted backups remain restorable.
- [ ] Restore endpoint rejects uploads exceeding `BACKUP_MAX_RESTORE_BYTES` before reading content fully into memory.
- [ ] All 11 new unit tests pass.
- [ ] `docs/guides/backup-and-restore.md` documents key generation and encryption behavior.
