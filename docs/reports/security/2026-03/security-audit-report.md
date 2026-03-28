# Security Audit Report

**Project**: Bite-Size Reader
**Date**: 2026-03-23
**Auditor**: Claude Security Audit
**Frameworks**: OWASP Top 10:2025 + NIST CSF 2.0 + CWE + SANS Top 25 + ASVS 5.0 + PCI DSS 4.0.1 + MITRE ATT&CK + SOC 2 + ISO 27001:2022
**Mode**: full (Phases 1-5)

---

## Executive Summary

| Metric | Count |
|--------|-------|
| :red_circle: Critical | 0 |
| :orange_circle: High | 2 |
| :yellow_circle: Medium | 8 |
| :green_circle: Low | 5 |
| :blue_circle: Informational | 4 |
| :black_square_button: Gray-box findings | 3 |
| :round_pushpin: Security hotspots | 10 |
| :broom: Code smells | 5 |
| **Total findings** | **37** |

**Overall Risk Assessment**: The project has strong security foundations -- proper JWT validation, HMAC-based Telegram auth with constant-time comparison, hash-only token storage, comprehensive SSRF protection on the main URL pipeline, and consistent ownership checks. The most significant risks are: (1) webhook delivery SSRF via DNS rebinding bypass, (2) account deletion without re-authentication, and (3) inconsistent fail-open/fail-closed behavior when user allowlists are empty. No critical vulnerabilities were found after the prior quick-audit fixes.

---

## OWASP Top 10:2025 Coverage

| OWASP ID | Category | Findings | Status |
|----------|----------|----------|--------|
| A01:2025 | Broken Access Control | 6 | :orange_circle: Needs Attention |
| A02:2025 | Security Misconfiguration | 2 | :yellow_circle: Needs Attention |
| A03:2025 | Software Supply Chain Failures | 1 | :yellow_circle: Needs Attention |
| A04:2025 | Cryptographic Failures | 0 | :white_check_mark: Acceptable |
| A05:2025 | Injection | 0 | :white_check_mark: Acceptable |
| A06:2025 | Insecure Design | 3 | :yellow_circle: Needs Attention |
| A07:2025 | Authentication Failures | 4 | :yellow_circle: Needs Attention |
| A08:2025 | Software or Data Integrity Failures | 0 | :white_check_mark: Acceptable |
| A09:2025 | Security Logging and Alerting Failures | 2 | :yellow_circle: Needs Attention |
| A10:2025 | Mishandling of Exceptional Conditions | 1 | :green_circle: Low Risk |

---

## NIST CSF 2.0 Coverage

| Function | Categories | Findings | Status |
|----------|-----------|----------|--------|
| GV (Govern) | GV.SC | 1 | :yellow_circle: Needs Attention |
| ID (Identify) | ID.AM, ID.RA, ID.IM | 0 | :white_check_mark: Acceptable |
| PR (Protect) | PR.AA, PR.DS, PR.PS | 12 | :orange_circle: Needs Attention |
| DE (Detect) | DE.CM, DE.AE | 2 | :yellow_circle: Needs Attention |
| RS (Respond) | RS.MA, RS.AN | 0 | :white_check_mark: Acceptable |
| RC (Recover) | RC.RP, RC.CO | 0 | :white_check_mark: Acceptable |

---

## Compliance Coverage

| Framework | Coverage | Details |
|-----------|----------|---------|
| CWE | 14 unique CWEs | CWE-918, CWE-862, CWE-367, CWE-863, CWE-307, CWE-613, CWE-352, CWE-778, CWE-770, CWE-829, CWE-209, CWE-203, CWE-330, CWE-284 |
| SANS/CWE Top 25 | 5/25 entries | #4 CWE-862, #11 CWE-918, #16 CWE-352, #20 CWE-306, #24 CWE-863 |
| OWASP ASVS 5.0 | 5/14 chapters | V2 (Authentication), V3 (Session), V4 (Access Control), V5 (Validation), V13 (API) |
| PCI DSS 4.0.1 | 3 requirements | 6.2.4 (software attacks), 6.3.2 (known vulns), 8.3.4 (auth attempts) |
| MITRE ATT&CK | 4 techniques | T1190 (Exploit Public App), T1557 (AitM), T1110 (Brute Force), T1530 (Data from Cloud) |
| SOC 2 | 3 criteria | CC6.1 (Logical Access), CC6.3 (Role-Based Access), CC7.2 (Security Event Monitoring) |
| ISO 27001:2022 | 4 controls | A.5.15 (Access Control), A.8.3 (Information Access Restriction), A.8.24 (Use of Cryptography), A.8.28 (Secure Coding) |

