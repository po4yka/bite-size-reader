# Cross-Project Roadmap Priorities

> Active task board: [docs/tasks/dashboard.md](dashboard.md) · Per-issue backlog: [docs/tasks/backlog.md](backlog.md)

Last updated: 2026-05-02

Scope:

- Ratatoskr backend and Frost web client: `/Users/po4yka/GitRep/ratatoskr`
- Ratatoskr KMP mobile client: `/Users/po4yka/GitRep/ratatoskr-client`
- RIPDPI Android censorship-bypass app: `/Users/po4yka/GitRep/RIPDPI`

## Priority Queue

## Top 3 Near-Term Priorities

1. Ratatoskr Mobile API contract readiness.
   This is the first company priority because it gates every useful mobile-client
   release. The backend must prove that auth, refresh, sync sessions, summaries,
   collections, search, digest, signal endpoints, response envelopes, and error
   IDs match `docs/reference/mobile-api.md` and `docs/openapi/mobile_api.yaml`.
   Trade-off: backend contract work wins over new web features because mobile
   integration churn is more expensive after the client starts relying on the
   contract.
2. Ratatoskr-client offline-first release slice.
   Once contract readiness is verified, the KMP client should focus on the
   smallest user-visible Android/iOS path: sign in, sync, browse summaries,
   inspect summary detail, manage collections, and survive offline/refresh
   transitions. Trade-off: this defers broader polish and secondary iOS widgets
   until the core client proves it can safely consume real data.
3. RIPDPI critical-epic sequencing, not parallel execution.
   RIPDPI remains a separate governance lane. Leadership should sequence ownerless critical epics and keep quality gates visible, but Ratatoskr
   implementation capacity should not be borrowed for broad RIPDPI execution.
   Trade-off: this protects existing RIPDPI reliability work while keeping the
   Ratatoskr mobile release path from fragmenting.

### P0 Release Blockers

No cross-project P0 is declared from the available issue payload. Promote work to
P0 only when it blocks an imminent release, causes data loss/security exposure,
breaks the Ratatoskr Mobile API contract, or prevents RIPDPI from functioning on
non-rooted Android devices.

### P1 Next Sprint

1. Ratatoskr backend: freeze and verify the Mobile API surface against
   `docs/reference/mobile-api.md` and `docs/openapi/mobile_api.yaml` before mobile
   client release work. Success means the KMP client can rely on auth, sync,
   summaries, collections, search, digest, and signal endpoints without contract
   drift.
2. Ratatoskr KMP client: finish the offline-first mobile integration path over
   the existing API contract. Success means auth refresh, sync sessions, summary
   browsing, collections, digest, settings, and pending operations work through
   feature-owned repositories without importing transport DTOs into domain or UI.
3. Ratatoskr Frost web/client consistency: keep Frost implementation aligned
   across web and mobile without changing canonical tokens. Success means new UI
   work uses existing Frost primitives and passes the repo-specific static checks.
4. RIPDPI: preserve the non-rooted Android baseline while hardening diagnostics
   and recommendation reliability. Success means VPN/proxy flows, DNS failover,
   strategy probes, and home analysis remain usable without root; root-only
   features stay opt-in and degrade cleanly.

## Explicit Stop List

- Do not start Mobile API shape changes without leadership approval. Contract drift is
  more damaging than missing a secondary endpoint in the first release slice.
- Do not start Frost token or visual-system redesign work. Web and mobile should
  use existing Frost primitives and tokens.
- Do not start broad RIPDPI implementation from Ratatoskr capacity. RIPDPI
  critical epics need leadership sequencing and their own quality gates first.
- Do not start secondary mobile surfaces such as iOS widgets/share polish,
  advanced digest tuning, or recommendation experiments until auth + sync +
  summary browsing are proven end to end.
- Do not start new remote-service dependencies for RIPDPI. Its product baseline
  remains local/offline and non-root functional.

## User-Visible Release Milestones

1. Contract Gate: backend/web API contract verified.
   Users do not see this directly, but it is the release gate for all mobile
   work. Exit when API checks prove envelope, auth, sync, and summary surfaces
   are stable.
2. Mobile Alpha: authenticated offline-first reader.
   Users can sign in, sync, browse summaries, open detail, use collections, and
   recover from token refresh/offline transitions on the KMP client.
3. Mobile Beta: Frost parity and QA regression pass.
   Users get a coherent Frost interface across web/mobile, with QA signoff on Android/iOS smoke coverage before release expansion.
4. RIPDPI Maintenance Gate: critical epics sequenced.
   Users should not see a Ratatoskr-driven RIPDPI feature push yet; they should
   see continued non-root reliability and diagnostics quality once quality gates are clear.

## Decision Points

- Confirm Ratatoskr mobile contract readiness remains the top company priority
  until all auth, sync, summary, collections, search, digest, and signal
  contract tasks in the [task board](dashboard.md) are resolved.
- Confirm RIPDPI stays isolated from Ratatoskr implementation capacity until
  leadership provides sequencing for ownerless critical epics.
- Confirm no additional roadmap expansion starts until active QA/security gate
  tasks in the [task board](dashboard.md) report completion.

### P2 Backlog

1. Ratatoskr backend: improve observability and support tooling around scraper,
   LLM, sync, and API failure correlation without changing user-visible
   contracts.
2. Ratatoskr KMP client: expand iOS share/widget polish after the Android/KMP
   core path is stable.
3. RIPDPI: continue documentation and operational polish for strategy packs,
   relay profiles, native size monitoring, and manual diagnostics assets.

### P3 Archive

Archive or defer work that only changes visual preference, duplicates existing
docs, adds remote-service dependence to RIPDPI, or requires Frost token/Mobile
API contract changes without leadership approval.

## Coordination Rules

- Mobile API contract changes and Frost token changes require leadership involvement before implementation tasks are created.
- Release readiness requires QA signoff on the relevant regression gate:
  Ratatoskr backend/API checks, ratatoskr-client KMP checks, or RIPDPI Android
  build/static/unit/diagnostic smoke checks.
- Child issues should be created only after confirming the concrete implementation slice, success criteria, and blocker graph.
