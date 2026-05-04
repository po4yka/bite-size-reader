# How to Migrate from `bite-size-reader` to Ratatoskr

This page is the operational guide for self-hosters upgrading across
the project rename. The rename is mechanical (no behavioural change),
but it touches several stable contracts (Docker image tags, MCP URIs,
HTTP cookies, Prometheus metric names) so most upgrades require a
short checklist of follow-up actions.

**Audience:** Operators upgrading an existing deployment.
**Difficulty:** Beginner if you run the default `docker-compose.yml`,
intermediate if you operate Grafana / Prometheus dashboards or have
external MCP / webhook integrations.
**Estimated Time:** 5–15 minutes depending on integrations.
**Related:** [DEPLOYMENT.md](../DEPLOYMENT.md),
[Migrate Versions (general)](migrate-versions.md),
[`CHANGELOG.md`](../../CHANGELOG.md) for the canonical breaking-change list.

---

## TL;DR

You're upgrading; here are the four things you must touch yourself —
everything else either auto-migrates or has a sensible default:

1. **Docker image / compose service names.** `bite-size-reader` → `ratatoskr`.
2. **`.env` file** — small set of default values changed; the Karakeep
   block goes away entirely (the integration has been retired).
3. **MCP client configs** — `bsr://` URIs and `X-BSR-*` headers → `ratatoskr` /
   `X-Ratatoskr-*`.
4. **Web bookmarks / browser sessions** — storage keys were renamed, so
   anyone with an open web session will be logged out and need to
   sign in again.

The rest of this page expands those four into a numbered checklist.

---

## Auto-migrated for you

Don't lose sleep over these — the code or the build handles them:

- **Database filename.** When `DB_PATH` ends in `ratatoskr.db` and
  `app.db` exists in the same directory, `DatabaseSessionManager` renames
  the file on first start. The default config triggers this; custom
  paths that don't end in `ratatoskr.db` are left alone (rename manually
  if you want consistency).
- **Telethon bot session.** Bot sessions are keyed by `BOT_TOKEN`, not
  username, so a bot-handle change (`bite_size_reader_bot` →
  `ratatoskr_tldr_bot`) only requires updating `BOT_TOKEN` and
  `VITE_TELEGRAM_BOT_USERNAME` in `.env` and rebuilding the web bundle.
- **Lock files.** `uv.lock`, `requirements.txt`, `requirements-dev.txt`,
  and `clients/web/package-lock.json` are regenerated as part of the
  rename PR — your build will pull the right artifact.
- **Container labels (Loki / Promtail).** Compose recreates containers
  with their new names on `up`; old log labels stop appearing as soon
  as the previous containers are removed.

---

## You must do this yourself

### 1. Update Docker image references

```sh
cd /path/to/your/checkout
git pull
docker compose -f ops/docker/docker-compose.yml down
docker compose -f ops/docker/docker-compose.yml build
docker compose -f ops/docker/docker-compose.yml up -d
```

If you pin `ghcr.io/po4yka/bite-size-reader:*` in any downstream
pipeline (CI, Watchtower, Argo CD, etc.), switch the image path to
`ghcr.io/po4yka/ratatoskr:*`. GitHub redirects from the old path do
work for `docker pull`, but the redirect can break authenticated
login flows; pin the new path explicitly.

### 2. Update your `.env`

The shipped `.env.example` is updated. If you copied it once and
hand-edited since, only a handful of values changed defaults:

| Variable | Old default | New default |
| --- | --- | --- |
| `FIRECRAWL_SELF_HOSTED_API_KEY` | `fc-bsr-local` | `fc-ratatoskr-local` |
| `REDIS_PREFIX` | `bsr` | `ratatoskr` |
| `DB_PATH` | `/data/app.db` | `/data/ratatoskr.db` |
| `OPENROUTER_HTTP_REFERER` | `https://github.com/po4yka/bite-size-reader` | `https://github.com/po4yka/ratatoskr` |
| `OPENROUTER_X_TITLE` | `Bite-Size Reader` | `Ratatoskr` |
| `*_RUST_BIN` example paths (commented) | `…/bsr-*` | `…/ratatoskr-*` |

**Drop any `KARAKEEP_*` lines from your `.env`** — the Karakeep
integration has been retired and those variables are no longer read.

The repo ships an idempotent helper script that applies these changes
in place; it is not committed but lives at
`tools/scripts/migrate-env-example.sh` after running once. Or just edit
by hand with the table above as a guide.

### 3. Update MCP client configs

If any external AI agent connects via MCP (OpenClaw, Claude Desktop,
hosted SSE):

- **Resource URIs:** `bsr://*` → `ratatoskr://*` (15 paths, e.g.
  `bsr://articles/recent` → `ratatoskr://articles/recent`).
- **MCP server registration name:** if you pinned it as
  `"bite-size-reader"` in the client, change to `"ratatoskr"`.