---

## :orange_circle: High Findings

### :orange_circle: [HIGH-001] Webhook SSRF via DNS Rebinding -- No DNS Resolution on Delivery

- **Severity**: :orange_circle: HIGH
- **OWASP**: A01:2025 (Broken Access Control -- SSRF)
- **CWE**: CWE-918 (Server-Side Request Forgery)
- **NIST CSF**: PR.DS (Data Security)
- **Compliance**: SANS Top 25 #11 | ASVS V13.1.1 | PCI DSS 6.2.4 | T1190 | CC6.1 | A.8.28
- **Location**: `app/domain/services/webhook_service.py:29-68` and `app/api/routers/webhooks.py:269-280`
- **Attack Vector**:
  1. Attacker registers webhook with URL `https://evil.example.com/hook` (passes `validate_webhook_url` since hostname is not a literal IP)
  2. `evil.example.com` DNS resolves to `169.254.169.254` (AWS metadata) or `10.0.0.1` (internal)
  3. On `POST /v1/webhooks/{id}/test` or any event trigger, server POSTs to internal service
  4. Attacker reads cloud credentials or internal API responses from delivery log (`response_body` stored up to 2000 chars)
- **Impact**: Internal network scanning, cloud metadata credential theft, access to internal services. Response body is stored in delivery log and returned to the attacker.
- **Vulnerable Code**:

  ```python
  # webhook_service.py:57-66 -- only checks literal IPs, not DNS-resolved
  try:
      addr = ip_address(hostname)
      if addr.is_private or addr.is_reserved or addr.is_loopback:
          ...
  except ValueError:
      pass  # Not an IP literal -- hostname DNS not checked

  # webhooks.py:269-280 -- delivery has no SSRF check
  async with httpx.AsyncClient(timeout=10.0) as client:
      resp = await client.post(sub["url"], ...)
  ```

- **Remediation**: Add DNS resolution check before every webhook delivery (not just at registration). Reuse `_resolve_host_ips()` and `BLOCKED_NETWORKS` from `app/api/routers/proxy.py`. Validate both at registration and at delivery time to prevent DNS rebinding.

---

### :orange_circle: [HIGH-002] Account Deletion Without Re-authentication

- **Severity**: :orange_circle: HIGH
- **OWASP**: A06:2025 (Insecure Design)
- **CWE**: CWE-352 (Missing Re-authentication for Critical Action)
- **NIST CSF**: PR.AA (Identity Management)
- **Compliance**: ASVS V2.1.1 | PCI DSS 8.3.4 | T1530 | CC6.1 | A.5.15
- **Location**: `app/api/routers/auth/endpoints_me.py` (DELETE /auth/me)
- **Attack Vector**:
  1. Attacker steals a valid JWT access token (XSS, MITM, device theft)
  2. Calls `DELETE /v1/auth/me` with stolen token
  3. User's entire account is permanently deleted including all summaries, collections, settings
  4. No confirmation, no re-authentication, no recovery
- **Impact**: Permanent data loss from a single stolen access token. Access tokens are valid for 30 minutes.
- **Vulnerable Code**:

  ```python
  # Only requires standard JWT auth -- no re-authentication step
  async def delete_account(user: dict[str, Any] = Depends(get_current_user)):
      await AuthService.delete_user(user_id)
  ```

- **Remediation**: Require password/secret re-entry or Telegram auth confirmation before account deletion. Add a confirmation step with a short-lived deletion token.

---

## :yellow_circle: Medium Findings

### :yellow_circle: [MEDIUM-001] RSS Feed Items Accessible Without Subscription Check

- **Severity**: :yellow_circle: MEDIUM
- **OWASP**: A01:2025 (Broken Access Control)
- **CWE**: CWE-862 (Missing Authorization)
- **NIST CSF**: PR.AA (Identity Management)
- **Compliance**: SANS Top 25 #4 | ASVS V4.1.2 | CC6.3 | A.5.15
- **Location**: `app/api/routers/rss.py:142-173`
- **Attack Vector**: Any authenticated user can call `GET /v1/rss/feeds/{feed_id}/items` with any feed_id and receive all feed items, regardless of whether they are subscribed to that feed. Similarly, `POST /v1/rss/feeds/{feed_id}/refresh` allows any user to trigger a refresh.
- **Impact**: Information disclosure of other users' RSS feed content; resource exhaustion via unauthorized feed refresh.
- **Vulnerable Code**:

  ```python
  @router.get("/feeds/{feed_id}/items")
  async def list_feed_items(feed_id: int, ...):
      feed = await repo.async_get_feed(feed_id)  # No subscription check
      items = await repo.async_list_feed_items(feed_id, ...)
  ```

