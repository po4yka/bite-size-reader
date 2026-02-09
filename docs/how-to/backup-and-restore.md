# How to Backup and Restore

Protect your data with regular backups and restore procedures.

**Audience:** Operators
**Difficulty:** Beginner
**Estimated Time:** 10 minutes

---

## What to Backup

Bite-Size Reader stores data in three locations:

1. **SQLite Database** (`data/app.db`) - **CRITICAL**
   - All summaries, requests, LLM calls
   - User interactions, audit logs
   - Size: ~1-100 MB depending on usage

2. **Environment File** (`.env`) - **IMPORTANT**
   - API keys, configuration
   - Size: ~5 KB

3. **YouTube Videos** (`data/videos/`) - **OPTIONAL**
   - Downloaded videos and metadata
   - Size: Can be 100 GB+

4. **ChromaDB Data** (`chroma_data/`) - **OPTIONAL**
   - Vector embeddings (can be regenerated)
   - Size: ~10-500 MB

---

## Manual Backup

### Quick Backup (Database Only)

```bash
# Backup database with timestamp
cp data/app.db data/app.db.backup.$(date +%Y%m%d-%H%M%S)

# Verify backup
ls -lh data/app.db.backup*
```

### Full Backup (All Data)

```bash
# Create backup directory
mkdir -p backups/$(date +%Y%m%d)

# Backup database
cp data/app.db backups/$(date +%Y%m%d)/app.db

# Backup environment file
cp .env backups/$(date +%Y%m%d)/.env

# Backup YouTube videos (if enabled)
tar -czf backups/$(date +%Y%m%d)/videos.tar.gz data/videos/

# Backup ChromaDB (if enabled)
tar -czf backups/$(date +%Y%m%d)/chroma.tar.gz chroma_data/

# Verify backups
ls -lh backups/$(date +%Y%m%d)/
```

---

## Automated Backup

### Daily Backup Script

Create `scripts/backup.sh`:

```bash
#!/bin/bash
set -e

# Configuration
BACKUP_DIR="/path/to/backups"
RETENTION_DAYS=30

# Create backup directory with date
BACKUP_DATE=$(date +%Y%m%d-%H%M%S)
BACKUP_PATH="$BACKUP_DIR/$BACKUP_DATE"
mkdir -p "$BACKUP_PATH"

# Backup database
echo "Backing up database..."
cp data/app.db "$BACKUP_PATH/app.db"

# Backup environment (exclude sensitive data from git)
cp .env "$BACKUP_PATH/.env"

# Backup YouTube videos (if exists)
if [ -d "data/videos" ]; then
    echo "Backing up YouTube videos..."
    tar -czf "$BACKUP_PATH/videos.tar.gz" data/videos/
fi

# Backup ChromaDB (if exists)
if [ -d "chroma_data" ]; then
    echo "Backing up ChromaDB..."
    tar -czf "$BACKUP_PATH/chroma.tar.gz" chroma_data/
fi

# Cleanup old backups (older than RETENTION_DAYS)
echo "Cleaning up old backups (>$RETENTION_DAYS days)..."
find "$BACKUP_DIR" -type d -mtime +$RETENTION_DAYS -exec rm -rf {} +

echo "Backup complete: $BACKUP_PATH"
```

Make executable and test:

```bash
chmod +x scripts/backup.sh
./scripts/backup.sh
```

### Schedule with Cron

```bash
# Edit crontab
crontab -e

# Add daily backup at 2 AM
0 2 * * * cd /path/to/bite-size-reader && ./scripts/backup.sh >> /var/log/bsr-backup.log 2>&1
```

### Docker Volume Backup

```bash
# Backup Docker volume
docker run --rm \
  -v bite-size-reader_data:/data \
  -v $(pwd)/backups:/backup \
  alpine tar -czf /backup/data_backup_$(date +%Y%m%d).tar.gz /data
```

---

## Remote Backup

### Sync to Cloud Storage

**AWS S3:**

```bash
# Install AWS CLI
pip install awscli

# Configure
aws configure

# Sync backups to S3
aws s3 sync backups/ s3://your-bucket/bite-size-reader-backups/
```

**Rclone (Any Cloud Provider):**

```bash
# Install rclone
curl https://rclone.org/install.sh | sudo bash

# Configure remote (interactive)
rclone config

# Sync backups
rclone sync backups/ remote:bite-size-reader-backups/
```

**rsync (Remote Server):**

```bash
# Sync to remote server
rsync -avz --delete backups/ user@remote:/backups/bite-size-reader/
```

---

## Restore Procedures

### Restore Database Only

```bash
# Stop bot
docker stop bite-size-reader  # or Ctrl+C if local

# Backup current database (precaution)
cp data/app.db data/app.db.before-restore

# Restore from backup
cp backups/YYYYMMDD/app.db data/app.db

# Verify integrity
sqlite3 data/app.db "PRAGMA integrity_check;"
# Should output: ok

# Restart bot
docker start bite-size-reader  # or python bot.py
```

### Restore Full Backup

