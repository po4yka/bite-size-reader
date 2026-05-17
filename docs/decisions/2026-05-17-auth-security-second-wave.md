# Decision memo: Ratatoskr auth/security second-wave scope

| field | value |
| --- | --- |
| date | 2026-05-17 |
| owner | CTO |
| status | **DRAFT — awaiting CTO sign-off on each numbered decision** |
| references | [[review-mobile-auth-threat-model]], [[decide-auth-security-second-wave-scope]] |

This memo is a structured frame for the CTO to record decisions on the five second-wave policy questions surfaced by the Security / AppSec review. **It does not record decisions made on behalf of the CTO.** Each numbered section ends with an explicit `DECISION:` placeholder plus the classification choices the task spec requires (implementation follow-up / security review follow-up / product–UX follow-up / approval needed / no-action with rationale).

---

## 1. TLS pinning policy

Question: should the KMP and web clients pin the production TLS certificate (chain or leaf), and if so under which rotation policy?

Evidence to weigh:

- Pinning reduces MITM risk on user-controlled devices but introduces a brick-the-app failure mode if a cert rotates outside the pinned window. Mobile clients especially can become unusable if the pin outlives the cert.
- The current `ratatoskr-client` storage uses platform secure storage; pinning would add a parallel trust anchor.
- Operational cost: a documented rotation runbook, ideally with multi-pin transition windows.

Implementation surface (if approved):

- `ratatoskr-client` Ktor `HttpClient` engine config — Android `OkHttpEngine.certificatePinner`, iOS `URLSession` pinning via `URLSessionDelegate.urlSession(_:didReceive:completionHandler:)`.
- Web: HSTS already covers transport; pin via `Expect-CT` if revived.

**DECISION:** _AWAITING CTO_ Classification: [ ] implementation follow-up [ ] security follow-up [ ] product/UX [ ] approval needed [ ] no-action with rationale

---

## 2. Secret show-once strategy

Question: when a user creates a long-lived secret key via the `secret-login` flow, do we show it plaintext exactly once, or do we always send it to the user's verified channel (Telegram DM) and never display it in the UI?

Evidence to weigh:

- Show-once is the industry default but trains users to screenshot secrets, weakening the storage assumptions.
- DM-only delivery requires the user has Telegram open and means the UI carries no secret — but it also fragments the UX across two surfaces.
- Either way, the **decoy PHC** path (`app/api/routers/auth/credential_auth.py:_DECOY_PHC`) must keep the timing-safe-compare guarantee.

Implementation surface (if approved):

- Show-once: extend the secret-key creation endpoint with a one-time `display_token` field whose lifetime is the UI render.
- DM-only: route plaintext through the existing Telegram bot notify path; UI returns metadata only.

**DECISION:** _AWAITING CTO_ Classification: [ ] implementation follow-up [ ] security follow-up [ ] product/UX [ ] approval needed [ ] no-action with rationale

---

## 3. AuditLog retention

Question: what is the retention policy for `AuditLog` rows (refresh-family revocations, secret-login attempts, account deletions)?

Evidence to weigh:

- Current schema (`app/db/models/core.py:AuditLog`) is append-only with no retention enforcement.
- Privacy claim in user-facing docs may need explicit retention window to be coherent.
- Investigative value of audit history is high during incident response — but indefinite retention enlarges the blast radius of a database compromise.

Implementation surface (if approved):

- New Taskiq nightly job pruning rows older than the retention window with a `last_pruned_at` watermark.
- Migration: optional `pii_redacted: bool` column to flag rows that have been scrubbed but kept for aggregate stats.

**DECISION:** _AWAITING CTO_  Retention window: ___________ Classification: [ ] implementation follow-up [ ] security follow-up [ ] product/UX [ ] approval needed [ ] no-action with rationale

---

## 4. Hosted MCP / CLI external exposure scope

Question: do we expand external exposure of the MCP server (`app/mcp/server.py`) and the CLI runner (`app/cli/`) beyond the owner-whitelist (`ALLOWED_USER_IDS`)? If yes, under which auth posture?

Evidence to weigh:

- The MCP server currently inherits owner-only ACL; broadening it changes the threat model significantly (multi-tenant rate-limiting, per-call cost attribution, abuse vectors).
- The CLI runner is local-only and stays that way unless the decision explicitly approves a hosted variant.
- The task spec is explicit: "Explicit approval is requested before any external exposure expansion."

**DECISION:** _AWAITING CTO — explicit approval gate_ Classification: [ ] approval needed [ ] no-action with rationale

---

## 5. Default `clearSavedCredentials` UX

Question: in the mobile client, when the user signs out, do we clear saved credentials by default, or do we keep them so the user can re-enter without re-entering the secret?

Evidence to weigh:

- Default-clear matches a higher-security posture but increases friction; users will likely opt back into "remember me".
- Default-keep matches mainstream consumer UX but means a stolen device retains a usable session boundary, mitigated only by the OS-level secure storage and the refresh-token family rotation in [[harden-refresh-token-rotation-revocation]].

**DECISION:** _AWAITING CTO_ Classification: [ ] implementation follow-up [ ] product/UX [ ] approval needed [ ] no-action with rationale

---

## Follow-up issue inventory

Backend's three high-priority blockers from the original review remain owned by the backend team and are tracked elsewhere:

- [[unify-allowed-user-ids-allowlist-semantics]]
- [[decouple-secret-login-pepper-from-jwt-key]]
- [[use-constant-time-compare-telegram-nonce]]

Once decisions 1–5 are recorded above, this memo links each decision to a created follow-up issue (one issue per "implementation follow-up" or "security review follow-up" classification) before the [[review-mobile-auth-threat-model]] gate can re-open.

## Risks of not deciding

The constraints in the task spec are explicit and remain in force:

- No release readiness claim can be made until Security and QA sign off on the second-wave remediation that flows from these decisions.
- The frontend-mobile task family ([[overhaul-articles-management]], [[run-frost-phase-7-mobile-regression]], [[map-ratatoskr-mobile-api-contract-to-kmp-readiness]]) cannot ship to production users while these auth decisions are open.
