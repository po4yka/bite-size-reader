---
name: developing-web-frontend
description: >
  Develop the web frontend (`clients/web/`) -- routing, auth, API integration,
  components, testing, and same-host FastAPI serving. Triggers: web frontend,
  React, Vite, web app, /web, frontend component, web route, design shim.
version: 2.3.0
allowed-tools: Bash, Read, Grep, Write
---

# Developing Web Frontend

Implement and debug the web interface in `clients/web/`.

## Dynamic Context

!cd clients/web && node -e "const p=JSON.parse(require('fs').readFileSync('package.json'));console.log('React:',p.dependencies.react)"

See also: [references/route-map.md](references/route-map.md)

## Scope

- React + TypeScript + Vite app in `clients/web/`
- Project-owned design shim under `clients/web/src/design/` (primitives, table,
  modal, navigation, structure, shell, icons, tokens). Feature code imports
  exclusively from `../design`.
- Route guards and auth flow
- API layer (`clients/web/src/api/*`) with envelope normalization and token refresh
- Same-host deployment contract (`/web`, `/static/web`)

## Primary References

- `docs/reference/frontend-web.md` (canonical frontend guide)
- `clients/web/src/App.tsx` (React Router wiring)
- `clients/web/src/routes/manifest.tsx` (route manifest and nav metadata)
- `clients/web/src/auth/AuthProvider.tsx` (hybrid auth provider)
- `clients/web/src/api/client.ts` (gateway + refresh behavior)
- `clients/web/vite.config.ts` (build output and static base)
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
cd clients/web
npm ci
npm run dev
```

### Required checks before finishing

```bash
cd clients/web
npm run check:static
npm run test
```

Optional:

```bash
cd clients/web
npm run test:e2e
npm run build
```

## Same-host Serve Validation

```bash
cd clients/web && npm run build
cd ..
uvicorn app.api.main:app --reload
# open http://localhost:8000/web/library
```

If `/web` returns 404:

- Ensure `app/static/web/index.html` exists
- Rebuild the `clients/web/` bundle

## Common Debug Patterns

### Auth failures

- Check mode detection in `clients/web/src/auth/mode.ts`
- Verify headers sent from `clients/web/src/api/client.ts`
- For JWT mode, confirm `VITE_TELEGRAM_BOT_USERNAME` is configured

### Route issues

- Check router basename in `clients/web/src/main.tsx` (`VITE_ROUTER_BASENAME`, default `/web`)
- Validate route registration in `clients/web/src/App.tsx` and `clients/web/src/routes/manifest.tsx`
- Confirm FastAPI `/web/{path:path}` handler returns SPA index

### API shape mismatch

- Inspect type mapping in `clients/web/src/api/*`
- Ensure snake_case/camelCase normalization works via `clients/web/src/lib/case.ts`
- Confirm envelope expectations (`success`, `data`, `error`)

## Telegram Mini App Integration

The frontend runs in two contexts: inside Telegram as a Mini App (`telegram-webapp` mode) and in a regular browser (`jwt` mode). Components must handle both.

Integration points:

| Concern | File | Notes |
|---|---|---|
| Type declarations | `clients/web/src/telegram.d.ts` | `TelegramWebApp`, `TelegramMainButton`, `TelegramBackButton` interfaces |
| App bootstrap / theme sync | `clients/web/src/main.tsx` | Maps `themeParams` to CSS vars; calls `webApp.ready()` / `expand()` |
| Safe area insets | `clients/web/src/styles.css` | `--tg-safe-area-inset-*`, `--tg-viewport-stable-height` |
| BackButton | `clients/web/src/components/AppShell.tsx` | Shown on non-root routes; `navigate(-1)` fallback to `/library` |
| MainButton hook | `clients/web/src/hooks/useTelegramMainButton.ts` | Declarative; only activates in `telegram-webapp` mode |
| Closing confirmation | `clients/web/src/hooks/useTelegramClosingConfirmation.ts` | Pass `isDirty` flag; protects unsaved forms |
| Auth mode detection | `clients/web/src/auth/mode.ts` | Checks `window.Telegram?.WebApp?.initData` |

Rules:

- Always use optional chaining: `window.Telegram?.WebApp` — the object is undefined in browser mode
- No third-party Telegram SDK (`@twa-dev/sdk`) — use direct `window.Telegram.WebApp` per `telegram.d.ts`
- Digest endpoints only work in `telegram-webapp` mode; show an informational message in JWT mode
- For viewport-sensitive layouts use `var(--tg-viewport-stable-height, 100dvh)`, not `100vh`
- Guard Telegram-specific logic with `const { mode } = useAuth()` before calling any hook

## Design Shim Conventions

Named imports only; always import from `../design`. The shim layer lives in
`clients/web/src/design/` and is the single source of truth for primitives,
table, modal, navigation, and icons. Add new components by extending the
design directory; never reach for an external design system in feature code.

- Components: `import { Button, DataTable } from "../design"` (path adjusts per file depth)
- Icons: `import { Add, TrashCan } from "../design"` (icons are co-exported)
- Theme tokens: use `--rtk-*` CSS custom properties from `clients/web/src/design/tokens.css`; never raw hex/rgb
- Shell: global `Header` + `SideNav` live in `clients/web/src/components/AppShell.tsx`

## Design Skill Interaction

Animation and polish principles from `emil-design-eng` apply to custom UI
elements built with the design shim. The shim itself is intentionally
minimal — feature code is free to layer transitions and microinteractions
onto shim primitives.

## Testing Patterns

- **Framework:** Vitest + React Testing Library
- **Test location:** colocated `*.test.tsx` files alongside source in `clients/web/src/`
- **Run tests:** `cd clients/web && npm run test`
- **What to mock:**
  - API client (`clients/web/src/api/client.ts`) for network isolation
  - Auth context (`clients/web/src/auth/AuthProvider.tsx`) for route guard tests
  - React Router context when testing page components
- **Assertions:** prefer `screen.getByRole` / `screen.getByText` over test IDs
- **Async:** use `waitFor` / `findBy*` for data-fetching components

## Common Pitfalls

- Env vars must use `VITE_` prefix to be exposed to client code
- Router basename must match `VITE_ROUTER_BASENAME` (default `/web`)
- Static assets go in `clients/web/public/` and are served at `/static/web/`
- Build output goes to `app/static/web/` (not `clients/web/dist/`) -- see `clients/web/vite.config.ts`
- Digest endpoints require Telegram WebApp auth context; they fail in browser JWT mode
- Feature flags in `clients/web/src/routes/features.ts` gate experimental routes
