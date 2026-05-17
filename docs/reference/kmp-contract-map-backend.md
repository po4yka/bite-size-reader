# Backend half of the Ratatoskr ↔ ratatoskr-client contract map

This is the backend-side of the cross-repo contract map called for
by [[map-ratatoskr-mobile-api-contract-to-kmp-readiness]]. It
inventories the 146 `/v1/*` endpoints currently in
`docs/openapi/mobile_api.yaml`, grouped by feature area, with
source-of-truth pointers and notes for the KMP client team.

The **client-side half** (which features actually consume each
surface, gaps in client DTOs, KMP module owners) belongs in the
ratatoskr-client repo and is out of scope here.

| field | value |
| --- | --- |
| as of commit | `git log -1 --format=%h` at the time this file was written |
| openapi spec | `docs/openapi/mobile_api.yaml` (146 paths) |
| envelope | `{ "ok": true, "data": …, "pagination": … }` — see `app/api/models/responses/common.py` |
| error envelope | `{ "ok": false, "error": { code, message, correlation_id } }` |
| auth | bearer JWT or Telegram WebApp `X-Telegram-Init-Data` header |

## Feature areas

### Authentication

| Surface | Path | Source-of-truth file | Notes for KMP |
| --- | --- | --- | --- |
| Telegram login | `POST /v1/auth/telegram-login` | `app/api/routers/auth/endpoints_telegram.py` | Issues bearer + refresh; refresh cookie also set when `Origin` is web |
| Telegram WebApp linking | `POST /v1/auth/me/telegram/link`, `/complete` | same file | Mini-app OTP/2FA flow |
| Refresh | `POST /v1/auth/refresh` | `app/api/routers/auth/endpoints_sessions.py` | Single-use rotation; post [[harden-refresh-token-rotation-revocation]] follow-up, family revocation kicks in on reuse |
| Logout (current device) | `POST /v1/auth/logout` | same file | |
| Logout-all | **not implemented** | — | Tracked in [[harden-refresh-token-rotation-revocation]] follow-up |
| Session list | `GET /v1/auth/sessions` | same file | |
| Single session revoke | `DELETE /v1/auth/sessions/{session_id}` | same file | |
| Secret-login | `POST /v1/auth/secret-login` | `app/api/routers/auth/endpoints_credentials.py` | Constant-time compare via `app/api/routers/auth/credential_auth.py` |
| Secret-key CRUD | `GET/POST /v1/auth/secret-keys`, `…/rotate`, `…/revoke` | `app/api/routers/auth/endpoints_secret_keys.py` | |
| Credentials change-password | `POST /v1/auth/credentials/change-password` | `endpoints_credentials.py` | |
| Me / Telegram linkage | `GET /v1/auth/me`, `GET /v1/auth/me/telegram` | `endpoints_me.py`, `endpoints_telegram.py` | |
| GitHub OAuth / PAT | `/v1/auth/github`, `…/device/start|poll`, `…/pat` | `app/api/routers/auth/github.py` | Device-flow + PAT alt path; tokens Fernet-encrypted at rest |

### Summaries / articles

| Surface | Path | Source-of-truth file | Notes |
| --- | --- | --- | --- |
| List | `GET /v1/summaries` | `app/api/routers/content/summaries.py:162` | Now supports `search=...` (added 2026-05-17) plus `is_read`, `is_favorited`, `lang`, `start_date`, `end_date`, `sort`. Bulk endpoints + `tag`/`domain`/`collection` filters tracked in [[overhaul-articles-management]] |
| Articles alias | `GET /v1/articles…` | same router | Pure alias surface — same handlers as `/v1/summaries…` so KMP can pick whichever naming feels native to mobile UX |
| Detail | `GET /v1/summaries/{id}` | `summaries.py:289` | Full `SummaryDetail` payload (35+ fields) |
| Content body | `GET /v1/summaries/{id}/content` | `summaries.py:412` | Text/markdown/html variants |
| Export | `GET /v1/summaries/{id}/export` | `summaries.py:480` | PDF via weasyprint |
| Toggle favorite | `POST /v1/summaries/{id}/favorite` | `summaries.py:604` | |
| Reading progress | `PATCH /v1/summaries/{id}/reading-position` | `summaries.py:559` | |
| Feedback | `POST /v1/summaries/{id}/feedback` | `summaries.py:617` | |
| Soft delete | `DELETE /v1/summaries/{id}` | `summaries.py:585` | |
| Recommendations | `GET /v1/summaries/recommendations` | `summaries.py:235` | |
| Highlights | `GET/POST/DELETE /v1/summaries/{id}/highlights/…` | `app/api/routers/content/` | |

### Sync

| Surface | Path | Source-of-truth file | Notes |
| --- | --- | --- | --- |
| Session list | `GET /v1/sync/sessions` | `app/api/routers/sync.py` | Multi-device sync envelope |
| Full sync | `GET /v1/sync/full` | same | |
| Delta sync | `GET /v1/sync/delta` | same | server_version watermark |
| Apply mutation | `POST /v1/sync/apply` | same | Conflict-resolution semantics |
| Device register | `POST /v1/notifications/device` | `app/api/routers/notifications.py` | |

### Collections

| Surface | Path | Source-of-truth file | Notes |
| --- | --- | --- | --- |
| List + CRUD | `GET/POST /v1/collections`, `…/{id}` | `app/api/routers/content/` | Owner + collaborator + invite model |
| Items | `POST/DELETE /v1/collections/{id}/items/{summary_id}` | same | |
| Reorder | `POST /v1/collections/{id}/reorder`, `/items/reorder` | same | Server enforces total order |
| ACL | `GET/POST /v1/collections/{id}/acl`, `/share/…` | same | Per-collaborator role |
| Invite | `POST /v1/collections/{id}/invite`, `/invites/{token}/accept` | same | Token-based; never expose plaintext |
| Tree | `GET /v1/collections/tree` | same | Pre-rendered hierarchy |

