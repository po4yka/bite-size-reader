# Visual Regression Testing

Reference for the Playwright-based local visual-regression solution.

**Audience:** Frontend developers, CI maintainers
**Type:** Reference
**Related:** [Web Frontend Guide](frontend-web.md)

---

## Overview

Two complementary Playwright specs protect the Frost design system from
unintended regressions. Both run locally and in CI — no third-party service
required, all baselines committed to the repo.

| Layer | Spec | Scope | Devices |
|---|---|---|---|
| Route | `mobile-routes.spec.ts` | Full-page screenshots per route | desktop, iPhone 12, Pixel 5, iPad Mini |
| Component | `storybook-visual.spec.ts` | One screenshot per Storybook story | Single viewport (1024×768) |

---

## Running locally

### Route-level (mobile-routes.spec.ts)

```bash
cd clients/web
# Run against all 4 device projects:
npm run test:e2e -- mobile-routes

# Run against a specific device:
npm run test:e2e -- mobile-routes --project="iPhone 12"

# Update baselines after an intentional UI change:
npm run test:e2e -- mobile-routes --update-snapshots
```

### Component-level (storybook-visual.spec.ts)

```bash
cd clients/web
# Build Storybook first (required — spec reads storybook-static/index.json):
npm run build-storybook

# Run only the storybook project:
npm run test:e2e -- storybook-visual --project=storybook

# Update baselines:
npm run test:e2e -- storybook-visual --project=storybook --update-snapshots
```

### Both specs together (convenience scripts)

```bash
cd clients/web
# Run both specs (builds Storybook first):
npm run test:visual

# Update all baselines (builds Storybook first):
npm run test:visual:update
```

---

## Baseline workflow

All baseline PNGs are committed to the repository alongside their specs:

- `clients/web/src/tests/e2e/mobile-routes.spec.ts-snapshots/`
- `clients/web/src/tests/e2e/storybook-visual.spec.ts-snapshots/`

When you make an intentional UI change that alters screenshots:

1. Run the relevant `--update-snapshots` command locally.
2. Review the changed PNGs in your working tree (`git diff --stat`).
3. Commit the new baselines together with the code change:

```bash
git add clients/web/src/tests/e2e/
git commit -m "test(web): update Playwright visual baselines for <change>"
```

Do **not** run `--update-snapshots` in CI automatically — that defeats the
purpose of the check.

---

## Where baselines live

```text
clients/web/src/tests/e2e/
  mobile-routes.spec.ts-snapshots/
    mobile-library-chromium-darwin.png        # desktop
    mobile-library-iPhone-12-darwin.png       # iPhone 12
    mobile-library-Pixel-5-darwin.png         # Pixel 5
    mobile-library-iPad-Mini-darwin.png       # iPad Mini
    ...  (16 routes × 4 devices = ~64 PNGs)
  storybook-visual.spec.ts-snapshots/
    <story-id>.png                            # one per story (~50 PNGs)
```

---

## CI behavior

The `web-playwright-visual` job:

1. Installs Chromium and WebKit with system deps via
   `npx playwright install --with-deps chromium webkit`.
2. Builds the frontend (`npm run build`) for the Vite preview server.
3. Builds Storybook (`npm run build-storybook`) producing `storybook-static/`.
4. Runs `npx playwright test`, which:
   - Projects `desktop`, `iPhone 12`, `Pixel 5`, `iPad Mini` run
     `mobile-routes.spec.ts` against the Vite preview server (port 4173).
   - Project `storybook` runs `storybook-visual.spec.ts` against
     `http-server` serving `storybook-static/` on port 6006.
5. Uploads the HTML report as artifact `playwright-report-<run-id>` (always,
   14-day retention).
6. On failure, uploads screenshot diffs as `playwright-screenshot-diffs-<run-id>`
   (14-day retention).

---

## Interpreting failures

- Download the `playwright-screenshot-diffs-<run-id>` artifact from the GitHub
  Actions run.
- The `test-results/` directory contains `actual.png`, `expected.png`, and
  `diff.png` for each failing assertion.
- If the diff is intentional (a planned design change), run
  `--update-snapshots` locally and commit the new baselines.
- If the diff is unintentional, investigate and revert the offending change.

---

## Device projects

| Project name | Device / viewport | Runs |
|---|---|---|
| `desktop` | 1440×900 | `mobile-routes.spec.ts` |
| `iPhone 12` | 390×844, Safari UA, `@media (hover: none)` | `mobile-routes.spec.ts` |
| `Pixel 5` | 393×851, Chrome Android UA | `mobile-routes.spec.ts` |
| `iPad Mini` | 768×1024, Safari UA | `mobile-routes.spec.ts` |
| `storybook` | 1024×768 | `storybook-visual.spec.ts` |

---

**Last Updated:** 2026-04-30