- **Remediation**: Verify the requesting user has an active subscription to the feed before returning items or allowing refresh.

---

### :yellow_circle: [MEDIUM-002] Refresh Token Rotation Race Condition

- **Severity**: :yellow_circle: MEDIUM
- **OWASP**: A07:2025 (Authentication Failures)
- **CWE**: CWE-367 (TOCTOU Race Condition)
- **NIST CSF**: PR.AA (Identity Management)
- **Compliance**: ASVS V3.5.2 | T1557 | CC6.1 | A.8.24
- **Location**: `app/api/routers/auth/endpoints_sessions.py:58-127`
- **Attack Vector**: Two concurrent `POST /v1/auth/refresh` requests with the same valid refresh token can both pass the `is_revoked` check before either completes the revocation, resulting in two valid session pairs.
- **Impact**: Duplicate sessions created; partially mitigated by reuse detection (replay of already-revoked token triggers revocation of ALL user tokens).
- **Vulnerable Code**:

  ```python
  # Not atomic: check-then-revoke-then-create
  stored = await auth_repo.async_get_refresh_token(token_hash)
  if stored.get("is_revoked"):  # TOCTOU window
      ...
  await auth_repo.async_revoke_refresh_token(token_hash)
  new_token, session_id = await create_refresh_token(...)
  ```

- **Remediation**: Use database-level locking (SELECT FOR UPDATE equivalent in SQLite: BEGIN EXCLUSIVE) or an atomic compare-and-swap operation when rotating refresh tokens.

---

### :yellow_circle: [MEDIUM-003] Image Proxy DNS Rebinding (TOCTOU)

- **Severity**: :yellow_circle: MEDIUM
- **OWASP**: A01:2025 (Broken Access Control -- SSRF)
- **CWE**: CWE-367 (TOCTOU Race Condition)
- **NIST CSF**: PR.DS (Data Security)
- **Compliance**: SANS Top 25 #11 | ASVS V13.1.1 | T1190 | A.8.28
- **Location**: `app/api/routers/proxy.py:126-148`
- **Attack Vector**: `_is_url_safe()` resolves DNS and checks IPs, but `httpx.AsyncClient.send()` resolves DNS independently. An attacker controlling a DNS server can return a public IP for the first resolution (passes check) and a private IP for the second (reaches internal service).
- **Impact**: SSRF via DNS rebinding, though the attack requires DNS server control and precise timing.
- **Vulnerable Code**:

  ```python
  if not _is_url_safe(current_url):   # DNS resolution #1
      raise AuthorizationError(...)
  resp = await client.send(req, ...)  # DNS resolution #2 (may differ)
  ```

- **Remediation**: Resolve DNS once, then connect directly to the resolved IP using httpx transport with pre-resolved addresses.

---

### :yellow_circle: [MEDIUM-004] JWT Auth Fail-Open When ALLOWED_USER_IDS Empty

- **Severity**: :yellow_circle: MEDIUM
- **OWASP**: A01:2025 (Broken Access Control)
- **CWE**: CWE-863 (Incorrect Authorization)
- **NIST CSF**: PR.AA (Identity Management)
- **Compliance**: ASVS V4.1.1 | CC6.1 | A.5.15
- **Location**: `app/api/routers/auth/dependencies.py:124`
- **Attack Vector**: When `ALLOWED_USER_IDS` is empty and OAuth providers (Apple/Google) are enabled, any person with an Apple/Google account can sign up and get full API access. JWT auth path uses `fail_open_when_empty=True` while WebApp auth uses `fail_open_when_empty=False` -- inconsistent security posture.
- **Impact**: Unauthorized access if operator forgets to set `ALLOWED_USER_IDS` and has OAuth enabled.
- **Vulnerable Code**:

  ```python
  if not Config.is_user_allowed(user_id, fail_open_when_empty=True):
  ```

- **Remediation**: Require explicit opt-in for open registration (e.g., `ALLOW_ALL_USERS=true`) rather than silently allowing when allowlist is empty.

---

### :yellow_circle: [MEDIUM-005] No Auth-Specific Rate Limiting on Login Endpoints