### Search

| Surface | Path | Source-of-truth file | Notes |
| --- | --- | --- | --- |
| Full search | `POST /v1/search` (or `GET /v1/search`) | `app/api/routers/content/search.py` | Topic + lexical + vector blended |
| Repository search | `GET /v1/search/repositories` | `app/api/routers/repositories.py` | Qdrant `entity_type=repository` |
| Topics index | `GET /v1/signals/topics` | `app/api/routers/signals.py` | |

### Digest

| Surface | Path | Source-of-truth file | Notes |
| --- | --- | --- | --- |
| Custom digest CRUD | `GET/POST/DELETE /v1/digests/custom…` | `app/api/routers/digest.py` | |
| Quick-save | `POST /v1/quick-save` | `app/api/routers/quick_save.py` | |

### Signals / aggregation

| Surface | Path | Source-of-truth file | Notes |
| --- | --- | --- | --- |
| Signals stream | `GET /v1/signals` | `app/api/routers/signals.py` | |
| Source toggle | `POST /v1/signals/sources/{id}/active` | same | |
| Signal feedback | `POST /v1/signals/{id}/feedback` | same | |
| Sources / topics health | `GET /v1/signals/health`, `…/sources/health` | same | |

### Repositories (GitHub ingestion)

| Surface | Path | Source-of-truth file | Notes |
| --- | --- | --- | --- |
| List + CRUD | `GET/POST /v1/repositories`, `…/{id}` | `app/api/routers/repositories.py` | |
| Re-analyze | `POST /v1/repositories/{id}/reanalyze` | same | Triggers `app/agents/repo_analysis_agent.py` |

### Goals / streaks

| Surface | Path | Source-of-truth file | Notes |
| --- | --- | --- | --- |
| Goal CRUD | `GET/POST/DELETE /v1/user/goals…` | `app/api/routers/user.py` | |
| Streak | `GET /v1/user/streak` | same | |
| Goal progress | `GET /v1/user/goals/progress` | same | |

### Account

| Surface | Path | Source-of-truth file | Notes |
| --- | --- | --- | --- |
| Account self | `GET /v1/auth/me` | `app/api/routers/auth/endpoints_me.py` | |
| Account delete | `DELETE /v1/auth/me` (verify in spec) | same | **Verify deletion completeness** — see security review |
| Admin surfaces | `/v1/admin/users`, `/v1/admin/jobs`, `/v1/admin/metrics`, `/v1/admin/audit-log`, `/v1/admin/health/content` | `app/api/routers/admin/` | Owner-only via ALLOWED_USER_IDS |

### Misc

| Surface | Path | Source-of-truth file | Notes |
| --- | --- | --- | --- |
| Health | `GET /v1/admin/health/content`, `/v1/healthz`, `/v1/readyz` | `app/api/routers/health.py` | |
| Audio (TTS) | `GET /v1/summaries/{id}/audio` | `app/api/routers/audio.py` | ElevenLabs-backed |
| Image proxy | `GET /v1/proxy/image` | `app/api/routers/proxy.py` | |
| Notifications device | `POST /v1/notifications/device` | `app/api/routers/notifications.py` | |

## Gaps / drift to file as follow-up issues

Items to flag to the KMP client owner once the client-side half is
filled in:

1. **Logout-all** is unimplemented backend-side
   ([[harden-refresh-token-rotation-revocation]] follow-up). If
   the KMP client exposes a "Sign out everywhere" UI surface, it
   currently has no endpoint to call.
2. **Refresh-token family revocation** semantics are not yet
   live; the policy module is in `app/security/token_family_policy.py`
   awaiting endpoint wiring. KMP should not advertise the
   "stolen-device protection" property until that wiring lands.
3. **Server-side `signal_score` field** on `SummaryCompact` is
   not yet present; only `confidence` exists. If the KMP UI uses
   a separate signal-score axis, file a backend follow-up with
   the precise formula (per [[overhaul-articles-management]]
   audit note).
4. **Account deletion completeness** — verify the cascade covers
   RefreshToken family, AuditLog redaction, Summary backrefs,
   Qdrant points. Flag in
   `docs/security/2026-05-17-mobile-auth-storage-review.md`.
5. **TLS pinning policy**, **secret show-once strategy**, and
   **`clearSavedCredentials` UX default** are CTO decisions in
   `docs/decisions/2026-05-17-auth-security-second-wave.md`; the
   KMP client should not implement a default for any of these
   until the decisions are recorded.

## Security / privacy notes per task spec

- Bearer tokens are issued by `app/api/routers/auth/tokens.py`;
  HS256-signed with `JWT_SECRET_KEY` env (one of the globals
  remaining in [[eliminate-module-globals]]).
- Refresh-token storage: hashed in DB (`RefreshToken.token_hash`);
  cookie-mode for web origin only; bearer-mode response field for
  native clients.
- Secret-keys at rest: hashed (PHC); decoy PHC stored as module
  constant to keep timing-safe-compare independent of registered
  users.
- GitHub OAuth / PAT tokens: Fernet-encrypted at rest via
  `app/security/token_crypto.py`.
- Telegram WebApp init-data: validated server-side every request;
  no caching of the verified payload across requests.

## Owner

CTO sign-off required before this file plus the ratatoskr-client
half are considered the contract baseline for the mobile release
gate.
