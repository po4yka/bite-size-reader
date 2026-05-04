# How to Configure Twitter / X Extraction

Enable Twitter / X content extraction in Ratatoskr — tweets, threads,
and X Articles.

**Audience:** Users, Operators.
**Difficulty:** Beginner for Tier 1 (Firecrawl); Intermediate for Tier 2
(authenticated Playwright).
**Estimated Time:** 5 minutes (Tier 1), 15 minutes (Tier 2).

---

## What Twitter / X content is supported

| Content type | URL pattern | Tier 1 (Firecrawl) | Tier 2 (Playwright) |
| --- | --- | --- | --- |
| Single tweet | `https://twitter.com/<user>/status/<id>` or `https://x.com/...` | ✓ when public | ✓ (uses your cookies) |
| Thread | `https://twitter.com/<user>/status/<id>` (root) | partial | ✓ |
| X Article | `https://x.com/<user>/status/<id>` redirected from an article URL | partial | ✓ |
| Profile / search / hashtag | various | ✗ | ✗ |

For tweets and threads the extractor intercepts the GraphQL API
response; for X Articles it falls back to DOM scraping. URL detection
and routing live in
[`app/adapters/twitter/url_patterns.py`](../../app/adapters/twitter/url_patterns.py).

---

## Two-tier strategy

Ratatoskr never authenticates against Twitter unless you opt in. The
default is Tier 1 only; Tier 2 is gated behind explicit env-var consent.

```
Twitter URL
  └─ Tier 1: Firecrawl /scrape   ← default, free, no Twitter login
        success → return
        failure ↓
  └─ Tier 2: Playwright + cookies.txt   ← opt-in via TWITTER_PLAYWRIGHT_ENABLED=true
        success → return
        failure → mark request failed
```

`TWITTER_PREFER_FIRECRAWL=true` (default) keeps Firecrawl ahead of
Playwright when both are enabled. `TWITTER_FORCE_TIER` lets you pin a
specific tier (`auto` | `firecrawl` | `playwright`) for debugging or
when you know one tier always works for a given account.

---

## Tier 1 — Firecrawl (default, no setup)

If you already have a working Firecrawl deployment (cloud or
self-hosted), Tier 1 is on out of the box.

```bash
# .env
TWITTER_ENABLED=true              # default
TWITTER_PREFER_FIRECRAWL=true     # default
TWITTER_PLAYWRIGHT_ENABLED=false  # default — Tier 2 stays off
```

Send a tweet URL to the bot to verify:

```
https://x.com/elonmusk/status/1234567890123456789
```

Expected: bot replies with a structured summary of the tweet text and
any embedded article. If Firecrawl returns a paywall page or a Twitter
login wall, summarisation will return a low-confidence result; that's
your cue to enable Tier 2.

---

## Tier 2 — Playwright (opt-in, authenticated)

Use this when public Firecrawl scraping cannot get past Twitter's login
wall — typically for protected accounts, age-gated content, replies in
deep threads, or X Articles that redirect through `t.co`.

### 1. Install Chromium

The browser ships with the optional `browser_scraper` extra:

```bash
uv sync --extra browser_scraper
playwright install chromium
```

Inside the Docker image Chromium is already present; no extra step is
needed unless you rebuild without `--no-cache` after a Playwright
package bump (in which case run `playwright install chromium` inside
the container — same as the URL-pipeline note in
[`CLAUDE.md`](../../CLAUDE.md)).

### 2. Export your Twitter / X cookies

Use a Netscape-format `cookies.txt` exporter (e.g. the `cookies.txt`
extension for Firefox / Chrome). Export from a browser session that's
already logged in to twitter.com or x.com.

```bash
# Place the file where Ratatoskr expects it
cp ~/Downloads/cookies.txt /data/twitter_cookies.txt
chmod 600 /data/twitter_cookies.txt
```

Default path: `/data/twitter_cookies.txt`. Override with
`TWITTER_COOKIES_PATH=/some/other/path`.

> **Security:** the cookies file grants full session access to your
> Twitter account. Mount it read-only into the container, never check
> it into git, and rotate by re-exporting whenever you change your
> Twitter password.

### 3. Turn Tier 2 on

