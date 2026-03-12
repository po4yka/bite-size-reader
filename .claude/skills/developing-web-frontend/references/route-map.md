# Web Frontend Route Map

Synced with `web/src/App.tsx`. Update this file when routes change.

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
| `/web/admin` | `NotFoundPage` | Yes | Gated by `FEATURE_FLAGS.admin` |
| `/web/login` | `LoginRoute` | No | Auth entry point |
| `*` | `NotFoundPage` | No | Catch-all 404 |

## Component File Paths

- `web/src/features/library/LibraryPage.tsx`
- `web/src/features/article/ArticlePage.tsx`
- `web/src/features/articles/ArticlesPage.tsx`
- `web/src/features/search/SearchPage.tsx`
- `web/src/features/submit/SubmitPage.tsx`
- `web/src/features/collections/CollectionsPage.tsx`
- `web/src/features/digest/DigestPage.tsx`
- `web/src/features/preferences/PreferencesPage.tsx`

## Auth Guard

All routes except `/web/login` and the catch-all are wrapped in `RouteGuard`
(`web/src/auth/RouteGuard.tsx`), which:

1. Shows `InlineLoading` while auth status is `"loading"`
2. Redirects to `/login` (with `from` state) if `canAccessProtectedRoute` returns false
3. Renders children (inside `AppShell`) when authenticated

Guard logic: `web/src/auth/guard.ts` (`canAccessProtectedRoute`)

## Feature Flags

Experimental routes are gated by `FEATURE_FLAGS` from `web/src/routes/features.ts`.
Currently only `admin` is feature-flagged.
