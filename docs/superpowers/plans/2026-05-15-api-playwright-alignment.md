# API Playwright Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align `Dockerfile.api` browser installation with `Dockerfile` so Playwright/Chromium works under the non-root `appuser` in API containers.

**Architecture:** The bot `Dockerfile` already solves this correctly: it sets `PLAYWRIGHT_BROWSERS_PATH=/ms-playwright`, installs both `playwright` and `patchright` Chromium into that world-readable path as root, then `chmod -R a+rX` it before switching to `appuser`. `Dockerfile.api` does none of this — the browser installs into `/root/.cache/ms-playwright` and `appuser` cannot find it. The fix copies the exact block from the bot Dockerfile into the API Dockerfile. A CI smoke test then builds the API image and runs the path check as UID 1000.

**Tech Stack:** Docker (multi-stage build), Playwright, patchright, GitHub Actions.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `ops/docker/Dockerfile.api` | Modify browser install block | Add `PLAYWRIGHT_BROWSERS_PATH`, `mkdir`, `patchright`, `chmod` |
| `.github/workflows/ci.yml` | Add new job `docker-api-browser-smoke` | Build API image and verify Chromium resolves as appuser |

---

## Task 1: Fix Dockerfile.api browser installation

**Files:**
- Modify: `ops/docker/Dockerfile.api:54-58`

### What is wrong now

Lines 54–58 of `Dockerfile.api` currently read:

```dockerfile
# Install Chromium for Playwright-based scraping fallback.
# Set WITH_PLAYWRIGHT=0 at build time to produce a slimmer image without
# the browser engine (e.g. when SCRAPER_PLAYWRIGHT_ENABLED=false).
ARG WITH_PLAYWRIGHT=1
RUN if [ "${WITH_PLAYWRIGHT}" = "1" ]; then playwright install --with-deps chromium; fi
```

Problems:
1. No `ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright` — browser lands in `/root/.cache/ms-playwright`, invisible to `appuser`.
2. No `mkdir -p /ms-playwright` before install.
3. No `patchright install chromium` — Scrapling's stealth browser path goes unresolved.
4. No `chmod -R a+rX /ms-playwright` — `appuser` cannot execute the browser even if the path were correct.
5. Single-line `RUN` gives no diagnostic output on failure (`set -eux` is missing).

- [ ] **Step 1: Read Dockerfile.api to confirm the exact current text**

```bash
grep -n "PLAYWRIGHT\|playwright\|patchright\|ms-playwright" ops/docker/Dockerfile.api
```

Expected output includes only lines 54–58 with `playwright install --with-deps chromium` and no `PLAYWRIGHT_BROWSERS_PATH`.

- [ ] **Step 2: Replace the browser installation block**

In `ops/docker/Dockerfile.api`, replace lines 54–58 (the comment block + `ARG WITH_PLAYWRIGHT` + `RUN if ...`) with the following. The replacement goes in the exact same position (before `COPY app ./app`, before `useradd`, before `USER appuser`).

```dockerfile
# Install Chromium for Playwright-based scraping fallback.
# Browsers are placed in /ms-playwright (shared, world-readable) so that the
# non-root `appuser` at runtime can find them — without PLAYWRIGHT_BROWSERS_PATH
# the install lands in /root/.cache/ms-playwright and appuser fails with
# "Executable doesn't exist at /home/appuser/.cache/ms-playwright/...".
# patchright is Scrapling's stealth Playwright backend; it honours the same
# env var and ships its own patched Chromium build.
# Set WITH_PLAYWRIGHT=0 at build time to produce a slimmer image without
# the browser engine (e.g. when SCRAPER_PLAYWRIGHT_ENABLED=false).
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ARG WITH_PLAYWRIGHT=1
RUN set -eux; \
    if [ "${WITH_PLAYWRIGHT}" = "1" ]; then \
        mkdir -p /ms-playwright; \
        playwright install --with-deps chromium; \
        patchright install chromium; \
        chmod -R a+rX /ms-playwright; \
    fi
```

- [ ] **Step 3: Verify the ENV line appears before the USER line**

```bash
grep -n "PLAYWRIGHT_BROWSERS_PATH\|USER appuser\|useradd" ops/docker/Dockerfile.api
```

Expected: `PLAYWRIGHT_BROWSERS_PATH` line number is **lower** than `useradd` and `USER appuser` line numbers — the env var must be set while still running as root.

- [ ] **Step 4: Verify the full file looks correct**

```bash
grep -n "PLAYWRIGHT\|playwright\|patchright\|ms-playwright\|WITH_PLAYWRIGHT" ops/docker/Dockerfile.api
```

Expected output (approximate line numbers):
```
54:# Install Chromium for Playwright-based scraping fallback.
63:ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
64:ARG WITH_PLAYWRIGHT=1
65:RUN set -eux; \
67:        mkdir -p /ms-playwright; \
68:        playwright install --with-deps chromium; \
69:        patchright install chromium; \
70:        chmod -R a+rX /ms-playwright; \
```