```bash
# .env
TWITTER_PLAYWRIGHT_ENABLED=true
TWITTER_COOKIES_PATH=/data/twitter_cookies.txt
TWITTER_HEADLESS=true              # default; set false to see the browser
TWITTER_PAGE_TIMEOUT_MS=15000      # default
TWITTER_MAX_CONCURRENT_BROWSERS=2  # default; raise carefully — each is ~150 MB RAM
```

Restart the bot. Send a tweet URL the way you'd send any other URL — no
new command required. Tier 2 fires automatically when Tier 1 fails (or
immediately if you set `TWITTER_FORCE_TIER=playwright`).

---

## Redirect-aware article resolver

X Article links often arrive as `t.co` shortlinks or as wrapped
redirects from third-party share buttons. Ratatoskr's resolver
unwraps these before extraction so the canonical X Article URL is
what hits the scraper. The resolver returns a structured `reason`
code on every input:

| reason | meaning | action |
| --- | --- | --- |
| `path_match` | The URL is already a canonical X Article path; no resolution needed. | Proceed to extraction. |
| `redirect_match` | The URL was a shortlink / wrapper that redirected to a canonical X Article. | Extract using the redirect target. |
| `canonical_match` | The page's `<link rel="canonical">` pointed at an X Article. | Extract using the canonical URL. |
| `not_article` | The URL resolves to something that is not an X Article (a tweet, profile, error page). | Fall through to the regular tweet/thread extractor. |
| `resolve_failed` | Network or HTTP error before we could decide. | Log and surface as a soft failure; no extraction attempt. |

Configuration:

```bash
TWITTER_ARTICLE_REDIRECT_RESOLUTION_ENABLED=true   # default
TWITTER_ARTICLE_RESOLUTION_TIMEOUT_SEC=5           # default; soft cap
```

Disable only if your Firecrawl deployment cannot reach the public
internet for a redirect-resolution probe.

---

## Optional live smoke test

A standalone script tests the full Twitter / X pipeline against a
fixed list of public URLs. It is gated behind an explicit opt-in so
CI doesn't accidentally hit Twitter on every run.

```bash
TWITTER_ARTICLE_LIVE_SMOKE_ENABLED=true \
  python tools/scripts/twitter_article_live_smoke.py
```

Reports per-link JSON diagnostics including the resolver `reason`,
the tier that succeeded, and timing. Useful when you suspect Twitter
has changed an extractor invariant.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Bot replies but the summary is "Sign in to view this content" | Firecrawl hit a login wall and Tier 2 is off. | Set `TWITTER_PLAYWRIGHT_ENABLED=true` and add cookies. |
| `TWITTER_FORCE_TIER=playwright requires TWITTER_PLAYWRIGHT_ENABLED=true` startup error | You pinned Tier 2 but didn't enable it. | Either set `TWITTER_PLAYWRIGHT_ENABLED=true` or change the force tier. |
| Playwright reports HTTP 401 / 403 | Cookies expired or wrong account. | Re-export cookies; verify the file is mounted into the container. |
| Captcha shown on first run after cookies refresh | Twitter's anti-bot triggered. | Run with `TWITTER_HEADLESS=false` once, solve manually, save cookies again. |
| 429 rate limits | Concurrency too high. | Drop `TWITTER_MAX_CONCURRENT_BROWSERS` to 1 and lower request volume. |
| Extraction succeeds but only the first tweet of a thread comes back | Thread continuation requires authenticated requests. | Ensure Tier 2 cookies belong to an account that can see the thread. |
| `not_article` for every X Article URL | Redirect resolver could not reach the network. | Either enable network egress for the resolver or disable it with `TWITTER_ARTICLE_REDIRECT_RESOLUTION_ENABLED=false`. |

For deeper logs, set `LOG_LEVEL=DEBUG` and grep for the request's
correlation ID — every Twitter extraction stamps one.

---

## Related

- [Architecture Overview § Subsystem index](../explanation/architecture-overview.md#subsystem-index)
- [Configure YouTube Download](configure-youtube-download.md)
- [Enable Web Search](enable-web-search.md)
- [`app/adapters/twitter/`](../../app/adapters/twitter/) — extraction
  source code (`extraction_coordinator.py` is the entry point).
- [`app/config/twitter.py`](../../app/config/twitter.py) — full config
  schema with validation rules.
