# Carbon Web Frontend Guide

Reference for the Carbon-based web interface implemented in `web/`.

**Audience:** Frontend developers, integrators, operators
**Type:** Reference
**Related:** [README.md § Carbon Web Interface](README.md#carbon-web-interface-v1), [docs/MOBILE_API_SPEC.md](docs/MOBILE_API_SPEC.md), [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

---

## Overview

The web interface is the sole frontend surface — a standalone SPA built with:

- React 18 + TypeScript + Vite
- IBM Carbon (`@carbon/react`, `@carbon/styles`, `@carbon/icons-react`)
- `@tanstack/react-query` for server state and polling

It is built into `app/static/web` and served by FastAPI on `/web` and `/web/*`.

---

## Directory Layout

```text
web/
  src/
    api/            # Typed API gateway + envelope normalization
    auth/           # Hybrid auth provider, guards, storage, redirects
    components/     # App shell + shared UI
    features/       # Route-level pages (library/search/submit/collections/...)
    routes/         # Feature flags
  vite.config.ts    # base=/static/web, outDir=../app/static/web
```

---

## Serving Contract

- Static assets: `/static/web/*`
- SPA entrypoint: `/web` and `/web/{path:path}`
- FastAPI implementation: `app/api/main.py` (`web_interface` route)
- If bundle is missing, backend returns `404 "Web interface is not built"`

Build output contract:

- Vite `outDir`: `../app/static/web`
- Vite `base`: `/static/web/`

---

## Route Map

- `/web/library`
- `/web/library/:id`
- `/web/articles`
- `/web/search`
- `/web/submit`
- `/web/collections`
- `/web/collections/:id`
- `/web/digest`
- `/web/preferences`
- `/web/admin`
- `/web/login`

Route-level feature flags live in `web/src/routes/features.ts`.

---

## Authentication Model

Auth is hybrid and selected at runtime in `detectAuthMode`:

1. `telegram-webapp` mode
   - Trigger: `window.Telegram.WebApp.initData` exists
   - Request header: `X-Telegram-Init-Data`
   - Typical use: launched from Telegram Mini App context

2. `jwt` mode
   - Trigger: no WebApp initData
   - Login: Telegram Login Widget -> `POST /v1/auth/telegram-login`
   - Client id: `web-carbon-v1`
   - Session: bearer token storage + auto refresh via `POST /v1/auth/refresh`

Auth provider implementation: `web/src/auth/AuthProvider.tsx`.

---

## API Layer Conventions

The frontend API gateway (`web/src/api/client.ts`) provides:

- Envelope handling (`success/data/meta/error`)
- Mixed key-style normalization (`snake_case` + `camelCase`)
- Standard error mapping
- JWT refresh retry on `401` in JWT mode
- Automatic auth header injection based on active auth mode

Submission flow (`web/src/features/submit`) includes:

- URL validation + duplicate pre-check
- Status polling lifecycle (`pending` -> `crawling|processing` -> `completed|failed`)
- Retry operation for failed requests

Search flow includes advanced filters:

- Mode (`auto|keyword|semantic|hybrid`)
- Language, read/favorite state, date range
- Tag/domain multi-select and similarity threshold

Collections flow includes:

- Tree view navigation
- Add/remove/move/reorder items
- Inline create/rename/delete operations

Digest flow parity (web route `/web/digest`) includes:

- Channel subscriptions
- Digest preferences
- Trigger digest now / trigger single-channel (owner)
- Delivery history

Note: digest endpoints require Telegram WebApp auth context.

Admin page (`/web/admin`) includes:

- Database info (file size, table row counts)
- Cache controls (clear Redis URL cache)

---

## UI Architecture

- Global shell: Carbon `Header` + `SideNav` (`web/src/components/AppShell.tsx`)
- Session UX:
  - in-app session status label
  - manual "Verify session" action
  - inline session warnings + re-auth actions
- Read experience polish (`/web/library/:id`):
  - reading progress bar
  - text size + density controls
  - copy/share helpers
  - favorite/read/collection actions

---

## Local Development

```bash
cd web
npm ci
npm run dev
```

Optional environment variables:

- `VITE_API_BASE_URL` (default: same-origin)
- `VITE_TELEGRAM_BOT_USERNAME` (required for JWT mode login widget)
- `VITE_ROUTER_BASENAME` (default: `/web`)

When testing same-host serving (instead of Vite proxy):

```bash
cd web
npm run build
cd ..
uvicorn app.api.main:app --reload
# open http://localhost:8000/web/library
```

---

## Quality Checks

Web commands:

```bash
cd web
npm run lint
npm run typecheck
npm run check:static
npm run test
npm run test:e2e
npm run build
```

CI jobs in `.github/workflows/ci.yml`:

- `web-build`
- `web-test`
- `web-static-check`

---

## Deployment Notes

- `Dockerfile` and `Dockerfile.api` both build `web/`.
- Runtime image ships the static bundle at `/app/app/static/web`.
- Same-host deployment avoids CORS complexity.

---

## Troubleshooting

### `/web` returns 404

Web bundle is not built into `app/static/web`.

```bash
cd web
npm ci
npm run build
```

### Login page shows "Missing configuration"

`VITE_TELEGRAM_BOT_USERNAME` is not set for JWT mode.

### Digest page fails outside Telegram

Digest endpoints require Telegram WebApp `initData`; use Telegram-launched context.

### Repeated auth failures in browser mode

Clear stored tokens (login page has "Clear local session") and sign in again.

---

**Last Updated:** 2026-03-17