No `PLAYWRIGHT` references should appear after `USER appuser`.

- [ ] **Step 5: Commit**

```bash
git add ops/docker/Dockerfile.api
git commit -m "fix(docker): align API Dockerfile browser install with bot (PLAYWRIGHT_BROWSERS_PATH, patchright, chmod)"
```

---

## Task 2: Add CI smoke test for API image browser execution as appuser

**Files:**
- Modify: `.github/workflows/ci.yml`

The existing `docker-build` CI job builds only `Dockerfile` (the bot image) using `docker/build-push-action` with `load: false` (image is cached but not loaded locally). We need a separate job that builds `Dockerfile.api` with a regular `docker build` command (so the image is available locally), then runs a Chromium path check as UID 1000 (the `appuser` UID).

- [ ] **Step 1: Read the current `docker-build` job in `.github/workflows/ci.yml`**

```bash
grep -n "docker-build\|docker-api\|Dockerfile.api" .github/workflows/ci.yml | head -20
```

Expected: `docker-build` job exists, no `docker-api-browser-smoke` job.

- [ ] **Step 2: Add the new `docker-api-browser-smoke` job**

Find the `compose-config-check:` job in `.github/workflows/ci.yml` (it appears after `docker-build`). Insert the following new job **between** `docker-build:` and `compose-config-check:`:

```yaml
  docker-api-browser-smoke:
    name: Docker API - Playwright browser smoke test
    needs: prepare-environment
    runs-on: ubuntu-latest
    timeout-minutes: 25
    permissions:
      contents: read
    steps:
      - name: Checkout
        uses: actions/checkout@v6

      - name: Detect Docker-relevant changes
        id: filter
        uses: dorny/paths-filter@v4
        with:
          filters: |
            docker:
              - 'ops/docker/Dockerfile.api'
              - 'app/**'
              - 'pyproject.toml'
              - 'uv.lock'

      - name: Build API image
        if: github.event_name == 'pull_request' || steps.filter.outputs.docker == 'true'
        run: |
          docker build \
            -f ops/docker/Dockerfile.api \
            -t ratatoskr-api:smoke \
            --build-arg WITH_PLAYWRIGHT=1 \
            .

      - name: Verify Chromium resolves as appuser (UID 1000)
        if: github.event_name == 'pull_request' || steps.filter.outputs.docker == 'true'
        run: |
          docker run --rm \
            --user 1000 \
            ratatoskr-api:smoke \
            python -c "
import os, sys
browsers_path = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '')
print(f'PLAYWRIGHT_BROWSERS_PATH={browsers_path}')
assert browsers_path == '/ms-playwright', f'Wrong path: {browsers_path!r}'

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    exe = p.chromium.executable_path
    print(f'Chromium executable: {exe}')
    assert exe.startswith('/ms-playwright'), f'Executable not under /ms-playwright: {exe!r}'
    assert os.path.isfile(exe), f'Executable does not exist: {exe!r}'
    assert os.access(exe, os.X_OK), f'Executable not executable by current user: {exe!r}'

print('Browser smoke test passed.')
"
```

- [ ] **Step 3: Verify the CI YAML is syntactically valid**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))" && echo "YAML valid"
```

Expected: `YAML valid`

- [ ] **Step 4: Verify the new job name appears in the file**

```bash
grep -n "docker-api-browser-smoke\|Playwright browser smoke" .github/workflows/ci.yml
```

Expected: two matching lines (the job key and the `name:` value).

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add API Playwright browser smoke test (runs as appuser UID 1000)"
```

---

## Self-Review

**Spec coverage:**

| Requirement | Task |
|---|---|
| Set `PLAYWRIGHT_BROWSERS_PATH` to `/ms-playwright` in API Dockerfile | Task 1 |
| Install browsers into shared path before switching to appuser | Task 1 (install runs as root before `useradd`/`USER appuser`) |
| `chmod`/`chown` browser directory so appuser can execute | Task 1 (`chmod -R a+rX /ms-playwright`) |
| Install patchright browser in API image | Task 1 (`patchright install chromium`) |
| Add Docker smoke test that runs as appuser and verifies Chromium executable resolution | Task 2 |
| Keep `WITH_PLAYWRIGHT=0` build arg supported | Task 1 (conditional `if [ "${WITH_PLAYWRIGHT}" = "1" ]`) |
| Bot and API browser setup are consistent | Task 1 (exact same block as bot Dockerfile) |

**Placeholder scan:** No TBD/TODO/placeholders. All code is complete and exact.

**Consistency:** The `ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright` line is set in the runtime stage, before the RUN block that creates `/ms-playwright` — consistent with how it works in the bot Dockerfile. The `USER appuser` line comes after, so the install runs as root with the correct env var set.

**Note on `chown` vs `chmod`:** The bot Dockerfile uses `chmod -R a+rX` (not `chown`). This grants read+execute to all users without changing ownership from root. `appuser` can read and execute the browser binary. Ownership staying as root is intentional — it prevents the non-root user from modifying the browser installation. This matches the existing bot Dockerfile pattern exactly.
