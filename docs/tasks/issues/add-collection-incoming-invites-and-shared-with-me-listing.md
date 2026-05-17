---
title: Add collection "incoming invites" and "shared with me" listing endpoints
status: backlog
area: api
priority: high
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Add collection "incoming invites" and "shared with me" listing endpoints #repo/ratatoskr #area/api #status/backlog ⏫

## Objective

Collection invites and collaboration models exist
(`CollectionCollaborator`, `CollectionInvite`) and a recipient can
accept an invite via `POST /invites/{token}/accept`, but there is
no listing endpoint — a recipient has no way to **discover** their
own pending invites without the invite-token URL being passed out
of band, and no way to **list collections shared with them** vs
collections they own.

## User story

As an invited collaborator, I want to see collections that have
been shared with me and accept pending invites from the app, so
that I can use a feature my friend already configured for me.

## Context

- Existing routes: `app/api/routers/collections.py:362-391` —
  `POST /{id}/invite` and `POST /invites/{token}/accept`.
- Missing: `GET /v1/collections/invites/incoming` (pending invites
  for caller) and a `?membership=shared` filter on
  `GET /v1/collections`.
- Grep for `shared_with_me`, `incoming_invite`, `list_invites`,
  `pending_invites` across the codebase returns zero results.

## Scope

- New `GET /v1/collections/invites/incoming` — returns pending
  invites for the caller (paginated, standard envelope).
- Extend `GET /v1/collections` with a `?membership=shared|owned|any`
  filter (default `any` for backwards compatibility).
- Update the OpenAPI spec and `docs/reference/mobile-api.md`.
- Frontend `/web/collections` exposes an "Invitations" section
  (covered by `ratatoskr-web` once spec lands).

## Acceptance criteria

- [ ] `GET /v1/collections/invites/incoming` returns rows where
  `invite.recipient_user_id = current_user` AND status pending.
- [ ] `GET /v1/collections?membership=shared` returns only
  collections where caller is a collaborator (not owner).
- [ ] OpenAPI spec + reference doc updated.
- [ ] Integration test covers each filter value.

## References

- Existing routes: `app/api/routers/collections.py:362-391`
- Models: `app/db/models/collections.py` (`CollectionCollaborator`,
  `CollectionInvite`)
- Related: [[add-public-share-by-link-for-collections]]