- **Severity**: :yellow_circle: MEDIUM
- **OWASP**: A07:2025 (Authentication Failures)
- **CWE**: CWE-307 (Improper Restriction of Excessive Authentication Attempts)
- **NIST CSF**: PR.AA (Identity Management), DE.CM (Continuous Monitoring)
- **Compliance**: SANS Top 25 #20 | ASVS V2.2.1 | PCI DSS 8.3.4 | T1110 | CC7.2 | A.5.15
- **Location**: `app/api/middleware.py:359-366`
- **Attack Vector**: Rate limit middleware has buckets for summaries/search/requests but no specific bucket for auth endpoints. Login and refresh endpoints fall through to the default bucket, allowing significantly more attempts than appropriate for brute-force protection.
- **Impact**: Brute-force attacks on refresh tokens, credential stuffing on OAuth endpoints.
- **Vulnerable Code**:

  ```python
  # No "auth" bucket -- falls through to default
  if "/summaries" in path: bucket = "summaries"
  elif "/search" in path: bucket = "search"
  elif "/requests" in path: bucket = "requests"
  # /v1/auth/* uses default limit
  ```

- **Remediation**: Add an `auth` rate limit bucket with stricter limits (e.g., 10 requests per minute per IP).

---

### :yellow_circle: [MEDIUM-006] Deleted User Tokens Persist in Redis Cache

- **Severity**: :yellow_circle: MEDIUM
- **OWASP**: A07:2025 (Authentication Failures)
- **CWE**: CWE-613 (Insufficient Session Expiration)
- **NIST CSF**: PR.AA (Identity Management)
- **Compliance**: ASVS V3.3.1 | CC6.1 | A.5.15
- **Location**: `app/api/routers/auth/endpoints_me.py` (DELETE /auth/me) and `app/infrastructure/persistence/sqlite/repositories/user_repository.py:141-148`
- **Attack Vector**: Account deletion cascades DB token deletion (SQLite CASCADE) but does not invalidate Redis-cached tokens. A cached refresh token could pass cache-layer validation until Redis TTL expires.
- **Impact**: Brief window where deleted user's tokens remain valid in cache. Subsequent DB lookup would fail, but creates inconsistent state.
- **Remediation**: Call `auth_repo.async_revoke_all_user_tokens()` before user deletion to ensure both DB and cache are cleared.

---

### :yellow_circle: [MEDIUM-007] Docker Base Images Not Pinned to SHA256 Digest

- **Severity**: :yellow_circle: MEDIUM
- **OWASP**: A03:2025 (Software Supply Chain Failures)
- **CWE**: CWE-829 (Inclusion of Functionality from Untrusted Control Sphere)
- **NIST CSF**: GV.SC (Supply Chain Risk Management)
- **Compliance**: ASVS V14.2.1 | PCI DSS 6.3.2 | CC6.1 | A.8.28
- **Location**: `Dockerfile:6,45,57`
- **Attack Vector**: `FROM python:3.13-slim` and `FROM node:25-alpine` use tag-based references that can be silently replaced by a compromised registry.
- **Impact**: Malicious base image could compromise entire build pipeline.
- **Vulnerable Code**:

  ```dockerfile
  FROM python:3.13-slim AS builder   # Tag can be replaced
  FROM node:25-alpine AS web-build   # Tag can be replaced
  FROM python:3.13-slim AS runtime   # Tag can be replaced
  ```

- **Remediation**: Pin each base image to a specific SHA256 digest: `FROM python:3.13-slim@sha256:<digest>`.

---

### :yellow_circle: [MEDIUM-008] No Alerting on Repeated Authentication Failures

- **Severity**: :yellow_circle: MEDIUM
- **OWASP**: A09:2025 (Security Logging and Alerting Failures)
- **CWE**: CWE-778 (Insufficient Logging)
- **NIST CSF**: DE.AE (Adverse Event Analysis)
- **Compliance**: ASVS V2.2.1 | PCI DSS 10.6.1 | CC7.2 | A.8.15
- **Location**: Application-wide (auth event handlers)
- **Attack Vector**: Individual auth failures are logged, but there is no mechanism to detect patterns (N failures from same IP in M minutes) or trigger alerts. An attacker can slowly brute-force without detection.
- **Impact**: Brute-force attacks go undetected until manual log review.
- **Remediation**: Add auth failure aggregation and alerting threshold (e.g., 10 failures/5 min triggers alert).

---

## :green_circle: Low & :blue_circle: Informational Findings

### :green_circle: [LOW-001] Collection Existence Oracle via Error Differentiation

