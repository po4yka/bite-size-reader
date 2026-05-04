# How to Backup and Restore

Protect a Ratatoskr instance by backing up the durable host paths used by the
current Docker Compose deployment.

**Audience:** Operators
**Difficulty:** Intermediate
**Estimated Time:** 20 minutes

---

## Scope

The default Compose file is `ops/docker/docker-compose.yml`. Run these commands
from the repository root.

Durable data is split across these locations:

| Data | Default path | Source |
| ---- | ------------ | ------ |
| SQLite database | `data/ratatoskr.db` on the host, `/data/ratatoskr.db` in containers | `DB_PATH=/data/ratatoskr.db` |
| Automatic SQLite snapshots | `data/backups/` unless `DB_BACKUP_DIR` is set | bot backup loop |
| ChromaDB vector store | `chroma_data/` on the host, `/data` in the Chroma container | Chroma `PERSIST_DIRECTORY=/data` |
| YouTube downloads | `data/videos/` | `YOUTUBE_STORAGE_PATH` default `/data/videos` |
| Attachments and non-YouTube media | `data/attachments/`, `data/video-sources/` | attachment defaults |
| TTS audio cache | `data/audio/` | `ELEVENLABS_AUDIO_PATH` default `/data/audio` |
| Config and secrets | `.env`, `ratatoskr.yaml`, `config/ratatoskr.yaml`, `config/models.yaml` when present | config search order |
| Redis | no durable backup expected in default Compose | `redis-server --save "" --appendonly no` |

The API `/v1/backups` and Telegram `/backup` flows create per-user export ZIPs
under `data/backups/<user_id>/`. They are useful for user data export, but they
are not a full instance backup because they do not include Chroma, media files,
all operational tables, or config.

---

## Before You Start

Set a backup timestamp once so every archive has matching names:

```bash
export BACKUP_TS="$(date -u +%Y%m%dT%H%M%SZ)"
export BACKUP_DIR="backups/$BACKUP_TS"
mkdir -p "$BACKUP_DIR"
```

Check the effective Compose services:

```bash
docker compose -f ops/docker/docker-compose.yml ps
```

For the most consistent backup, stop services that can write to SQLite or
Chroma:

```bash
docker compose -f ops/docker/docker-compose.yml stop ratatoskr mobile-api mcp mcp-write chroma
```

If you need a low-downtime SQLite-only backup, use the `.backup` command in the
next section while services keep running, then archive Chroma/media during a
maintenance window.

---

## Backup

### SQLite

Preferred SQLite backup, safe while readers/writers exist:

```bash
sqlite3 data/ratatoskr.db ".backup '$BACKUP_DIR/ratatoskr.db'"
sqlite3 "$BACKUP_DIR/ratatoskr.db" "PRAGMA integrity_check;"
```

Expected output:

```text
ok
```

If the application is fully stopped, a plain copy is also acceptable:

```bash
cp data/ratatoskr.db "$BACKUP_DIR/ratatoskr.db"
sqlite3 "$BACKUP_DIR/ratatoskr.db" "PRAGMA integrity_check;"
```

Ratatoskr also creates automatic SQLite snapshots from the bot process when
`DB_BACKUP_ENABLED=true` (default). The default interval is
`DB_BACKUP_INTERVAL_MINUTES=360`, and `DB_BACKUP_RETENTION=14` keeps the newest
14 snapshot files, not 14 days. Without `DB_BACKUP_DIR`, snapshots land in
`data/backups/`.

### ChromaDB

The default Chroma service persists its database through the host bind mount
`chroma_data:/data`. Back it up after stopping `chroma`:

```bash
tar -C . -czf "$BACKUP_DIR/chroma_data.tar.gz" chroma_data
```

Chroma data is rebuildable from SQLite for summaries that have enough stored
text and embedding inputs:

```bash
python -m app.cli.backfill_chroma_store --rebuild
```

Backing up `chroma_data/` is still faster and preserves the exact current vector
store. Rebuild when the archive is missing, corrupted, or intentionally stale
after an embedding model or namespace change.

### Redis

Default Redis is internal-only and configured without RDB or AOF persistence:

```yaml
command: ["redis-server", "--save", "", "--appendonly", "no"]
```

