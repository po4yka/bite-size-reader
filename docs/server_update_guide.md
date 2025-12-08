# Server Update & Deployment Checklist

How to pull the latest Bite-Size Reader code onto a Linux host and redeploy the Dockerized service (assumes initial setup via `DEPLOYMENT.md`).

## 1) Prereqs
- SSH to host; repo at `/opt/bite-size-reader` (adjust if different).
- Docker Engine + Compose plugin.
- `.env` with all secrets; `data/` volume for SQLite persistence and backups.

## 2) Safety first
1. Backup DB + env:
   ```bash
   cd /opt/bite-size-reader
   tar czf ~/bite-size-reader-backup-$(date +%Y%m%d%H%M).tgz data app.db .env
   ```
   (Container also writes backups to `data/backups/`.)
2. Clean tree:
   ```bash
   git status
   ```
   Stash local overrides (e.g., `docker-compose.override.yml`) before pulling.

## 3) Pull latest
```bash
cd /opt/bite-size-reader
git fetch --all --prune
git checkout main
git pull --ff-only
```
Pin to a tag:
```bash
git checkout tags/<tag>
```

## 4) Refresh deps (when pyproject/lock changed)
```bash
make lock-uv   # or: make lock-piptools
```

## 5) Rebuild & redeploy
- Docker:
  ```bash
  sudo docker stop bsr || true
  sudo docker rm bsr || true
  sudo docker build -t bite-size-reader:latest .
  sudo docker run -d \
    --env-file .env \
    -v $(pwd)/data:/data \
    -p 8000:8000 \  # expose API if needed
    --name bsr \
    --restart unless-stopped \
    bite-size-reader:latest
  ```
- Compose:
  ```bash
  sudo docker compose down
  sudo docker compose up -d --build
  ```

## 6) Verify
```bash
sudo docker ps
sudo docker logs -f bsr
```
- Send a test from a whitelisted Telegram account (`/help`, URL, or forwarded post).
- Optionally inspect `data/app.db` for new requests.

## 7) Rollback
- Stop container, restore backup tarball, restart previous image (Docker retains older images unless pruned).
- Quick revert to prior commit:
  ```bash
  git checkout <previous-commit-sha>
  sudo docker compose up -d --build
  ```

## 8) Troubleshooting
- Missing deps: rebuild image.
- Secrets/env: recheck `.env` (quote special chars).
- Telegram auth: verify `API_ID`, `API_HASH`, `BOT_TOKEN`; ensure bot not banned.
- Firecrawl/OpenRouter: confirm keys; consider reducing `MAX_CONCURRENT_CALLS`.
- DB perms: ensure host `data/` is writable by Docker user.

Use this checklist to keep production aligned with the repo while protecting data and minimizing downtime.