- **Severity**: :green_circle: LOW
- **OWASP**: A01:2025 (Broken Access Control)
- **CWE**: CWE-203 (Observable Discrepancy)
- **NIST CSF**: PR.DS (Data Security)
- **Location**: `app/api/services/collection_service.py:82-106`
- **Vulnerable Code**: Returns 404 for non-existent collections, 403 for existing but unauthorized. Allows enumeration of valid collection IDs.
- **Remediation**: Return uniform 404 for both cases (check existence and authorization together).

### :green_circle: [LOW-002] Secret Key Revocation Does Not Invalidate Existing Sessions

- **Severity**: :green_circle: LOW
- **OWASP**: A07:2025 (Authentication Failures)
- **CWE**: CWE-613 (Insufficient Session Expiration)
- **NIST CSF**: PR.AA (Identity Management)
- **Location**: `app/api/routers/auth/endpoints_secret_keys.py:256-294`
- **Vulnerable Code**: Revoking a secret key prevents new logins but existing JWT/refresh tokens remain valid (30 min / 30 day expiry).
- **Remediation**: Revoke all refresh tokens for the user/client_id pair when a secret key is revoked.

### :green_circle: [LOW-003] Debug Error Messages May Leak Internal Details

- **Severity**: :green_circle: LOW
- **OWASP**: A10:2025 (Mishandling of Exceptional Conditions)
- **CWE**: CWE-209 (Error Message Containing Sensitive Info)
- **NIST CSF**: DE.AE (Adverse Event Analysis)
- **Location**: `app/api/error_handlers.py:134-136`
- **Vulnerable Code**: When `LOG_LEVEL=DEBUG`, `str(exc)` is returned to clients, potentially leaking internal paths or query details.
- **Remediation**: Never return `str(exc)` in API responses, even in debug mode.

### :green_circle: [LOW-004] FTS5 Query Construction (Well-Mitigated)

- **Severity**: :green_circle: LOW
- **OWASP**: A05:2025 (Injection)
- **CWE**: CWE-89 (SQL Injection)
- **NIST CSF**: PR.DS (Data Security)
- **Location**: `app/infrastructure/persistence/sqlite/repositories/topic_search_repository.py:576-607`
- **Vulnerable Code**: User search queries are sanitized via `_sanitize_fts_term()` (strips to `[\w-]` only) and passed via parameterized MATCH. Defense is adequate but relies on sanitizer correctness.
- **Remediation**: No immediate action needed; maintain sanitizer coverage in tests.

### :green_circle: [LOW-005] Export Collection Filter Missing Ownership Check

- **Severity**: :green_circle: LOW
- **OWASP**: A01:2025 (Broken Access Control)
- **CWE**: CWE-862 (Missing Authorization)
- **NIST CSF**: PR.AA (Identity Management)
- **Location**: `app/api/routers/import_export.py:270-278`
- **Vulnerable Code**: Collection ID filter in export doesn't verify ownership, but outer user_id filter prevents data leakage. Could leak which summaries are in another user's collection.
- **Remediation**: Add collection ownership verification before applying the filter.

### :blue_circle: [INFO-001] Sequential Collection IDs Enable Enumeration

- **Severity**: :blue_circle: INFO
- **OWASP**: A01:2025
- **CWE**: CWE-330 (Use of Insufficiently Random Values)
- **Location**: `app/db/_models_collections.py:15` -- `id = peewee.AutoField()`
- **Note**: Combined with LOW-001, enables trivial enumeration. Consider UUIDs for shared resources.

### :blue_circle: [INFO-002] Health Probes Intentionally Unauthenticated

- **Severity**: :blue_circle: INFO
- **Location**: `app/api/routers/health.py:290-335`
- **Note**: `/health/ready` and `/health/live` expose only boolean status for K8s probes. `/health/detailed` properly requires auth. Acceptable design.

### :blue_circle: [INFO-003] Webhook HMAC Properly Implemented

- **Severity**: :blue_circle: INFO (Positive)
- **Location**: `app/domain/services/webhook_service.py:18-26`
- **Note**: Uses `hmac.compare_digest()` for constant-time comparison. Secret generation uses `secrets.token_hex(32)`.

### :blue_circle: [INFO-004] JWT HS256 Algorithm Properly Restricted

- **Severity**: :blue_circle: INFO (Positive)
- **Location**: `app/api/routers/auth/tokens.py:56,175`
- **Note**: `jwt.decode()` uses `algorithms=[ALGORITHM]` preventing algorithm confusion attacks. HS256 is appropriate for single-server deployment.

---

## :black_square_button: Gray-Box Findings

### [GRAY-001] Collection Existence Oracle

