# Tech Design: Collections & Folders API (Nesting, Sharing, Reorder)
- Date: 2025-12-08
- Owner: AI Partner
- Status: Draft
- Related Docs: `.docs/TECH_DESIGNS/TD_response_contracts.md`, `.docs/TECH_DESIGNS/TD_openapi-typed-contracts.md`, `.docs/TESTING/TEST_collections_folders.md`, `docs/openapi/mobile_api.yaml`

## Summary
- Extend the existing collections domain to support nested folders, item ordering, sharing/collaboration, and moving summaries between collections while preserving envelopes/meta and authorization. Reuse `/v1/collections` namespace; avoid a new domain.

## Context & Problem
- Current collections are flat, single-owner only, no ordering, no sharing, and only add/remove summary item. Lacking nested organization, collaboration, and move/reorder flows.

## Goals / Non-Goals
- Goals: nesting (parent_id), ordering (position) for collections and items, sharing/ACL with roles, move summaries across collections, tree/list APIs with pagination, idempotent reorder/move, OpenAPI contracts, validation rules, and tests.
- Non-Goals: UI/Telegram changes, full backend implementation of invitations via email/notifications; advanced multi-tenant org features.

## Assumptions & Constraints
- Keep Summary ↔ Collection many-to-many.
- Depth bounded (default max depth 5).
- Position integers are dense per parent; ordering is per sibling set.
- Sharing limited to explicit collaborators (user IDs) and optional invite tokens; no public links.
- Soft deletes preferred for collections; items delete hard is acceptable.

## Requirements Traceability
- Nesting: parent_id, tree/list endpoints.
- Ordering: position on collections (per parent) and items.
- Sharing: ACL entries with roles (owner/editor/viewer), invites.
- Move: summaries between collections, collections under new parent.
- Validation: cycle prevention, ownership/ACL enforcement, rate limits, envelopes.

## Architecture / Flow
- Controllers: extend `app/api/routers/collections.py` with new routes.
- Services: introduce `CollectionService` for auth + business rules (nesting, sharing, move, reorder).
- Storage: extend `Collection` model; add `CollectionCollaborator`, `CollectionInvite`; add `position` to `CollectionItem`.
- Data flow: Request → Auth (JWT) → Rate limiter → Collections router → Service → Peewee models → Response envelope with meta/pagination.

## Data Contracts
- `collections` table: add `parent` FK self-nullable, `position` int (default append), `is_shared` bool (derived), `share_count` int (optional), unique `(user_id, parent_id, name)` to avoid sibling dupes.
- `collection_items` table: add `position` int, unique `(collection_id, position)` optional; keep `(collection, summary)` unique.
- New `collection_collaborators`: id, collection_id FK, user_id FK, role enum {owner, editor, viewer}, status enum {active, revoked, pending}, invited_by, created_at, updated_at, server_version; unique `(collection_id, user_id)`.
- New `collection_invites`: id, collection_id FK, token (uuid), role, expires_at, created_at, used_at, invited_email? (nullable), invited_user_id? (nullable), status.
- Derived fields: `effective_owner_id` = collection.user_id; owner is also collaborator (role=owner).
- Indices: parent/position, parent/name unique, collaborator lookup by user_id, invite token unique.
- Migrations: add columns with defaults, backfill position via created_at order; add tables with indexes.

## Interfaces (API / Contracts)
- All responses use `success/meta` envelopes.
- CRUD (existing paths remain):
  - `GET /v1/collections?parent_id=&limit=&offset=` — list for parent; default root. Pagination required.
  - `GET /v1/collections/tree` — return nested tree up to `max_depth` (server limit) with `children`.
  - `POST /v1/collections` — body: {name, description?, parent_id?, position?}.
  - `GET /v1/collections/{id}` — include parent_id, position, acl summary, item_count, is_shared.
  - `PATCH /v1/collections/{id}` — rename/description, optional parent_id/position (move + reorder).
  - `DELETE /v1/collections/{id}` — soft delete; cascades items; forbids delete if not owner.
- Sharing:
  - `GET /v1/collections/{id}/acl` — list collaborators with roles/status.
  - `POST /v1/collections/{id}/share` — add collaborator {user_id, role}. Owner only.
  - `DELETE /v1/collections/{id}/share/{user_id}` — remove collaborator (owner only; cannot drop owner).
  - `POST /v1/collections/{id}/invite` — create invite token {role, expires_at?}.
  - `POST /v1/collections/invites/{token}/accept` — accept invite; adds collaborator.
