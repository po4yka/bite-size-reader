---
name: web-frontend
description: Work on the Carbon web frontend (`web/`) including routing, auth, API integration, static checks, and same-host FastAPI serving (`/web`, `/static/web`). Use for React/Vite/Carbon frontend tasks.
version: 1.0.0
allowed-tools: Bash, Read, Grep, Write
---

# Web Frontend Skill

Implement and debug the Carbon web interface in `web/`.

## Scope

- React + TypeScript + Vite app in `web/`
- Carbon UI components and app shell
- Route guards and auth flow
- API layer (`web/src/api/*`) with envelope normalization and token refresh
- Same-host deployment contract (`/web`, `/static/web`)

## Primary References

- `FRONTEND.md` (canonical frontend guide)
- `web/src/App.tsx` (route map)
- `web/src/auth/AuthProvider.tsx` (hybrid auth provider)
- `web/src/api/client.ts` (gateway + refresh behavior)
- `web/vite.config.ts` (build output and static base)
- `app/api/main.py` (SPA route serving)

## Route Map (current)

- `/web/library`
- `/web/library/:id`
- `/web/articles`
- `/web/search`
- `/web/submit`
- `/web/collections`
- `/web/collections/:id`
- `/web/digest`
- `/web/preferences`
- `/web/login`

## Auth Model

1. `telegram-webapp` mode:

- Trigger: `window.Telegram.WebApp.initData` exists
- Header: `X-Telegram-Init-Data`

1. `jwt` mode:

- Trigger: no initData
- Login widget -> `POST /v1/auth/telegram-login`
- Uses `client_id=web-carbon-v1`
- Bearer auth + refresh via `POST /v1/auth/refresh`

## Local Workflow

```bash
cd web
npm ci
npm run dev
```

### Required checks before finishing

```bash
cd web
npm run check:static
npm run test
```

Optional:

```bash
cd web
npm run test:e2e
npm run build
```

## Same-host Serve Validation

```bash
cd web && npm run build
cd ..
uvicorn app.api.main:app --reload
# open http://localhost:8000/web/library
```

If `/web` returns 404:

- Ensure `app/static/web/index.html` exists
- Rebuild `web/` bundle

## Common Debug Patterns

### Auth failures

- Check mode detection in `web/src/auth/mode.ts`
- Verify headers sent from `web/src/api/client.ts`
- For JWT mode, confirm `VITE_TELEGRAM_BOT_USERNAME` is configured

### Route issues

- Check router basename in `web/src/main.tsx` (`VITE_ROUTER_BASENAME`, default `/web`)
- Validate route registration in `web/src/App.tsx`
- Confirm FastAPI `/web/{path:path}` handler returns SPA index

### API shape mismatch

- Inspect type mapping in `web/src/api/*`
- Ensure snake_case/camelCase normalization works via `web/src/lib/case.ts`
- Confirm envelope expectations (`success`, `data`, `error`)