- **Severity**: :green_circle: LOW
- **OWASP**: A01:2025
- **CWE**: CWE-203
- **NIST CSF**: PR.DS
- **Tested As**: Regular authenticated user (not owner/collaborator)
- **Endpoint**: `GET /v1/collections/{collection_id}`
- **Expected**: Uniform 404 for both non-existent and unauthorized collections
- **Actual**: 404 for non-existent, 403 for existing-but-unauthorized
- **Request**: `GET /v1/collections/99999` (returns 404) vs `GET /v1/collections/1` (returns 403)
- **Remediation**: Combine existence and authorization check; return 404 for both cases.

### [GRAY-002] Admin Owner Check Uses DB Lookup (Positive)

- **Severity**: :blue_circle: INFO (Positive)
- **Tested As**: Regular authenticated user
- **Endpoint**: `GET /v1/admin/users`, `GET /v1/system/db-dump`
- **Expected**: 403 for non-owner
- **Actual**: Correctly returns 403 via `AuthService.require_owner()` which queries DB (not JWT claims)
- **Note**: Cannot be bypassed by forging JWT claims since `is_owner` is checked against the User DB record.

### [GRAY-003] Webhook/Rule/Tag Ownership Returns Uniform 404 (Positive)

- **Severity**: :blue_circle: INFO (Positive)
- **Tested As**: Regular authenticated user accessing another user's resources
- **Endpoint**: `GET /v1/webhooks/{id}`, `GET /v1/rules/{id}`, `GET /v1/tags/{id}`
- **Expected**: No information leakage about other users' resources
- **Actual**: All return 404 for both non-existent and non-owned resources (correct pattern)

---

## :round_pushpin: Security Hotspots

### [HOTSPOT-001] JWT Secret Key Management

- **OWASP**: A04:2025
- **CWE**: CWE-321
- **NIST CSF**: PR.DS
- **Location**: `app/api/routers/auth/tokens.py:29-68`
- **Why sensitive**: JWT secret key is the root of trust for all API authentication
- **Risk if modified**: Token forgery, session hijacking for all users
- **Review guidance**: Verify minimum length (32), no logging of secret, no default values accepted

### [HOTSPOT-002] Telegram WebApp HMAC Validation

- **OWASP**: A07:2025
- **CWE**: CWE-347
- **NIST CSF**: PR.AA
- **Location**: `app/api/routers/auth/webapp_auth.py:56-86`
- **Why sensitive**: Validates Telegram Mini App authentication; uses BOT_TOKEN as HMAC key
- **Risk if modified**: Authentication bypass for Mini App users; replay attacks if timestamp check removed
- **Review guidance**: Preserve constant-time comparison, timestamp freshness check, and data_check_string ordering

### [HOTSPOT-003] Access Controller Whitelist

- **OWASP**: A01:2025
- **CWE**: CWE-284
- **NIST CSF**: PR.AA
- **Location**: `app/adapters/telegram/access_controller.py:89-190`
- **Why sensitive**: Primary access gate for Telegram bot; blocks unauthorized users
- **Risk if modified**: Unauthorized bot access, lockout bypass
- **Review guidance**: Ensure `ALLOWED_USER_IDS` validation at startup, failed attempt tracking, lockout threshold

### [HOTSPOT-004] URL Validation & SSRF Protection

- **OWASP**: A01:2025
- **CWE**: CWE-918
- **NIST CSF**: PR.DS
- **Location**: `app/core/url_utils.py:112-148`, `app/api/routers/proxy.py:29-47,76-115`
- **Why sensitive**: Prevents SSRF on user-submitted URLs; blocks internal network access
- **Risk if modified**: SSRF leading to cloud credential theft, internal service access
- **Review guidance**: Verify all private ranges covered, DNS resolution check present, redirect handling safe

### [HOTSPOT-005] Refresh Token Rotation & Reuse Detection

- **OWASP**: A07:2025
- **CWE**: CWE-384
- **NIST CSF**: PR.AA
- **Location**: `app/api/routers/auth/endpoints_sessions.py:58-127`
- **Why sensitive**: Token rotation prevents stolen refresh token reuse; reuse detection triggers mass revocation
- **Risk if modified**: Token theft goes undetected; session hijacking
- **Review guidance**: Preserve revoke-before-create order, reuse detection cascade, token hash storage

### [HOTSPOT-006] Content-to-LLM Pipeline

- **OWASP**: A05:2025
- **CWE**: CWE-94
- **NIST CSF**: PR.DS
- **Location**: `app/adapters/content/pure_summary_service.py:84-86`, `app/core/content_cleaner.py:14-32`
- **Why sensitive**: User content enters LLM prompts; indirect prompt injection possible
- **Risk if modified**: Prompt injection, data exfiltration via LLM
- **Review guidance**: Maintain CONTENT START/END delimiters, content cleaning, output validation