- Reorder / Move:
  - `POST /v1/collections/{id}/reorder` — reorder child collections: {items:[{collection_id, position}]}.
  - `POST /v1/collections/{id}/items/reorder` — reorder items in a collection: {items:[{summary_id, position}]}.
  - `POST /v1/collections/{id}/move` — move collection to new parent_id with optional position.
  - `POST /v1/collections/{id}/items/move` — move summaries between collections: {summary_ids, target_collection_id, position?}.
- Retrieval helpers:
  - `GET /v1/collections/{id}/items` — list items with pagination, order by position then created_at.

### Schemas (OpenAPI additions)
- `Collection`: add `parent_id`, `position`, `is_shared`, `item_count`, `children?` (tree response only), `acl_summary?`.
- `CollectionTreeNode`: {collection: Collection, children: [CollectionTreeNode]} or embed children inside Collection when `include_children=true`.
- `CollectionCollaborator`: {user_id, role (owner|editor|viewer), status, invited_by, created_at, updated_at}.
- Requests: `CollectionReorderRequest`, `CollectionItemReorderRequest`, `CollectionMoveRequest`, `CollectionItemMoveRequest`, `CollectionShareRequest`, `CollectionInviteRequest`, `CollectionInviteAcceptRequest`.
- Responses: envelopes for tree, acl list, reorder/move operations return success + updated positions/server_version.

## Flows (key)
- Create: validate parent ownership (or editor rights if shared), depth limit, unique sibling name; assign position (append or requested) and shift others.
- Move collection: prevent cycles (ancestor check), enforce ownership, adjust positions in old/new parent.
- Reorder: idempotent overwrite of sibling positions; validate all belong to same parent.
- Sharing: owner can add/remove; editor/viewer cannot. Accept invite validates token, expiration, role; inserts collaborator.
- Item move: validate visibility and permissions on source and target collections; maintain unique positions.

## Error Handling & Retries
- 400: invalid parent/position, cycle detected, depth exceeded, duplicate name.
- 403: insufficient role.
- 404: collection/item/invite not found.
- 409: conflicting positions or duplicate name on sibling set.
- 410: expired invite token.
- Idempotent reorders/moves; safe to retry.

## Security & Privacy
- Auth via existing JWT; enforce owner/editor permissions per action; viewers read-only.
- Redact tokens in logs; do not expose invite tokens after acceptance.
- No public link sharing; ACL restricted to known user IDs.

## Performance & Scalability
- Pagination for list/items; tree endpoint limited by depth/max children; optional `include_children=false` fallback.
- Indexes on parent, position, user_id for collaborator queries.
- Batch queries for ACL and counts to avoid N+1.

## Operations
- Feature flag `COLLECTION_SHARING_ENABLED` and `COLLECTION_NESTING_ENABLED`.
- Metrics: collection_create, move, reorder, share_add/remove, invite_accept; include correlation_id.
- Logs: include user_id, collection_id, parent_id, depth, counts.

## Testing Strategy
- See `.docs/TESTING/TEST_collections_folders.md`.
- Unit: validation (depth, cycles, sibling name uniqueness), position assignment, ACL checks.
- Integration: CRUD + nesting, move/reorder, sharing add/remove, invite accept, item move/reorder.
- Error paths: 403 (role), 409 (duplicate/position conflict), 410 (expired invite), 400 (cycle/depth).

## Rollout / Migration
- Add columns/tables with defaults; backfill positions.
- Gate sharing/nesting behind flags; start with owner-only + flat as compatibility path.
- Maintain existing endpoints shape; new fields are additive/nullable.

## Risks / Trade-offs
- Complexity of tree retrieval: mitigate with depth limit and pagination for children.
- Position churn under concurrent updates: mitigate with optimistic locking via server_version and idempotent reorder payloads.
- Sharing increases auth surface: mitigate with centralized service checks and tests.

## Alternatives Considered
- Separate “folders” domain: rejected to reduce duplication and reuse collections UX.
- Public link sharing: rejected due to privacy/scope.

## Open Questions
- Should items support multiple positions (ordered per collection) vs single global order? (assumed per collection).
- Need soft-delete for collaborators/invites or hard delete is acceptable? (lean hard delete).
