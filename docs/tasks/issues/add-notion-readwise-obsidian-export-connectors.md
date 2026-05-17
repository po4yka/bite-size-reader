---
title: Add export connectors for Notion, Readwise, and Obsidian
status: backlog
area: api
priority: low
owner: unassigned
blocks: []
blocked_by:
  - emit-summary-events-to-webhook-publisher
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Add export connectors for Notion, Readwise, and Obsidian #repo/ratatoskr #area/api #status/backlog 🔽

## Objective

`rg -n "notion|readwise|obsidian|instapaper"` returns zero hits across `app/`. Inbound *import* parsers exist (`app/domain/services/import_parsers/{pocket,linkwarden,omnivore, netscape,opml}.py`) — but no outbound bridge. The architecture already has `WebhookDelivery` + a clean port pattern; Readwise has a public REST API ideal for a ~200-line adapter. Each connector is small but each has its own vendor SDK / auth flow, so size adds up.

## User story

As a user with an existing knowledge base in Notion / Readwise / Obsidian, I want new summaries pushed to that destination automatically, so that Ratatoskr enriches my existing workflow instead of fragmenting it.

## Context

- Existing inbound parsers: `app/domain/services/import_parsers/{pocket,linkwarden,omnivore,netscape,opml}.py`.
- No outbound connector.
- Generic webhook publisher covered by [[emit-summary-events-to-webhook-publisher]] — must land first.
- Encrypted token storage exists: `app/security/token_crypto.py`.

## Scope

- One adapter per vendor under `app/adapters/export/`: - `notion_export.py` — uses Notion REST API; pushes to a user-chosen database. - `readwise_export.py` — uses Readwise Highlights API; pushes summary + extractive quotes as highlights. - `obsidian_export.py` — writes markdown files to a user-mounted Obsidian vault directory (local-first; documented as opt-in for self-hosted users).
- Each adapter: - Stores its API token Fernet-encrypted (reuse `app/security/token_crypto.py`). - Triggers via the same event bus as [[emit-summary-events-to-webhook-publisher]] (no new fan-out infra). - Has a per-user enable / disable toggle in the `user_export_integrations` table.
- Document each connector setup flow in `docs/guides/configure-export-connectors.md`.

## Acceptance criteria

- [ ] Each connector round-trips a new summary into the destination.
- [ ] Token revocation / re-auth path documented per vendor.
- [ ] Failure path persists into delivery log (reuse `WebhookDelivery` shape or new table — pick one).
- [ ] Feature gated per-user; off by default.

## References

- Existing import parsers: `app/domain/services/import_parsers/`
- Token storage: `app/security/token_crypto.py`
- Depends on: [[emit-summary-events-to-webhook-publisher]]