### [HOTSPOT-007] LLM Output Validation

- **OWASP**: A08:2025
- **CWE**: CWE-20
- **NIST CSF**: PR.DS
- **Location**: `app/core/summary_contract.py`, `app/core/summary_schema.py`
- **Why sensitive**: Validates LLM output before storage and rendering
- **Risk if modified**: XSS via LLM output, data corruption, contract violations
- **Review guidance**: Maintain strict schema validation, HTML escaping in card renderer

### [HOTSPOT-008] Client Secret Hashing (Salt + Pepper)

- **OWASP**: A04:2025
- **CWE**: CWE-916
- **NIST CSF**: PR.DS
- **Location**: `app/api/routers/auth/secret_auth.py:42-51,108-112`
- **Why sensitive**: Client secrets hashed with HMAC(pepper, salt+payload); pepper compromise breaks all secrets
- **Risk if modified**: Secret recovery from database if hashing weakened
- **Review guidance**: Verify pepper loaded from env, not logged, salt is random per-secret

### [HOTSPOT-009] MCP Server User Scoping

- **OWASP**: A01:2025
- **CWE**: CWE-639
- **NIST CSF**: PR.AA
- **Location**: `app/mcp/server.py:90-95`, `app/mcp/context.py:72-80`
- **Why sensitive**: MCP tools expose full article/collection data to AI agents
- **Risk if modified**: Cross-user data access if scoping removed or bypassed
- **Review guidance**: Ensure `MCP_USER_ID` is always set in production; reject unscoped access

### [HOTSPOT-010] Database Session Manager

- **OWASP**: A02:2025
- **CWE**: CWE-16
- **NIST CSF**: PR.PS
- **Location**: `app/db/session.py`
- **Why sensitive**: Sole DB entry point; manages connections, migrations, FTS5 indexing
- **Risk if modified**: Data corruption, migration failures, connection leaks
- **Review guidance**: Verify WAL mode, async RW lock, migration ordering

---

## :broom: Code Smells

### [SMELL-001] Large Files with Security Logic

- **OWASP**: A06:2025
- **CWE**: CWE-1080 (Source Code File with Excessive Number of Lines of Code)
- **NIST CSF**: GV.RM
- **Location**: `app/adapters/telegram/callback_actions.py` (860 lines), `app/core/url_utils.py` (833 lines)
- **Pattern**: Security-critical logic (URL validation, callback routing) in large files
- **Security implication**: Harder to audit, higher risk of missed vulnerabilities during code review
- **Suggestion**: Break into focused modules (url_validation.py, url_normalization.py, url_ssrf.py)

### [SMELL-002] Inconsistent Fail-Open/Fail-Closed Patterns

- **OWASP**: A06:2025
- **CWE**: CWE-636 (Not Failing Securely)
- **NIST CSF**: PR.AA
- **Location**: `app/api/routers/auth/dependencies.py:124` vs `app/api/routers/auth/webapp_auth.py:103`
- **Pattern**: JWT uses `fail_open_when_empty=True`, WebApp uses `fail_open_when_empty=False`
- **Security implication**: Inconsistent security posture could confuse operators; one path is secure-by-default while the other is not
- **Suggestion**: Document the difference clearly; add startup warning when fail-open is active with OAuth enabled

### [SMELL-003] Silent Exception Suppression in Initialization

- **OWASP**: A10:2025
- **CWE**: CWE-390 (Detection of Error Condition Without Action)
- **NIST CSF**: DE.AE
- **Location**: `app/di/telegram.py:693,726` -- broad `except Exception` during bot setup
- **Pattern**: Initialization failures caught and logged but execution continues
- **Security implication**: Misconfigured security features (rate limiter, cache, etc.) could silently fail
- **Suggestion**: Add structured logging with severity level; consider failing startup for security-critical components

### [SMELL-004] SSRF Protection Logic in Multiple Locations

- **OWASP**: A01:2025
- **CWE**: CWE-1041 (Use of Redundant Code)
- **NIST CSF**: PR.DS
- **Location**: `app/api/routers/proxy.py` (BLOCKED_NETWORKS), `app/core/url_utils.py` (_validate_hostname_security), `app/adapters/rss/feed_fetcher.py` (imports from proxy), `app/domain/services/webhook_service.py` (own validation)
- **Pattern**: SSRF validation implemented differently across 4 locations
- **Security implication**: Inconsistent coverage; webhook validator missed DNS resolution while proxy and RSS have it
- **Suggestion**: Extract a single `ssrf_validator` module used by all HTTP-requesting code paths

