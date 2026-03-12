---
name: developing-web-frontend
description: >
  Develop the Carbon web frontend (web/) -- routing, auth, API integration,
  components, testing, and same-host FastAPI serving. Triggers: Carbon, React,
  Vite, web frontend, web app, /web, frontend component, web route.
version: 2.0.0
allowed-tools: Bash, Read, Grep, Write
---

# Developing Web Frontend

Implement and debug the Carbon web interface in `web/`.

## Dynamic Context

!cd web && node -e "const p=JSON.parse(require('fs').readFileSync('package.json'));console.log('React:',p.dependencies.react,'Carbon:',p.dependencies['@carbon/react'])"

See also: [references/route-map.md](references/route-map.md)

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

## Auth Model

1. `telegram-webapp` mode:
   - Trigger: `window.Telegram.WebApp.initData` exists
   - Header: `X-Telegram-Init-Data`

2. `jwt` mode:
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

## Carbon Component Conventions

- Named imports: `import { Button, DataTable } from '@carbon/react'`
- Icons: `import { Add, TrashCan } from '@carbon/icons-react'`
- Theme tokens: use Carbon CSS custom properties (`--cds-*`), never raw hex/rgb
- Layout: use `<Grid>`, `<Column>` from `@carbon/react`, not custom grid CSS
- Spacing/typography: prefer Carbon design tokens over ad-hoc values
- Shell: global `Header` + `SideNav` live in `web/src/components/AppShell.tsx`

## Testing Patterns

- **Framework:** Vitest + React Testing Library
- **Test location:** colocated `*.test.tsx` files alongside source in `web/src/`
- **Run tests:** `cd web && npm run test`
- **What to mock:**
  - API client (`web/src/api/client.ts`) for network isolation
  - Auth context (`web/src/auth/AuthProvider.tsx`) for route guard tests
  - React Router context when testing page components
- **Assertions:** prefer `screen.getByRole` / `screen.getByText` over test IDs
- **Async:** use `waitFor` / `findBy*` for data-fetching components

## Common Pitfalls

- Env vars must use `VITE_` prefix to be exposed to client code
- Router basename must match `VITE_ROUTER_BASENAME` (default `/web`)
- Static assets go in `web/public/` and are served at `/static/web/`
- Build output goes to `app/static/web/` (not `web/dist/`) -- see `vite.config.ts`
- Digest endpoints require Telegram WebApp auth context; they fail in browser JWT mode
- Feature flags in `web/src/routes/features.ts` gate experimental routes
