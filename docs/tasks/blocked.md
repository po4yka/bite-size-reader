# Blocked — ratatoskr

> Tasks that cannot proceed until an external condition resolves.

- [ ] #task Review Ratatoskr mobile auth, secret-login, and client storage threat model #repo/ratatoskr #area/auth #status/blocked #blocked ⏫ [paperclip:POY-257]
  - Paperclip: POY-257 · assigned to: Security Engineer
  - Blocked by: POY-280, POY-282, POY-283, POY-284
  
  Objective
  Produce a focused security review plan for Ratatoskr mobile auth and client storage before mobile release readiness is claimed.

  Context
  Ratatoskr mobile API uses bearer auth, refresh tokens, Telegram initData, secret-login, secret-key creation/rotation/revocation, account deletion, session listing, and allowlist-aware behavior. ratatoskr-client stores tokens in platform secure storage (Tink AEAD/DataStore on Android, KeychainSettings on iOS) and uses Ktor bearer refresh. The project must not expose secrets, store plaintext secrets, or broaden external access without explicit approval.

  Owner
  Security Engineer. Coordinate with Senior Python Backend Engineer and Senior KMP/Compose Engineer as needed.

  Priority
  High.

  Parent issue or goal linkage
  Goal: Ratatoskr ecosystem mobile contract and release-readiness baseline. Project: ratatoskr. Related issues: POY-253 and POY-255.

  Acceptance criteria
  - Identify security-sensitive auth/session/client-storage flows and source files/docs to review.
  - Define must-have tests or inspection evidence for refresh-token rotation, logout/revocation, secret-login one-time plaintext behavior, Telegram linking, account deletion, and secure storage.
  - Flag any release-blocking ambiguity in fail-open allowlist behavior, external client IDs, or hosted MCP/CLI access.
  - State what requires explicit approval: external access expansion, credentials, telemetry, or production release signoff.

  Expected artifact
  Paperclip security review note with flow inventory, risk classification, required evidence, and follow-up issues if needed.

  Constraints
  Do not run live auth calls or print secrets. Do not edit code. Use current repo docs and code as source of truth.

  Risks
  Mobile auth drift can create token persistence, unauthorized access, stale refresh sessions, or account deletion gaps.

  Verification plan
  Static inspection only; name targeted backend/client tests for follow-up owners.

  Definition of done
  Security has a concrete release-readiness checklist or has filed blocking follow-up issues for unresolved auth/storage risks.
