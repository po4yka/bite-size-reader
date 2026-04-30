# Visual Regression Testing

Reference for the two visual-regression layers added in Phase 9.

**Audience:** Frontend developers, CI maintainers
**Type:** Reference
**Related:** [Web Frontend Guide](frontend-web.md)

---

## Overview

Two complementary visual-regression systems protect the Frost design system from
unintended regressions:

| Layer | Tool | Scope | Trigger |
|---|---|---|---|
| Component | Chromatic | Individual Storybook stories | Push + same-repo PRs |
| Route | Playwright | Full-page screenshots per route | Every CI run |

---

## Chromatic — Component-level visual diff

Chromatic connects to Storybook and detects pixel-level changes in individual
components. Each push publishes the Storybook build to chromatic.com; reviewers
accept or reject visual changes in the Chromatic UI before merging.

### Initial setup

1. Sign in at [chromatic.com](https://www.chromatic.com) with your GitHub account.
2. Click **Add project** and select the `ratatoskr` repository.
3. Copy the project token shown after the project is created.
4. In the GitHub repository, go to **Settings → Secrets and variables → Actions**.
5. Add a new repository secret named `CHROMATIC_PROJECT_TOKEN` with the copied value.

The `web-chromatic` CI job will start working on the next push once the secret
is configured. Until then, the job runs with `continue-on-error: true` so it
does not block PRs.

### Running locally

```bash
cd clients/web
CHROMATIC_PROJECT_TOKEN=<your-token> npm run chromatic
```

The `chromatic` script uses `--exit-zero-on-changes` (soft-fail) and
`--build-script-name=build-storybook`. Drop `--exit-zero-on-changes` in the
script if you want strict failure on any visual diff.

### Interpreting results

- Chromatic posts a link to the build in the GitHub PR checks panel.
- Each changed story shows a before/after diff. Click **Accept** to approve the
  change as the new baseline, or **Deny** to flag it as a regression.
- Baselines are stored in Chromatic (not in the repo).

---

## Playwright — Route-level screenshot diff

`clients/web/src/tests/e2e/mobile-routes.spec.ts` captures full-page screenshots
for 16 routes across 4 device profiles (desktop 1440px, iPhone 12, Pixel 5,
iPad Mini). Subsequent CI runs diff against the committed baselines.

### Baseline workflow

Snapshots are committed to the repository alongside the spec. When you add or
significantly alter a route's layout, regenerate baselines locally:

```bash
cd clients/web
# Start the dev server (used by playwright.config.ts webServer block)
# then update snapshots:
npm run test:e2e -- mobile-routes --update-snapshots
```

Commit the generated `src/tests/e2e/*.spec.ts-snapshots/` directories:

```bash
git add clients/web/src/tests/e2e/
git commit -m "test(web): update Playwright visual baselines for <change>"
```

Do **not** run `--update-snapshots` in CI automatically — that defeats the
purpose of the check.

### Running locally

```bash
cd clients/web
# Run only the mobile-routes spec:
npm run test:e2e -- mobile-routes

# Run with a specific project (device):
npm run test:e2e -- mobile-routes --project="iPhone 12"

# Update baselines after an intentional UI change:
npm run test:e2e -- mobile-routes --update-snapshots
```

### CI job behavior

The `web-playwright-visual` job:

1. Installs Chromium and WebKit with system deps via
   `npx playwright install --with-deps chromium webkit`.
2. Builds the frontend (`npm run build`), which the `webServer` block in
   `playwright.config.ts` serves on port 4173.
3. Runs `mobile-routes.spec.ts` across all 4 device projects.
4. Uploads the HTML report as artifact `playwright-report-<run-id>` (always,
   14-day retention).
5. On failure, uploads screenshot diffs as `playwright-screenshot-diffs-<run-id>`
   (14-day retention).

### First-run note

If baseline PNGs are not yet committed, the first CI run will fail with
"missing baseline" errors. Generate and commit them locally (see above), then
push again.

### Interpreting failures

- Download the `playwright-screenshot-diffs-<run-id>` artifact from the GitHub
  Actions run.
- The `test-results/` directory contains `actual.png`, `expected.png`, and
  `diff.png` for each failing assertion.
- If the diff is intentional (a planned design change), run
  `--update-snapshots` locally and commit the new baselines.
- If the diff is unintentional, investigate and revert the offending change.

---

## Device projects

| Project name | Device / viewport |
|---|---|
| `desktop` | 1440×900 |
| `iPhone 12` | 390×844, Safari UA, `@media (hover: none)` |
| `Pixel 5` | 393×851, Chrome Android UA |
| `iPad Mini` | 768×1024, Safari UA |

---

**Last Updated:** 2026-04-30
