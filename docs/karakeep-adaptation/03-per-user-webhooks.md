# Per-User Webhook Subscriptions

**Status:** Partial (system-wide only)
**Complexity:** Small
**Dependencies:** EventBus (existing)

## Problem Statement

BSR has a system-wide webhook handler (`app/infrastructure/messaging/handlers/webhook.py`) that POSTs to a single configured URL. There is no per-user webhook management, event filtering, or delivery tracking. Karakeep provides per-user webhook subscriptions with event selection, HMAC signing, retry logic, and delivery history.

## Current State

The existing `WebhookEventHandler` in `app/infrastructure/messaging/handlers/webhook.py`:

- Listens for events on the EventBus
- POSTs to a single URL from environment variable
- Supports event types: `summary.created`, `request.completed`, `request.failed`
- No HMAC signing, no retry, no delivery tracking

## Data Model

New models in `app/db/models.py`:

```python
class WebhookSubscription(BaseModel):
    """Per-user webhook endpoint subscription."""
    id = peewee.AutoField()
    user = peewee.ForeignKeyField(User, backref="webhooks", on_delete="CASCADE")
    name = peewee.TextField(null=True)          # human-readable label
    url = peewee.TextField()                     # delivery endpoint
    secret = peewee.TextField()                  # HMAC-SHA256 signing key
    events_json = JSONField(default=list)         # list of subscribed event types
    enabled = peewee.BooleanField(default=True)
    status = peewee.TextField(default="active")  # active | paused | disabled
    failure_count = peewee.IntegerField(default=0)
    last_delivery_at = peewee.DateTimeField(null=True)
    server_version = peewee.BigIntegerField(default=_next_server_version)
    is_deleted = peewee.BooleanField(default=False)
    deleted_at = peewee.DateTimeField(null=True)
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "webhook_subscriptions"
        indexes = (
            (("user", "enabled"), False),
        )


class WebhookDelivery(BaseModel):
    """Delivery attempt log for a webhook."""
    id = peewee.AutoField()
    subscription = peewee.ForeignKeyField(
        WebhookSubscription, backref="deliveries", on_delete="CASCADE"
    )
    event_type = peewee.TextField()
    payload_json = JSONField()
    response_status = peewee.IntegerField(null=True)
    response_body = peewee.TextField(null=True)   # truncated to 1KB
    duration_ms = peewee.IntegerField(null=True)
    success = peewee.BooleanField()
    attempt = peewee.IntegerField(default=1)       # retry attempt number
    error = peewee.TextField(null=True)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "webhook_deliveries"
        indexes = (
            (("subscription",), False),
            (("created_at",), False),
        )
```

## Event Types

| Event | Payload Contains |
|-------|-----------------|
| `summary.created` | Summary ID, title, URL, tags, language |
| `summary.updated` | Summary ID, changed fields |
| `request.completed` | Request ID, summary ID, URL, processing time |
| `request.failed` | Request ID, URL, error type, error message |
| `tag.attached` | Summary ID, tag name, source |
| `tag.detached` | Summary ID, tag name |
| `collection.item_added` | Collection ID, summary ID |
| `collection.item_removed` | Collection ID, summary ID |

## Delivery Contract

### Request Format

```http
POST {subscription.url}
Content-Type: application/json
X-BSR-Signature: sha256={hmac_hex}
X-BSR-Event: summary.created
X-BSR-Delivery-Id: {delivery.id}
X-BSR-Timestamp: {unix_timestamp}

{
    "event": "summary.created",
    "timestamp": "2026-03-21T10:30:00Z",
    "data": { ... }
}
```

### HMAC Signing

```python
import hmac, hashlib

signature = hmac.new(
    subscription.secret.encode(),
    payload_bytes,
    hashlib.sha256
).hexdigest()
```

### Retry Policy

- 3 attempts total (1 initial + 2 retries)
- Backoff: 10s, 60s
- After 10 consecutive failures across any deliveries: set `status="disabled"`
- Users can re-enable disabled subscriptions via API

### Timeout

- 10 second connection timeout
- 30 second read timeout

## Architecture

### Delivery Flow

```
EventBus event (e.g., summary.created)
  -> WebhookDispatcher.on_event(event)
    -> Query WebhookSubscription WHERE user_id=event.user_id AND enabled=True
    -> Filter subscriptions where event_type in events_json
    -> For each matching subscription:
      -> Build payload
      -> Sign with HMAC-SHA256
      -> POST to subscription.url (async httpx)
      -> Log to WebhookDelivery
      -> On failure: schedule retry via APScheduler
      -> On 10 consecutive failures: disable subscription
```

### Key Files

- `app/infrastructure/messaging/handlers/webhook_dispatcher.py` -- new handler replacing/extending existing `webhook.py`
- `app/domain/services/webhook_service.py` -- HMAC signing, payload building
- `app/api/routers/webhooks.py` -- API router

### Migration from System Webhook

The existing system-wide webhook continues to work. Per-user webhooks are additive. If `WEBHOOK_URL` env var is set, it acts as a system-wide catch-all alongside per-user subscriptions.

## API Endpoints

New router: `app/api/routers/webhooks.py`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/webhooks` | List user's webhook subscriptions |
| `POST` | `/v1/webhooks` | Create subscription. Body: `{ name?, url, events }`. Secret auto-generated and returned once. |
| `GET` | `/v1/webhooks/{id}` | Get subscription details (secret masked) |
| `PATCH` | `/v1/webhooks/{id}` | Update name/url/events/enabled |
| `DELETE` | `/v1/webhooks/{id}` | Soft-delete subscription |
| `POST` | `/v1/webhooks/{id}/test` | Send test event to verify endpoint |
| `GET` | `/v1/webhooks/{id}/deliveries` | Paginated delivery history |
| `POST` | `/v1/webhooks/{id}/rotate-secret` | Generate new secret (returns once) |

### Security Validation

- URL must use HTTPS (except localhost for development)
- URL must not resolve to private/internal IPs (prevent SSRF)
- Max 10 subscriptions per user
- Rate limit: max 1000 deliveries per hour per user

## Frontend (React + Carbon)

### New Components

- **WebhooksPage** (`web/src/features/webhooks/WebhooksPage.tsx`) -- subscription list with status indicators
- **WebhookEditor** (`web/src/features/webhooks/WebhookEditor.tsx`) -- create/edit form with event checkboxes
- **WebhookDeliveryLog** (`web/src/features/webhooks/WebhookDeliveryLog.tsx`) -- Carbon `DataTable` with status, response code, duration

### Route

Add `/web/webhooks` route under settings/preferences section.

## Telegram Bot Integration

Minimal -- webhook management is API/web only. Telegram provides:

- `/webhooks` -- list active subscriptions with delivery stats
- Webhook creation/editing -- redirect to web UI

## Testing

- Unit tests for HMAC signature generation and verification
- Integration test: create subscription, trigger event, verify delivery logged
- Retry test: mock failed delivery, verify retry scheduling
- Auto-disable test: simulate 10 consecutive failures, verify status changes
- SSRF validation test: verify private IP rejection
