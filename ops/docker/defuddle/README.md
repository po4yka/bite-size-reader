This directory contains the self-hosted Defuddle sidecar — a minimal Fastify server that fetches pages via Playwright Chromium and extracts clean Markdown using the [defuddle](https://github.com/kepano/defuddle) library. It replaces the public `defuddle.md` endpoint with an internal Docker service, so content extraction never leaves the stack. Build and start it alongside the rest of the scraper sidecars:

```
docker compose -f ops/docker/docker-compose.yml --profile with-scrapers build defuddle-api
docker compose -f ops/docker/docker-compose.yml --profile with-scrapers up -d
```

The service listens on internal port `3003` (no host binding). The `ratatoskr` and `mobile-api` containers reach it at `http://defuddle-api:3003` via Docker DNS, controlled by `SCRAPER_DEFUDDLE_API_BASE_URL`.
