# Test Plan: Collections & Folders API
- Date: 2025-12-08
- Owner: AI Partner
- Related Docs: `.docs/TECH_DESIGNS/TD_collections_folders_api.md`

## Scope & Objectives
- Cover nesting, sharing/ACL, reorder/move, CRUD, and item move/reorder for `/v1/collections` while preserving envelopes/meta and auth constraints.
- Out of scope: UI/Telegram surfaces, email delivery for invites.

## Test Approach
- Unit: validation (depth, cycles, sibling uniqueness), position assignment, ACL role checks, invite token validation.
- Integration: API routes with JWT auth and feature flags, database effects (positions, parent_id, ACL), pagination, envelopes/meta.
- E2E (optional): happy path create → share → invite accept → move/reorder items.

## Environments & Tooling
- Use pytest + FastAPI TestClient; SQLite test DB; feature flags `COLLECTION_SHARING_ENABLED`, `COLLECTION_NESTING_ENABLED`.
- Redis optional; rate limiter can be disabled for tests unless explicitly covered.

## Test Cases
- TC1 CRUD: create/list/get/update/delete collection; sibling name uniqueness per parent; pagination/meta.
- TC2 Nesting: create with parent, depth limit, cycle detection on move, tree endpoint depth cap.
- TC3 Reorder collections: reorder siblings; idempotent payload; invalid cross-parent ids → 400/409.
- TC4 Move collection: move to new parent; positions adjust; prevent moving into descendant (cycle) → 400.
- TC5 Items list/reorder: list items paginated; reorder positions; conflict on duplicate positions → 409; missing items → 404.
- TC6 Move items: move summaries between collections; missing target or permission → 403/404; preserves uniqueness.
- TC7 Sharing ACL list: owner sees ACL summary; viewer denied writes.
- TC8 Share add/remove: owner can add/remove collaborator; cannot remove owner; duplicate add idempotent.
- TC9 Invites: create invite token; accept invite (valid, expired 410, revoked 404); role applied; token single-use.
- TC10 Permissions: viewer read-only; editor can reorder/move/items but not share; owner full control.
- TC11 Rate limiting/meta: responses include envelopes/meta; correlation_id present; 429 when limits hit (flagged test).
- TC12 Error responses: 400 (bad parent/position), 403 (role), 404 (missing), 409 (name/position conflict), 410 (expired invite).

## Regression Coverage
- Existing flat collections remain functional when nesting/sharing flags off; legacy list/get/add/remove still work.
- Summary add/remove still idempotent and timestamps update.

## Non-Functional
- Performance: tree endpoint bounded by depth/limit; pagination respected.
- Resilience: idempotent reorder/move can be retried.

## Entry / Exit Criteria
- Entry: migrations applied; feature flags configured; auth fixture available.
- Exit: All TC1–TC12 pass in CI; no envelope schema regressions; lint/type/format pass.

## Risks & Mitigations
- Race in reorder: test idempotent overwrite and server_version increments.
- Invite abuse: ensure token invalidation and expiration covered.

## Reporting
- Pytest output in CI; track coverage of new routes; log correlation_id for failures.