```bash
# Stop bot
docker stop bite-size-reader

# Restore database
cp backups/YYYYMMDD/app.db data/app.db

# Restore environment
cp backups/YYYYMMDD/.env .env

# Restore YouTube videos (if needed)
tar -xzf backups/YYYYMMDD/videos.tar.gz -C /

# Restore ChromaDB (if needed)
tar -xzf backups/YYYYMMDD/chroma.tar.gz -C /

# Verify database
sqlite3 data/app.db "PRAGMA integrity_check;"

# Restart bot
docker start bite-size-reader
```

### Restore to New Server

```bash
# Copy backups to new server
scp -r backups/YYYYMMDD/ user@new-server:/tmp/

# On new server:
# 1. Install Bite-Size Reader (see DEPLOYMENT.md)
# 2. Restore data
cp /tmp/YYYYMMDD/app.db data/app.db
cp /tmp/YYYYMMDD/.env .env

# 3. Start bot
docker run -d \
  --name bite-size-reader \
  --env-file .env \
  -v $(pwd)/data:/data \
  ghcr.io/po4yka/bite-size-reader:latest
```

---

## Database Maintenance

### Vacuum Database

Reclaim space after deleting records:

```bash
# Stop bot
docker stop bite-size-reader

# Vacuum
sqlite3 data/app.db "VACUUM;"

# Verify size reduction
ls -lh data/app.db

# Restart bot
docker start bite-size-reader
```

### Verify Integrity

```bash
# Check database integrity
sqlite3 data/app.db "PRAGMA integrity_check;"

# Expected output: ok

# If corrupted:
# Restore from latest backup
```

### Rebuild Indexes

```bash
# Rebuild search indexes
python -m app.cli.rebuild_indexes

# Rebuild ChromaDB embeddings
python -m app.cli.backfill_chroma_store --rebuild
```

---

## Disaster Recovery

### Database Corruption

**Symptom:** "Database disk image is malformed"

**Recovery:**

```bash
# 1. Stop bot immediately
docker stop bite-size-reader

# 2. Attempt recovery
sqlite3 data/app.db ".recover" | sqlite3 data/app.db.recovered

# 3. If recovery works, replace
mv data/app.db data/app.db.corrupted
mv data/app.db.recovered data/app.db

# 4. If recovery fails, restore from backup
cp backups/YYYYMMDD/app.db data/app.db

# 5. Restart bot
docker start bite-size-reader
```

### Lost Backups

**Prevention:**

- Multiple backup locations (local + cloud)
- Test restores regularly (monthly)
- Monitor backup script execution

**If no backups:**

- Database is unrecoverable
- Must start fresh (lose all summaries)
- Lesson: Set up automated backups immediately

---

## Backup Best Practices

### Frequency

- **Database**: Daily (critical data)
- **Videos**: Weekly or on-demand (regenerable via re-download)
- **ChromaDB**: Weekly (regenerable from database)
- **Environment**: On every config change

### Retention

```bash
# Suggested retention policy
Daily backups: Keep 7 days
Weekly backups: Keep 4 weeks
Monthly backups: Keep 12 months
```

### Testing

```bash
# Monthly restore test
# 1. Restore to test environment
# 2. Verify bot starts
# 3. Verify summaries accessible
# 4. Delete test environment
```

### Security

```bash
# Encrypt backups containing API keys
tar -czf - backups/YYYYMMDD/ | \
  openssl enc -aes-256-cbc -salt -out backups/YYYYMMDD.tar.gz.enc

# Decrypt when needed
openssl enc -aes-256-cbc -d -in backups/YYYYMMDD.tar.gz.enc | \
  tar -xz
```

---

## Monitoring Backups

### Check Backup Age

```bash
# Find latest backup
ls -lt backups/ | head -5

# Alert if backup older than 48 hours
LATEST=$(ls -t backups/ | head -1)
AGE=$(( ($(date +%s) - $(stat -f %m "backups/$LATEST")) / 3600 ))

if [ $AGE -gt 48 ]; then
    echo "WARNING: Latest backup is $AGE hours old!"
fi
```

### Backup Size Monitoring

```bash
# Track backup size growth
du -sh backups/*

# Alert if backup size >10 GB (unexpected)
SIZE=$(du -s backups/ | awk '{print $1}')
if [ $SIZE -gt 10485760 ]; then  # 10 GB in KB
    echo "WARNING: Backups larger than 10 GB!"
fi
```

---

## Export Summaries (Alternative Backup)

### Export to JSON

```bash
# Export all summaries
python -m app.cli.export_summaries --format json --output summaries.json

# Export specific date range
python -m app.cli.export_summaries \
  --format json \
  --start-date 2026-01-01 \
  --end-date 2026-02-09 \
  --output summaries_jan.json
```

### Export to CSV

```bash
# Export summaries as CSV
sqlite3 data/app.db -header -csv \
  "SELECT id, url, title, created_at FROM summaries;" \
  > summaries.csv
```

### Export to Markdown

```bash
# Export summaries as Markdown files
python -m app.cli.export_summaries --format markdown --output-dir summaries_md/

# One .md file per summary
```

---

## See Also

- [DEPLOYMENT.md](../DEPLOYMENT.md) - Production deployment
- [How to Migrate Versions](migrate-versions.md) - Upgrade procedures
- [TROUBLESHOOTING § Database Issues](../TROUBLESHOOTING.md#database-issues)

---

**Last Updated:** 2026-02-09