Do not expect Redis data to survive container recreation, and do not include the
`redis_data` volume in release-critical backups. Ratatoskr uses Redis for
ephemeral caches, auth/sync/session TTLs, rate-limit state, batch progress, and
similar recoverable data. After restore, users may need to sign in again, sync
sessions may be gone, and caches will warm naturally.

If you run an external persistent Redis with custom settings, use that
deployment's normal `BGSAVE`, AOF, or managed snapshot process. That is outside
the default Ratatoskr Compose contract.

### Media Files

Back up media directories that exist. The SQLite `video_downloads` table stores
paths to downloaded YouTube videos, subtitles, and thumbnails, so restoring the
files keeps cached video results usable.

```bash
for path in data/videos data/attachments data/video-sources data/audio; do
  if [ -d "$path" ]; then
    tar -C . -czf "$BACKUP_DIR/$(echo "$path" | tr / _).tar.gz" "$path"
  fi
done
```

Notes:

- `data/videos/` can be large. It is optional if you accept re-downloading or
  losing cached video files.
- `data/attachments/` and `data/video-sources/` are temporary by default, but
  include them for a byte-for-byte instance restore.
- `data/audio/` is a cache for generated audio and can be regenerated if the
  provider and source text are still available.

### Config And Secrets

Back up config files separately from the database. These files may contain API
keys and should be encrypted at rest.

```bash
CONFIG_FILES=()
for path in .env ratatoskr.yaml config/ratatoskr.yaml config/models.yaml; do
  [ -f "$path" ] && CONFIG_FILES+=("$path")
done
[ "${#CONFIG_FILES[@]}" -gt 0 ] && tar -C . -czf "$BACKUP_DIR/config.tar.gz" "${CONFIG_FILES[@]}"
```

For a single encrypted archive:

```bash
tar -C backups -czf - "$BACKUP_TS" | \
  openssl enc -aes-256-cbc -pbkdf2 -salt -out "backups/$BACKUP_TS.tar.gz.enc"
```

Store the passphrase outside the host. Do not commit backup archives or copied
`.env` files.

### Verify The Backup

```bash
find "$BACKUP_DIR" -maxdepth 1 -type f -print -exec ls -lh {} \;
sqlite3 "$BACKUP_DIR/ratatoskr.db" "PRAGMA quick_check;"
[ ! -f "$BACKUP_DIR/chroma_data.tar.gz" ] || tar -tzf "$BACKUP_DIR/chroma_data.tar.gz" >/dev/null
[ ! -f "$BACKUP_DIR/config.tar.gz" ] || tar -tzf "$BACKUP_DIR/config.tar.gz" >/dev/null
```

Restart services after the backup:

```bash
docker compose -f ops/docker/docker-compose.yml up -d
```

---

## Restore

### Restore On The Same Host

Stop all services that can read or write restored state:

```bash
docker compose -f ops/docker/docker-compose.yml stop ratatoskr mobile-api mcp mcp-write chroma redis
```

Keep a pre-restore copy of the current state:

```bash
mkdir -p "restore-safety/$BACKUP_TS"
[ -f data/ratatoskr.db ] && cp data/ratatoskr.db "restore-safety/$BACKUP_TS/ratatoskr.db.before-restore"
[ -d chroma_data ] && tar -C . -czf "restore-safety/$BACKUP_TS/chroma_data.before-restore.tar.gz" chroma_data
```

Restore SQLite:

```bash
cp "$BACKUP_DIR/ratatoskr.db" data/ratatoskr.db
sqlite3 data/ratatoskr.db "PRAGMA integrity_check;"
```

Restore Chroma if you backed it up:

```bash
if [ -f "$BACKUP_DIR/chroma_data.tar.gz" ]; then
  rm -rf chroma_data
  tar -C . -xzf "$BACKUP_DIR/chroma_data.tar.gz"
fi
```

Restore media archives that exist:

```bash
for archive in "$BACKUP_DIR"/data_*.tar.gz; do
  [ -e "$archive" ] || continue
  tar -C . -xzf "$archive"
done
```

Restore config files deliberately. Review before overwriting production secrets:

```bash
[ -f "$BACKUP_DIR/config.tar.gz" ] && tar -C . -xzf "$BACKUP_DIR/config.tar.gz"
```

Start the stack:

