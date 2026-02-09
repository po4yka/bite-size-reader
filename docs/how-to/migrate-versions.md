# How to Migrate Between Versions

Upgrade Bite-Size Reader to a new version safely.

**Audience:** Operators
**Difficulty:** Intermediate
**Estimated Time:** 10-15 minutes

---

## Before You Start

### Backup First

**CRITICAL**: Always backup your data before upgrading:

```bash
# Backup database
cp data/app.db data/app.db.backup.$(date +%Y%m%d)

# Backup environment file
cp .env .env.backup

# Backup YouTube videos (if enabled)
tar -czf youtube_backup_$(date +%Y%m%d).tar.gz data/videos/

# Verify backups
ls -lh data/*.backup* youtube_backup*
```

### Check Release Notes

1. Visit https://github.com/po4yka/bite-size-reader/releases
2. Read **CHANGELOG.md** for breaking changes
3. Note any required migration steps

---

## Migration Path

### Docker Deployment

#### 1. Pull Latest Image

```bash
# Pull new version
docker pull ghcr.io/po4yka/bite-size-reader:latest

# Or specific version
docker pull ghcr.io/po4yka/bite-size-reader:v1.2.0
```

#### 2. Stop Current Container

```bash
# Stop gracefully
docker stop bite-size-reader

# Backup current container (optional)
docker commit bite-size-reader bite-size-reader-backup
```

#### 3. Update Configuration (If Needed)

```bash
# Compare .env.example from new version
docker run --rm ghcr.io/po4yka/bite-size-reader:latest cat .env.example > .env.example.new

# Review differences
diff .env .env.example.new

# Add any new required variables
nano .env
```

#### 4. Run Database Migrations

```bash
# Run migrations before starting new version
docker run --rm \
  --env-file .env \
  -v $(pwd)/data:/data \
  ghcr.io/po4yka/bite-size-reader:latest \
  python -m app.cli.migrate_db

# Check output for any errors
```

#### 5. Start New Version

```bash
# Remove old container
docker rm bite-size-reader

# Start new version
docker run -d \
  --name bite-size-reader \
  --env-file .env \
  -v $(pwd)/data:/data \
  --restart unless-stopped \
  ghcr.io/po4yka/bite-size-reader:latest

# Verify startup
docker logs bite-size-reader | head -20
```

#### 6. Test Functionality

```bash
# Send test URL to bot
# Expected: Bot responds normally

# Check logs for errors
docker logs bite-size-reader | grep -i error

# Verify database integrity
docker exec bite-size-reader sqlite3 /data/app.db "PRAGMA integrity_check;"
```

---

### Local Installation

#### 1. Update Repository

```bash
# Stash local changes
git stash

# Pull latest code
git pull origin main

# Or checkout specific version
git checkout v1.2.0

# Restore local changes
git stash pop
```

#### 2. Update Dependencies

```bash
# Activate venv
source .venv/bin/activate

# Update dependencies
pip install -r requirements.txt -r requirements-dev.txt --upgrade

# Verify no conflicts
pip check
```

#### 3. Run Migrations

```bash
# Run database migrations
python -m app.cli.migrate_db

# Check for errors
echo $?  # Should output: 0
```

#### 4. Restart Bot

```bash
# Stop bot (Ctrl+C)
# Then restart
python bot.py

# Verify startup logs
```

---

## Common Migration Scenarios

### Upgrading from v0.x to v1.x (Breaking Changes)

**Breaking changes:**

- Environment variable renames (see CHANGELOG)
- Database schema changes (automatic migration)
- Summary contract v3.0 (new fields)

**Steps:**

1. Backup database (critical!)
2. Update environment variables:

   ```bash
   # Renamed variables
   OLD_VAR_NAME → NEW_VAR_NAME
   ```

3. Run migrations
4. Verify summaries still accessible

---

### Minor Version Upgrade (v1.1 → v1.2)

**Usually safe:**

- No breaking changes
- Database migrations automatic
- New optional features

**Steps:**