### [SMELL-005] 26 contextlib.suppress(Exception) Calls

- **OWASP**: A10:2025
- **CWE**: CWE-390
- **NIST CSF**: DE.AE
- **Location**: Application-wide (26 occurrences)
- **Pattern**: Broad exception suppression in optional/non-critical paths (Redis cache, MCP init, audit logging)
- **Security implication**: Most are justified fail-soft patterns, but some could mask security-relevant errors
- **Suggestion**: Audit each suppression for security relevance; add logging where absent

---

## Recommendations Summary

**Priority 1 -- Fix This Sprint:**

1. **[HIGH-001]** Add DNS resolution + private IP check to webhook delivery path (SSRF)
2. **[HIGH-002]** Require re-authentication for account deletion
3. **[MEDIUM-005]** Add auth-specific rate limit bucket for login/refresh endpoints
4. **[MEDIUM-001]** Add subscription ownership check to RSS feed item endpoints

**Priority 2 -- Fix This Month:**
5. **[MEDIUM-002]** Make refresh token rotation atomic (DB-level lock)
6. **[MEDIUM-004]** Require explicit opt-in for fail-open allowlist behavior
7. **[MEDIUM-006]** Invalidate Redis cache on user deletion
8. **[MEDIUM-007]** Pin Docker base images to SHA256 digests
9. **[MEDIUM-008]** Add auth failure aggregation and alerting

**Priority 3 -- Backlog:**
10. **[LOW-001]** Uniform 404 for collection access (prevent enumeration)
11. **[LOW-002]** Revoke sessions on secret key revocation
12. **[SMELL-004]** Consolidate SSRF validation into single module

---

## Methodology

| Aspect | Details |
|--------|---------|
| Phases executed | 1-5 (Full audit) |
| Frameworks detected | FastAPI (Python 3.13), React 18 + TypeScript + Vite, Peewee ORM, Pyrogram |
| White-box categories | All 20 categories scanned |
| Gray-box testing | Regular user vs owner, 3 findings (1 vulnerability, 2 positive confirmations) |
| Security hotspots | 10 hotspots across crypto, auth, access control, LLM, and infrastructure |
| Code smells | 5 patterns: large files, inconsistent fail-open, suppressed exceptions, duplicated SSRF, broad suppress |
| Packs loaded | None |
| Scope exclusions | No `.security-audit-ignore` file found |
| Baseline comparison | No `.security-audit-baseline.json` found |
| OWASP Top 10:2025 | 10/10 categories covered |
| NIST CSF 2.0 | All 6 functions covered (GV, ID, PR, DE, RS, RC) |
| CWE | 14 unique CWE IDs identified |
| SANS/CWE Top 25 | 5/25 matched (#4, #11, #16, #20, #24) |
| ASVS 5.0 | 5/14 chapters with findings (V2, V3, V4, V5, V13) |
| Additional frameworks | PCI DSS 4.0.1 (3 requirements), MITRE ATT&CK (4 techniques), SOC 2 (3 criteria), ISO 27001:2022 (4 controls) |

### Areas Confirmed Clean

- **SQL Injection**: All production queries use Peewee ORM parameterization. FTS5 queries use sanitized terms via parameterized MATCH.
- **Command Injection**: No `os.system()`, `eval()`, `exec()`, or unsafe `subprocess` calls.
- **XSS**: LLM output HTML-escaped in Telegram card renderer. React JSX auto-escapes. No `dangerouslySetInnerHTML`.
- **Cryptographic Failures**: JWT HS256 with algorithm restriction. HMAC-SHA256 with constant-time comparison. SHA-256 for token hashes. No MD5/SHA1 for security.
- **Hardcoded Secrets**: None found. All secrets from environment variables.
- **Deserialization**: Pickle fallback removed (prior audit fix). Only safe JSON parsing (`orjson.loads`, `json.loads`).
- **CSRF**: Refresh cookie uses `httpOnly=True`, `secure=True`, `samesite="strict"`, path-scoped to `/v1/auth`.
- **Docker Security**: Non-root user (`appuser`, UID 1000), `no-new-privileges:true`, no login shell.
- **CI/CD**: GitHub Actions use `${{ secrets.* }}` safely; no injection via event payloads.
- **Authorization Redaction**: API keys/tokens redacted before logging and DB persistence.

---

*Report generated by Claude Security Audit*
