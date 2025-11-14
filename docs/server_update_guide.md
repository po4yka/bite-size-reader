# Server Update & Deployment Checklist

This document describes how to pull the latest Bite‑Size Reader code onto a Linux server and (re)deploy the service with Docker. It assumes the project was already deployed once using the instructions in `DEPLOYMENT.md`.

## 1. Prerequisites
- SSH access to the target host.
- Existing clone of the repository, e.g. `/opt/bite-size-reader`.
- Docker Engine + Docker Compose Plugin installed on the server.
- A filled-in `.env` file on the server containing all required secrets (see `DEPLOYMENT.md`).
- Optional: `data/` directory mounted as a Docker volume for SQLite persistence (recommended).

## 2. Pre-update Safety Checks
1. **Back up the database and env file.**
   ```bash
   cd /opt/bite-size-reader
   tar czf ~/bite-size-reader-backup-$(date +%Y%m%d%H%M).tgz data app.db .env
   ```
   Adjust the paths if your deployment stores the SQLite file elsewhere. The container also creates timestamped backups under `data/backups/`—copy them off-host if needed.
2. **Inspect local changes.** Ensure the working tree is clean before pulling updates:
   ```bash
   git status
   ```
   If you have local modifications (e.g., `docker-compose.override.yml`), stash them first.

## 3. Pull the Latest Version
```bash
cd /opt/bite-size-reader
# Fetch tags and branches from origin
git fetch --all --prune
# Checkout the deployment branch (main by default)
git checkout main
# Fast-forward to the newest commit
git pull --ff-only
```
If you track a specific release tag, replace the last command with:
```bash
git checkout tags/<tag-name>
```

## 4. Refresh Dependencies (optional but recommended)
When `pyproject.toml` changes, rebuild the lock files so the Docker image uses the latest pins:
```bash
make lock-uv  # or: make lock-piptools
```
Commit the regenerated `requirements*.txt` if you maintain a fork.

## 5. Rebuild and Redeploy the Container
If you use raw Docker commands:
```bash
# Stop and remove the running container
sudo docker stop bsr || true
sudo docker rm bsr || true
# Build the new image
sudo docker build -t bite-size-reader:latest .
# Re-create the container with persisted data
sudo docker run -d \
  --env-file .env \
  -v $(pwd)/data:/data \
  --name bsr \
  --restart unless-stopped \
  bite-size-reader:latest
```

For Docker Compose deployments (`docker-compose.yml` in the repo root):
```bash
sudo docker compose down
sudo docker compose up -d --build
```

## 6. Post-deploy Verification
1. **Check container status and logs.**
   ```bash
   sudo docker ps
   sudo docker logs -f bsr
   ```
   Confirm there are no startup errors and that the bot connects to Telegram successfully.
2. **Send a test message.** From your Telegram account (listed in `ALLOWED_USER_IDS`), run `/help` or forward a URL to ensure summaries are produced.
3. **Confirm database writes.** Inspect `data/app.db` (or your mounted location) to verify new request entries if desired.

## 7. Rollback Strategy
- If the new version misbehaves, stop the container, restore the archived backup, and restart with the previous image tag (Docker keeps old images unless pruned).
- To redeploy the prior commit quickly:
  ```bash
  git checkout <previous-commit-sha>
  sudo docker compose up -d --build
  ```

## 8. Troubleshooting Checklist
- **Missing dependencies:** rebuild the image to ensure new Python packages are installed.
- **Environment secrets errors:** re-check `.env` formatting—values must be quoted if they contain spaces or special characters.
- **Telegram authorization failures:** verify `API_ID`, `API_HASH`, and `BOT_TOKEN` are correct and the bot is not banned.
- **Firecrawl/OpenRouter errors:** confirm API keys remain valid and consider reducing `MAX_CONCURRENT_CALLS` in `.env` if rate-limited.
- **Database permission errors:** ensure the host `data/` directory is writable by the Docker daemon user.

Following this checklist keeps the production bot aligned with the latest repository state while preserving data and minimizing downtime.