1. Backup database (precaution)
2. Pull new code/image
3. Run migrations
4. Restart bot

---

### Patch Version Upgrade (v1.2.0 → v1.2.1)

**Always safe:**

- Bug fixes only
- No database changes
- No config changes

**Steps:**

1. Pull new code/image
2. Restart bot
3. Done!

---

## Rollback Procedure

If upgrade fails or causes issues:

### Docker Rollback

```bash
# Stop new version
docker stop bite-size-reader
docker rm bite-size-reader

# Restore database backup
cp data/app.db.backup.YYYYMMDD data/app.db

# Run previous version
docker run -d \
  --name bite-size-reader \
  --env-file .env.backup \
  -v $(pwd)/data:/data \
  --restart unless-stopped \
  ghcr.io/po4yka/bite-size-reader:v1.1.0  # Previous version

# Verify
docker logs bite-size-reader
```

### Local Rollback

```bash
# Restore database
cp data/app.db.backup.YYYYMMDD data/app.db

# Checkout previous version
git checkout v1.1.0

# Restore dependencies
pip install -r requirements.txt

# Restart bot
python bot.py
```

---

## Migration Checklist

Use this checklist for all upgrades:

- [ ] **Read release notes and CHANGELOG.md**
- [ ] **Backup database** (`cp data/app.db data/app.db.backup.$(date +%Y%m%d)`)
- [ ] **Backup .env file** (`cp .env .env.backup`)
- [ ] **Backup YouTube videos** (if enabled)
- [ ] **Pull new version** (Docker: `docker pull`, Local: `git pull`)
- [ ] **Compare .env.example** (check for new variables)
- [ ] **Update .env** (add any new required variables)
- [ ] **Run database migrations** (`python -m app.cli.migrate_db`)
- [ ] **Restart bot** (Docker: `docker restart`, Local: restart process)
- [ ] **Test functionality** (send test URL to bot)
- [ ] **Check logs** (verify no errors)
- [ ] **Verify database integrity** (`PRAGMA integrity_check`)
- [ ] **Monitor for 24 hours** (watch for issues)
- [ ] **Delete old backups** (after 7 days if stable)

---

## Troubleshooting

### Migration fails

**Symptom:** Error during `migrate_db`

**Solution:**

```bash
# Check database integrity
sqlite3 data/app.db "PRAGMA integrity_check;"

# If corrupted, restore from backup
cp data/app.db.backup.YYYYMMDD data/app.db

# Retry migration
python -m app.cli.migrate_db
```

---

### Bot won't start after upgrade

**Symptom:** Bot crashes on startup

**Diagnostics:**

```bash
# Check logs
docker logs bite-size-reader

# Common causes:
# 1. Missing environment variables
# 2. Database schema mismatch
# 3. Dependency conflicts

# Solution: Rollback and report issue
```

---

### Summaries not accessible

**Symptom:** Search/retrieval fails for old summaries

**Solution:**

```bash
# Rebuild search index
python -m app.cli.rebuild_indexes

# Backfill ChromaDB embeddings (if enabled)
python -m app.cli.backfill_chroma_store

# Verify
sqlite3 data/app.db "SELECT COUNT(*) FROM summaries;"
```

---

## Automated Update (Advanced)

### Watchtower (Docker)

```bash
# Install Watchtower to auto-update containers
docker run -d \
  --name watchtower \
  -v /var/run/docker.sock:/var/run/docker.sock \
  containrrr/watchtower \
  --cleanup \
  --interval 86400 \
  bite-size-reader

# Watchtower checks daily and updates if new version available
```

**Warning:** Automated updates skip backup step. Use with caution.

---

## See Also

- [CHANGELOG.md](../../CHANGELOG.md) - Version history
- [DEPLOYMENT.md](../DEPLOYMENT.md) - Deployment guide
- [TROUBLESHOOTING.md](../TROUBLESHOOTING.md) - Fix issues
- [Backup and Restore Guide](backup-and-restore.md) - Data protection

---

**Last Updated:** 2026-02-09
