# Web Frontend Route Map

Synced with `clients/web/src/App.tsx` and `clients/web/src/routes/manifest.tsx`. Update this file when routes change.

## Route Table

| Route | Component | Auth | Notes |
|---|---|---|---|
| `/web` | `HomeRedirect` | Yes | Redirects to `/web/library` |
| `/web/library` | `LibraryPage` | Yes | Main landing page |
| `/web/library/:id` | `ArticlePage` | Yes | Single article reader |
| `/web/articles` | `ArticlesPage` | Yes | Article list/browse |
| `/web/search` | `SearchPage` | Yes | Full-text and semantic search |
| `/web/submit` | `SubmitPage` | Yes | Submit URL for summarization |
| `/web/collections` | `CollectionsPage` | Yes | Collection tree view |
| `/web/collections/:id` | `CollectionsPage` | Yes | Collection detail (same component) |
| `/web/digest` | `DigestPage` | Yes | Channel digest (requires Telegram WebApp auth) |
| `/web/preferences` | `PreferencesPage` | Yes | User settings |
| `/web/admin` | `AdminPage` | Yes | Gated by `FEATURE_FLAGS.admin`; falls back to `NotFoundPage` when flag is false |
| `/web/login` | `LoginRoute` | No | Auth entry point |
| `*` | `NotFoundPage` | No | Catch-all 404 |

## Component File Paths

- `clients/web/src/features/library/LibraryPage.tsx`
- `clients/web/src/features/article/ArticlePage.tsx`
- `clients/web/src/features/articles/ArticlesPage.tsx`
- `clients/web/src/features/search/SearchPage.tsx`
- `clients/web/src/features/submit/SubmitPage.tsx`
- `clients/web/src/features/collections/CollectionsPage.tsx`
- `clients/web/src/features/digest/DigestPage.tsx`
- `clients/web/src/features/preferences/PreferencesPage.tsx`

## Auth Guard

All routes except `/web/login` and the catch-all are wrapped in `RouteGuard`
(`clients/web/src/auth/RouteGuard.tsx`), which:

1. Shows `InlineLoading` while auth status is `"loading"`
2. Redirects to `/login` (with `from` state) if `canAccessProtectedRoute` returns false
3. Renders children (inside `AppShell`) when authenticated

Guard logic: `clients/web/src/auth/guard.ts` (`canAccessProtectedRoute`)

## Feature Flags

Experimental routes are gated by `FEATURE_FLAGS` from `clients/web/src/routes/features.ts`.
Currently only `admin` is feature-flagged.
