---
title: Add public share-by-link for collections (read-only, token-gated)
status: backlog
area: api
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Add public share-by-link for collections (read-only, token-gated) #repo/ratatoskr #area/api #status/backlog 🔼

## Objective

`app/api/routers/collections.py` exposes only collaborator-style
sharing — both `/{id}/share` and `/{id}/invite` require an
authenticated target `user_id`
(`CollectionService.add_collaborator` at line 341). The README
pitches Ratatoskr as a "searchable archive", but there is no
surface for sharing a curated subset with someone outside
`ALLOWED_USER_IDS`.

## User story

As a collection owner, I want to generate a read-only public link
to a curated collection, so that I can share my reading list with
someone who doesn't have a Ratatoskr account.

## Context

- Existing share methods:
  `app/api/routers/collections.py:341, 362-391`.
- Grep for `public_share`, `share_token`, `public.*link` against
  `app/db/models/collections.py` and `app/api/routers/collections.py`
  returns zero.

## Scope

- New `POST /v1/collections/{id}/public-link` (owner-only) →
  returns a token; allows `expires_at`, optional password.
- New `DELETE /v1/collections/{id}/public-link/{token}` to
  revoke.
- New `GET /v1/public/collections/{token}` returns a read-only
  payload (collection title, item titles + summaries, owner
  display name) without auth.
- Schema additions: `collection_public_links` table (token,
  collection_id, created_at, expires_at, revoked_at,
  password_hash, view_count).
- Audit-log entry on every public-link read (rate-limited).
- Expired or revoked tokens 404 with the standard envelope.
- Document in OpenAPI spec and reference doc.

## Acceptance criteria

- [ ] Public link returns 200 with collection contents when valid.
- [ ] Returns 404 when revoked, expired, or unknown.
- [ ] Owner can list and revoke active links.
- [ ] View count incremented per fetch, rate-limited per IP.

## References

- Existing share endpoints:
  `app/api/routers/collections.py:341, 362-391`
- Models: `app/db/models/collections.py`
- Related: [[add-collection-incoming-invites-and-shared-with-me-listing]]
