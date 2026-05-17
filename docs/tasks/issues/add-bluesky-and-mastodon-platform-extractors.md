---
title: Add Bluesky and Mastodon platform extractors (defer LinkedIn)
status: backlog
area: content
priority: low
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Add Bluesky and Mastodon platform extractors (defer LinkedIn) #repo/ratatoskr #area/content #status/backlog 🔽

## Objective

`app/adapters/` has dedicated `twitter/`, `github/`, `youtube/`,
`academic/`, `meta/`, `video/` extractors. There is no
`bluesky/`, `mastodon/`, `medium/`, or `linkedin/`. Bluesky has a
free AT-Proto API; Mastodon has per-instance REST; both
pattern-match the Twitter adapter shape. Mastodon and Bluesky are
sustained growth platforms; the Twitter adapter already proves
the seam works. **LinkedIn is intentionally deferred** —
auth-walled, aggressive bot detection, ToS risk.

## User story

As a user who follows interesting threads on Bluesky / Mastodon,
I want to paste a single post URL and get a well-structured
summary, so that my reading experience matches what Twitter
already gets.

## Context

- Existing platform extractors:
  `app/adapters/twitter/`, `app/adapters/youtube/`,
  `app/adapters/academic/`.
- Twitter adapter is the closest pattern:
  `app/adapters/twitter/{url_patterns,graphql_parser,
  text_formatter,playwright_client,twitter_extractor}.py`.
- URL routing happens in the URL processor
  (`app/adapters/content/url_processor.py`).

## Scope

- New `app/adapters/bluesky/`:
  - URL pattern matcher for `bsky.app/profile/<handle>/post/<rkey>`.
  - AT-Proto API client
    (`https://public.api.bsky.app/xrpc/...`).
  - Text formatter that follows thread chains.
- New `app/adapters/mastodon/`:
  - URL pattern matcher for `*/users/*/statuses/*` and the
    public-id URL form (host-agnostic since Mastodon is federated).
  - Per-instance REST client (`/api/v1/statuses/<id>`,
    `/api/v1/statuses/<id>/context`).
- Register both in the URL router ahead of the generic chain
  when host matches.
- **Skip LinkedIn** until a clear legal / auth path emerges.
- Test fixtures: a known Bluesky thread URL + a known Mastodon
  thread URL → markdown with original + replies.

## Acceptance criteria

- [ ] A Bluesky post URL summarized end-to-end produces
  visibly-better content than the generic chain.
- [ ] Same for a Mastodon post URL across at least 2 instances
  (mastodon.social + one other).
- [ ] LinkedIn URLs pass through to the generic chain unchanged
  (no crash, no special handling).

## References

- Twitter template:
  `app/adapters/twitter/`
- URL routing:
  `app/adapters/content/url_processor.py`
- Related: [[add-reddit-and-hackernews-scraper-providers]]
