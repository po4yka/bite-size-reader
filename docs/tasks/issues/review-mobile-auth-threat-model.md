---
title: Review Ratatoskr mobile auth, secret-login, and client storage threat model
status: blocked
area: auth
priority: high
owner: Security Engineer
blocks: []
blocked_by: [decide-auth-security-second-wave-scope]
created: 2026-04-30
updated: 2026-05-17
---

- [ ] #task Review Ratatoskr mobile auth, secret-login, and client storage threat model #repo/ratatoskr #area/auth #status/blocked #blocked ⏫

    - blocked_reason: Per the original spec, this review is gated by the CTO decisions in [[decide-auth-security-second-wave-scope]]. The per-flow risk classification, release-blocker calls, and approval signoff cannot be completed until those policy decisions are recorded.

## Status

A structured security-review frame is checked in at
`docs/security/2026-05-17-mobile-auth-storage-review.md`. It
pre-populates the mechanical flow inventory (file pointers, surface
list, AuditLog write paths) from the codebase as of HEAD. The
**per-flow risk classification table**, the **release-blocker
calls**, and the **must-have-test list** are marked
`_AWAITING SECURITY ENGINEER_` — they require Security Engineer
judgement and are blocked on the CTO decision memo.

## Objective

Produce a focused security review plan for Ratatoskr mobile auth and client storage before mobile release readiness is claimed.

## Context

Ratatoskr mobile API uses bearer auth, refresh tokens, Telegram initData, secret-login, secret-key creation/rotation/revocation, account deletion, session listing, and allowlist-aware behavior. ratatoskr-client stores tokens in platform secure storage (Tink AEAD/DataStore on Android, KeychainSettings on iOS) and uses Ktor bearer refresh. The project must not expose secrets, store plaintext secrets, or broaden external access without explicit approval.

## Acceptance criteria

- [ ] Identify security-sensitive auth/session/client-storage flows and source files/docs to review.
- [ ] Define must-have tests or inspection evidence for refresh-token rotation, logout/revocation, secret-login one-time plaintext behavior, Telegram linking, account deletion, and secure storage.
- [ ] Flag any release-blocking ambiguity in fail-open allowlist behavior, external client IDs, or hosted MCP/CLI access.
- [ ] State what requires explicit approval: external access expansion, credentials, telemetry, or production release signoff.

## Expected artifact

Paperclip security review note with flow inventory, risk classification, required evidence, and follow-up issues if needed.

## Constraints

Do not run live auth calls or print secrets. Do not edit code. Use current repo docs and code as source of truth.

## Risks

Mobile auth drift can create token persistence, unauthorized access, stale refresh sessions, or account deletion gaps.

## Definition of done

Security has a concrete release-readiness checklist or has filed blocking follow-up issues for unresolved auth/storage risks.

## References

- `docs/security/2026-05-17-mobile-auth-storage-review.md` (frame; awaiting Security Engineer judgements + CTO decisions)
- `docs/decisions/2026-05-17-auth-security-second-wave.md` (CTO decisions blocking this review)