```bash
docker compose -f ops/docker/docker-compose.yml up -d
docker compose -f ops/docker/docker-compose.yml ps
```

Run migrations for the restored image if needed:

```bash
python -m app.cli.migrate_db --status
python -m app.cli.migrate_db data/ratatoskr.db
```

If Chroma was not restored, rebuild it after Chroma is healthy:

```bash
python -m app.cli.backfill_chroma_store --rebuild
```

### Restore To A New Host

On the new host:

```bash
git clone <repo-url> ratatoskr
cd ratatoskr
mkdir -p data config backups
```

Copy the backup directory or encrypted archive to `backups/`, then restore the
same files:

```bash
export BACKUP_TS=YYYYMMDDTHHMMSSZ
export BACKUP_DIR="backups/$BACKUP_TS"

cp "$BACKUP_DIR/ratatoskr.db" data/ratatoskr.db
[ -f "$BACKUP_DIR/config.tar.gz" ] && tar -C . -xzf "$BACKUP_DIR/config.tar.gz"
[ -f "$BACKUP_DIR/chroma_data.tar.gz" ] && tar -C . -xzf "$BACKUP_DIR/chroma_data.tar.gz"

for archive in "$BACKUP_DIR"/data_*.tar.gz; do
  [ -e "$archive" ] || continue
  tar -C . -xzf "$archive"
done
```

Validate and start:

```bash
sqlite3 data/ratatoskr.db "PRAGMA integrity_check;"
docker compose -f ops/docker/docker-compose.yml config
docker compose -f ops/docker/docker-compose.yml up -d
python -m app.cli.migrate_db --status
```

If the new host uses different paths, update `.env` or `ratatoskr.yaml` for
`DB_PATH`, `YOUTUBE_STORAGE_PATH`, `ATTACHMENT_STORAGE_PATH`,
`ATTACHMENT_VIDEO_STORAGE_PATH`, and `ELEVENLABS_AUDIO_PATH` before starting.

---

## Restore Test Checklist

Run this on a staging host or disposable VM before a release:

1. Create a full backup with SQLite, Chroma, media, and config.
2. Restore it into an empty checkout.
3. Run `sqlite3 data/ratatoskr.db "PRAGMA integrity_check;"`.
4. Run `docker compose -f ops/docker/docker-compose.yml config`.
5. Start the stack with `docker compose -f ops/docker/docker-compose.yml up -d`.
6. Confirm `ratatoskr`, `mobile-api`, `redis`, and `chroma` are healthy or
   intentionally disabled by profile/config.
7. Open the web/API and verify existing summaries are visible.
8. Run a semantic search. If Chroma was rebuilt instead of restored, run
   `python -m app.cli.backfill_chroma_store --rebuild` first.
9. Open a restored YouTube summary with a `video_file_path` and confirm the
   file path exists under `data/videos/`, or accept that the media cache was not
   restored.
10. Send one known-good URL through the bot or CLI to confirm new writes work.

---

## Maintenance Commands

Vacuum SQLite during a maintenance window:

```bash
docker compose -f ops/docker/docker-compose.yml stop ratatoskr mobile-api mcp mcp-write
sqlite3 data/ratatoskr.db "VACUUM;"
sqlite3 data/ratatoskr.db "PRAGMA integrity_check;"
docker compose -f ops/docker/docker-compose.yml up -d
```

Recover a damaged SQLite database into a new file:

```bash
docker compose -f ops/docker/docker-compose.yml stop ratatoskr mobile-api mcp mcp-write
sqlite3 data/ratatoskr.db ".recover" | sqlite3 data/ratatoskr.recovered.db
sqlite3 data/ratatoskr.recovered.db "PRAGMA integrity_check;"
mv data/ratatoskr.db data/ratatoskr.corrupted.db
mv data/ratatoskr.recovered.db data/ratatoskr.db
docker compose -f ops/docker/docker-compose.yml up -d
```

If recovery fails, restore the newest backup that passes `PRAGMA integrity_check`.

---

## See Also

- [Deployment](../DEPLOYMENT.md)
- [How to Migrate Versions](migrate-versions.md)
- [ChromaDB Vector Search](setup-chroma-vector-search.md)
- [YouTube Downloads](configure-youtube-download.md)
- [Config File Reference](../reference/config-file.md)
