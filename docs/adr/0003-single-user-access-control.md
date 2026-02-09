# ADR-0003: Single-User Access Control Model

**Date:** 2024-12-20

**Status:** Accepted

**Deciders:** po4yka

**Technical Story:** Define access control and multi-tenancy strategy

## Context

Bite-Size Reader needs to control who can use the Telegram bot and access summaries. As a personal productivity tool with API costs (Firecrawl, OpenRouter), we need to prevent:

1. **Unauthorized Usage**: Random Telegram users discovering and spamming the bot
2. **API Cost Abuse**: Each summary costs $0.02-0.05 (Firecrawl + LLM), uncontrolled access = unbounded costs
3. **Data Privacy**: Summaries may contain sensitive links (internal docs, private articles)
4. **Rate Limit Exhaustion**: Free tier limits (Firecrawl: 500/month) could be consumed by others

Traditional approaches for bots:

- **Public Bots**: Anyone can use (requires abuse prevention, rate limiting, moderation)
- **Private Bots**: Invitation-only with user management (registration, permissions, roles)
- **Single-User Bots**: Hardcoded owner ID, zero multi-tenancy

Key constraints:

- **Single Owner**: Built for personal use, not multi-user SaaS
- **Zero Admin UI**: No desire to build user management interface
- **Static Configuration**: Acceptable to redeploy for access changes
- **API Cost Control**: Must guarantee zero spend from unauthorized users

## Decision

We will implement a **single-user access control model** with:

- **Hardcoded Whitelist**: `ALLOWED_USER_IDS` environment variable (comma-separated Telegram user IDs)
- **Pre-Handler Rejection**: All messages from non-whitelisted users rejected before processing
- **Zero Multi-Tenancy**: Database stores data globally, no user-specific isolation
- **Mobile API Extension**: JWT authentication for mobile app tied to same `ALLOWED_USER_IDS`

**Implementation**: `app/adapters/telegram/access_controller.py` checks user ID against whitelist for every message.

## Consequences

### Positive

- **Zero Cost Risk**: Impossible for unauthorized users to trigger API calls
- **Zero Complexity**: No user registration, password resets, roles, or permissions
- **Zero Attack Surface**: No authentication flows to exploit (SQL injection, session hijacking, etc.)
- **Instant Access Revocation**: Remove user ID from env var, restart container
- **Perfect Privacy**: No data leakage between users (only one user exists)
- **Deployment Simplicity**: No database migrations for user tables, no OAuth setup

### Negative

- **No Self-Service**: Owner must manually add collaborators to `ALLOWED_USER_IDS`
- **No Granular Permissions**: All whitelisted users have full access (can't do read-only)
- **Restart Required**: Adding new users requires container restart
- **Not SaaS-Ready**: Would require complete rewrite for multi-tenancy
- **No Audit Trail per User**: All actions logged globally, can't filter by user easily

### Neutral

- Mobile API uses JWT tokens, but tokens are issued only to `ALLOWED_USER_IDS` users
- Database has `user_id` fields for future extensibility, but not used for access control
- Suitable for personal use and small teams (1-5 users), not for public deployment

## Alternatives Considered

### Alternative 1: Invitation-Based Registration

Build user registration flow with invitation codes and database-backed user management.

**Pros:**

- Self-service onboarding (users request access, owner approves)
- Granular permissions (admin vs read-only roles)
- Revocation without restart (disable user in database)
- Audit trail per user

**Cons:**

- **High Complexity**: Need registration, login, password reset, session management
- **Database Schema**: Add `users`, `sessions`, `invitations` tables
- **Security Overhead**: Implement bcrypt, JWT refresh tokens, CSRF protection
- **Development Time**: 1-2 weeks of work for MVP
- **Maintenance**: Ongoing security patches, password reset emails, etc.

**Why not chosen**: 10x complexity for a single-user tool. Not worth the effort.

### Alternative 2: OAuth Integration (Telegram Login)

Use Telegram Login Widget for web-based authentication.

**Pros:**

- No password management (delegated to Telegram)
- Familiar UX for Telegram users
- Secure authentication (Telegram handles it)

**Cons:**

- **Web Interface Required**: Need to build web UI for OAuth callback
- **Session Management**: Still need JWT tokens, refresh logic, expiration
- **Overkill**: Telegram bot already knows user ID directly
- **Mobile App Complication**: OAuth on mobile requires WebView

**Why not chosen**: Telegram bot already has user ID. Adding OAuth is unnecessary indirection.

### Alternative 3: API Key Per User

Generate unique API keys for each user, store in database.

**Pros:**

- No restart required for new users (generate key on-the-fly)
- Key revocation without redeployment
- Audit trail (track usage per key)

**Cons:**

- **Complexity**: Need API key generation, storage, validation
- **Security**: Need to hash keys, handle rotation, prevent leakage
- **User Education**: Users must learn to manage API keys
- **Still Need Whitelist**: Telegram bot messages don't include API keys

**Why not chosen**: Doesn't solve Telegram bot access control. API keys only useful for HTTP API, not Pyrogram.

### Alternative 4: Public Bot with Rate Limiting

Allow anyone to use bot, but enforce aggressive rate limiting per user.

**Pros:**

- Zero configuration (fully public)
- Good for building user base
- Rate limiting prevents cost abuse

**Cons:**

- **Cost Risk**: Even rate-limited usage adds up (1000 users × 10 summaries/month = $500/month)
- **Spam Management**: Need to handle abuse, offensive content, API quotas
- **Privacy Risk**: All summaries visible to users (can't share private links)
- **Moderation Burden**: Need to monitor for abuse, block bad actors

**Why not chosen**: Defeats the purpose of a personal productivity tool. Opens cost and privacy risks.

## Decision Criteria

1. **Cost Control** (High): Must prevent unauthorized API spending
2. **Development Effort** (High): Should minimize code complexity
3. **Deployment Simplicity** (High): Should be easy to self-host
4. **Security** (Medium): Should have minimal attack surface
5. **Flexibility** (Low): Multi-user features not a priority

Single-user access control scored highest on cost control, development effort, and simplicity.

## Related Decisions

- Mobile API JWT authentication (`app/api/routers/auth.py`) validates against same `ALLOWED_USER_IDS`
- No decision to migrate to multi-tenancy planned (not a priority)

## Implementation Notes

- **Code**: `app/adapters/telegram/access_controller.py` (`AccessController` class)
- **Configuration**: `ALLOWED_USER_IDS=123456789,987654321` (comma-separated)
- **Validation**: Every message passes through `is_user_allowed()` before routing
- **Rejection Message**: Non-whitelisted users receive "Access denied" with bot owner contact info
- **Logging**: All access denials logged with user ID and correlation ID

**Finding Your Telegram User ID**:

1. Message `@userinfobot` on Telegram
2. Copy the numeric ID
3. Add to `ALLOWED_USER_IDS` environment variable
4. Restart container

**Mobile API Access**: Same users, JWT tokens issued only to `ALLOWED_USER_IDS`.

## Notes

**2025-01-28**: Added support for multiple whitelisted users (previously single user). Useful for family sharing.

**2025-02-08**: Mobile API JWT authentication successfully integrated with whitelist. No changes to access model required.

---

### Update Log

| Date | Author | Change |
|------|--------|--------|
| 2024-12-20 | po4yka | Initial decision (Accepted) |
| 2025-01-28 | po4yka | Added multi-user whitelist support |
| 2025-02-08 | po4yka | Mobile API integration note |
