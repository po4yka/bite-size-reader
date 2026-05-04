---
title: Decide second-wave Ratatoskr auth/security policy scope
status: doing
area: auth
priority: high
owner: CTO
blocks: [review-mobile-auth-threat-model]
blocked_by: []
created: 2026-04-30
updated: 2026-05-04
---

- [ ] #task Decide second-wave Ratatoskr auth/security policy scope #repo/ratatoskr #area/auth #status/doing ⏫

## Objective

Decide the second-wave Ratatoskr auth/security policy scope from the Security/AppSec review in [[review-mobile-auth-threat-model]], then create the follow-up implementation/review issues that are warranted.

## Context

Security marked Ratatoskr mobile auth, secret-login, and client storage not release-ready. The three high implementation blockers — [[unify-allowed-user-ids-allowlist-semantics]], [[decouple-secret-login-pepper-from-jwt-key]], and [[use-constant-time-compare-telegram-nonce]] — were assigned to Backend. Security deferred 11 additional follow-ups pending direction on scope.

## Acceptance criteria

- [ ] Decision memo posted covering TLS pinning policy, secret show-once strategy, AuditLog retention, hosted MCP/CLI exposure scope, and default clearSavedCredentials UX.
- [ ] Each decision is classified as implementation follow-up, security review follow-up, product/UX follow-up, approval needed, or no-action-with-rationale.
- [ ] Follow-up issues are created with explicit owners, acceptance criteria, expected artifact, constraints, risks, verification plan, and definition of done.
- [ ] Explicit approval is requested before any external exposure expansion, credential policy change, telemetry/privacy scope change, or release-readiness claim.

## Constraints

- Do not edit product code in this task.
- Do not grant credentials or change external access.
- Do not approve release readiness until Security and QA have signed off after follow-up remediation.

## Risks

- Shipping with inconsistent auth semantics or weak credential separation would undermine user trust.
- Over-scoping TLS pinning or hosted MCP/CLI exposure can create operational and support cost without a clear release gate.
- Under-documenting AuditLog retention or credential clearing UX leaves privacy claims ambiguous.

## Definition of done

The decision memo has been posted, deferred follow-ups created or explicitly rejected, and [[review-mobile-auth-threat-model]] left with a clear Security/AppSec re-review path.