- **Trusted-gateway forwarded headers:** `X-BSR-Forwarded-Access-Token`
  and `X-BSR-MCP-Forwarding-Secret` → `X-Ratatoskr-Forwarded-Access-Token`
  and `X-Ratatoskr-MCP-Forwarding-Secret`. Set them via the
  `MCP_FORWARDED_ACCESS_TOKEN_HEADER` and `MCP_FORWARDED_SECRET_HEADER`
  env vars if you need to keep the old header names temporarily for
  rolling deployments.

The full MCP surface (22 tools, 16 resources) is enumerated in
[`docs/reference/mcp-server.md`](../reference/mcp-server.md).

### 4. Update webhook receivers

If you subscribe to outgoing webhooks, update the signature / event
header names:

- `X-BSR-Signature` → `X-Ratatoskr-Signature`
- `X-BSR-Event` → `X-Ratatoskr-Event`

There is no compatibility shim. If you need a brief overlap period,
deploy a small reverse proxy that copies the new headers back into the
old names while you cut over.

### 5. Update Grafana / Prometheus dashboards

The repo ships updated dashboards (`ratatoskr-overview.json`,
`ratatoskr-aggregation.json`) and updated alerting rules; Compose
provisioning will pick them up automatically. The follow-up work on
your side:

- **Bookmarks.** Dashboard UIDs are renamed (`bsr-overview` →
  `ratatoskr-overview`, `bsr-aggregation` → `ratatoskr-aggregation`),
  so any saved Grafana URLs you keep will 404 — re-bookmark from the
  new dashboards.
- **Old time-series.** Existing `bsr_*` metric series remain in TSDB
  but stop collecting from this release. If you need historical
  continuity in queries, add a recording rule that aliases the old
  metric name to the new one (Prometheus has no built-in metric
  rename).
- **Loki labels.** `tenant_id`, `job`, and the log path under
  `/var/log/bsr/` switch to `ratatoskr`. Update any LogQL queries you
  rely on.

### 6. Reissue CLI logins (if you use the packaged CLI)

The `ratatoskr-cli` package replaces `bsr-cli` and writes its config to
`~/.config/ratatoskr/` instead of `~/.config/bsr/`. Existing tokens
under the old path are not migrated:

```sh
pip install --upgrade ratatoskr-cli  # or pipx reinstall ratatoskr-cli
ratatoskr login --server https://your-server.example.com ...
```

If your scripts read `BSR_SERVER_URL`, switch to `RATATOSKR_SERVER_URL`.
The console script renamed from `bsr` to `ratatoskr`.

### 7. Reissue web sessions

The web frontend's localStorage key changed
(`bsr_web_auth_tokens` → `ratatoskr_web_auth_tokens`) and the refresh
cookie changed (`bsr_refresh_token` → `ratatoskr_refresh_token`).
Anyone with an existing browser session will be effectively logged
out on first reload after the upgrade — they sign back in via the
normal flow. No server-side action required.

### 8. Flush old Redis keys (optional)

Existing `bsr:batch:*`, `bsr:query:*`, `bsr:embed:*`, `bsr:auth:*` keys
remain in Redis but are no longer read or written; they expire on
their own TTL. If you want to reclaim memory immediately, flush by
prefix:

```sh
redis-cli --scan --pattern 'bsr:*' | xargs -L 100 redis-cli del
```

---

## Grace periods and known gaps

- **Old Prometheus metric names** retain their last samples in TSDB but
  do not collect new data; there is no recording-rule shim shipped.
- **GHCR image redirect** from `po4yka/bite-size-reader` to
  `po4yka/ratatoskr` is best-effort GitHub behaviour — pin the new path
  in CI to avoid auth-flow breakage.
- **Karakeep integration** is removed in the same release. The canonical
  runtime migration path is now `app/cli/migrations/`; if an older local
  database still contains a `karakeep_sync` table, drop it manually after
  confirming you no longer need that data. Re-running the rename does not
  re-create the table.
- **The digest mini-app's built JS asset** in `app/static/digest/assets/`
  may still encode the old `bsr_library_filter` localStorage key in its
  bundled output until you rebuild the mini-app.
- **`OpenAPI` server URLs** advertise `https://ratatoskrapi.po4yka.com`,
  but the DNS record itself is not part of the rename PR — update DNS
  separately if you publish a hosted instance.

---

## Rollback

If something in your deployment depends on the old name in a way the
checklist above didn't anticipate:

1. **Pin the last pre-rename image.** Use the most recent tag of
   `ghcr.io/po4yka/bite-size-reader:*` from before the rename
   (or your own previously-built image). The image redirects at GHCR
   should make this work for `docker pull`.
2. **Restore your DB if the auto-rename did the wrong thing.** Pre-rename
   backups are in your usual backup location with the old prefix
   `bite_size_reader_backup_*` (sqlite) or `bsr-backup-*` (zip).
   Restore by stopping the bot, copying the backup back to
   `/data/app.db`, and pinning the old image.
3. **Old Redis keys are still readable** because Ratatoskr never deleted
   them — just point the old binary at the same Redis and it will pick
   up where it left off.

If rollback is required, please [open an
issue](https://github.com/po4yka/ratatoskr/issues) so the gap can be
fixed forward in the next release rather than leaving everyone on the
old name.
