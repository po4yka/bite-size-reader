# First Mobile API Client Tutorial

Build a simple mobile client for Bite-Size Reader using the REST API.

**Time:** ~30 minutes
**Difficulty:** Intermediate
**Prerequisites:** Python 3.8+ or JavaScript/Node.js 16+

---

## What You'll Learn

By the end of this tutorial, you'll have:

- ✅ Authenticated via Telegram login exchange
- ✅ Obtained and managed JWT tokens
- ✅ Fetched summaries from the API
- ✅ Implemented basic sync functionality
- ✅ Working sample client in Python or JavaScript

---

## Prerequisites

### 1. Bite-Size Reader Mobile API Running

```bash
# Verify API is running
curl http://localhost:8000/health

# Expected response:
# {"status":"healthy","version":"1.0.0"}
```

If not running, see [DEPLOYMENT.md](../DEPLOYMENT.md) for setup.

### 2. Required Environment Variables

Ensure these are set in your `.env`:

```bash
# Mobile API
JWT_SECRET_KEY=your_secret_key_here  # 32+ random characters
API_RATE_LIMIT_PER_MINUTE=100

# Telegram (for login exchange)
BOT_TOKEN=your_bot_token
ALLOWED_USER_IDS=your_user_id
```

### 3. Development Tools

**Python:**

```bash
pip install httpx pyjwt
```

**JavaScript:**

```bash
npm install axios jsonwebtoken
```

---

## Step 1: Telegram Login Exchange (Get Auth Token)

The Mobile API uses Telegram as the identity provider. Users authenticate by messaging the bot.

### How It Works

1. User messages bot: `/mobile_login`
2. Bot generates one-time auth token (valid 5 minutes)
3. Bot sends token to user via Telegram
4. Client exchanges token for JWT

### Get Auth Token

**Via Telegram:**

```
/mobile_login
```

**Bot response:**

```
🔐 Mobile API Login Token

Token: 1a2b3c4d5e6f7g8h9i0j

Use this token to authenticate your mobile client.
Expires in 5 minutes.

curl -X POST http://localhost:8000/v1/auth/telegram-login \
  -H "Content-Type: application/json" \
  -d '{"telegram_user_id": 123456789, "telegram_auth_token": "1a2b3c4d5e6f7g8h9i0j"}'
```

---

## Step 2: Exchange Token for JWT (Python)

Create `client.py`:

```python
import httpx
from typing import Optional

API_BASE_URL = "http://localhost:8000/v1"

class BiteSizeClient:
    def __init__(self, base_url: str = API_BASE_URL):
        self.base_url = base_url
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.client = httpx.Client(base_url=base_url)

    def login(self, telegram_user_id: int, telegram_auth_token: str) -> dict:
        """Exchange Telegram auth token for JWT tokens."""
        response = self.client.post(
            "/auth/telegram-login",
            json={
                "telegram_user_id": telegram_user_id,
                "telegram_auth_token": telegram_auth_token
            }
        )
        response.raise_for_status()
        data = response.json()

        # Store tokens
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]

        return data

    def _get_headers(self) -> dict:
        """Get headers with authorization."""
        if not self.access_token:
            raise ValueError("Not logged in. Call login() first.")
        return {"Authorization": f"Bearer {self.access_token}"}

# Usage
client = BiteSizeClient()

# Replace with your values from /mobile_login
telegram_user_id = 123456789
auth_token = "1a2b3c4d5e6f7g8h9i0j"

# Login
tokens = client.login(telegram_user_id, auth_token)
print(f"Logged in! Access token expires in {tokens['expires_in']}s")
```

---

## Step 2: Exchange Token for JWT (JavaScript)

Create `client.js`:

```javascript
const axios = require('axios');

const API_BASE_URL = 'http://localhost:8000/v1';

class BiteSizeClient {
    constructor(baseUrl = API_BASE_URL) {
        this.baseUrl = baseUrl;
        this.accessToken = null;
        this.refreshToken = null;
        this.client = axios.create({ baseURL: baseUrl });
    }

    async login(telegramUserId, telegramAuthToken) {
        const response = await this.client.post('/auth/telegram-login', {
            telegram_user_id: telegramUserId,
            telegram_auth_token: telegramAuthToken
        });

        // Store tokens
        this.accessToken = response.data.access_token;
        this.refreshToken = response.data.refresh_token;

        return response.data;
    }

    _getHeaders() {
        if (!this.accessToken) {
            throw new Error('Not logged in. Call login() first.');
        }
        return { Authorization: `Bearer ${this.accessToken}` };
    }
}

// Usage
const client = new BiteSizeClient();

// Replace with your values from /mobile_login
const telegramUserId = 123456789;
const authToken = '1a2b3c4d5e6f7g8h9i0j';

// Login
client.login(telegramUserId, authToken)
    .then(tokens => {
        console.log(`Logged in! Access token expires in ${tokens.expires_in}s`);
    })
    .catch(error => {
        console.error('Login failed:', error.response?.data || error.message);
    });
```

---

## Step 3: Fetch Summaries (Python)

Add to `client.py`:

```python
def get_summaries(
    self,
    limit: int = 20,
    offset: int = 0,
    topic: Optional[str] = None
) -> dict:
    """Fetch summaries from API."""
    params = {"limit": limit, "offset": offset}
    if topic:
        params["topic"] = topic

    response = self.client.get(
        "/summaries",
        headers=self._get_headers(),
        params=params
    )
    response.raise_for_status()
    return response.json()

# Usage
summaries = client.get_summaries(limit=10)
print(f"Fetched {len(summaries['items'])} summaries")

for summary in summaries['items']:
    print(f"- {summary['title']}")
    print(f"  URL: {summary['url']}")
    print(f"  TLDR: {summary['tldr']}")
    print()
```

---

## Step 3: Fetch Summaries (JavaScript)

Add to `client.js`:

```javascript
async getSummaries(limit = 20, offset = 0, topic = null) {
    const params = { limit, offset };
    if (topic) params.topic = topic;

    const response = await this.client.get('/summaries', {
        headers: this._getHeaders(),
        params
    });

    return response.data;
}

// Usage
client.getSummaries(10)
    .then(summaries => {
        console.log(`Fetched ${summaries.items.length} summaries`);

        summaries.items.forEach(summary => {
            console.log(`- ${summary.title}`);
            console.log(`  URL: ${summary.url}`);
            console.log(`  TLDR: ${summary.tldr}`);
            console.log();
        });
    });
```

---

## Step 4: Get Single Summary (Python)

```python
def get_summary(self, request_id: str) -> dict:
    """Fetch single summary by request ID."""
    response = self.client.get(
        f"/summaries/{request_id}",
        headers=self._get_headers()
    )
    response.raise_for_status()
    return response.json()

# Usage
request_id = "a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6"
summary = client.get_summary(request_id)

print(f"Title: {summary['title']}")
print(f"Summary (250 chars): {summary['summary_250']}")
print(f"Key Ideas: {', '.join(summary['key_ideas'])}")
```

---

## Step 4: Get Single Summary (JavaScript)

```javascript
async getSummary(requestId) {
    const response = await this.client.get(`/summaries/${requestId}`, {
        headers: this._getHeaders()
    });
    return response.data;
}

// Usage
const requestId = 'a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6';
client.getSummary(requestId)
    .then(summary => {
        console.log(`Title: ${summary.title}`);
        console.log(`Summary (250 chars): ${summary.summary_250}`);
        console.log(`Key Ideas: ${summary.key_ideas.join(', ')}`);
    });
```

---

## Step 5: Implement Sync (Python)

```python
def sync_summaries(
    self,
    last_sync_timestamp: Optional[str] = None,
    mode: str = "delta"
) -> dict:
    """Sync summaries (delta or full)."""
    params = {"mode": mode}
    if last_sync_timestamp:
        params["last_sync_timestamp"] = last_sync_timestamp

    response = self.client.post(
        "/sync/summaries",
        headers=self._get_headers(),
        params=params
    )
    response.raise_for_status()
    return response.json()

# Usage - Initial sync (full)
sync_result = client.sync_summaries(mode="full")
print(f"Synced {len(sync_result['added'])} summaries")
print(f"Sync timestamp: {sync_result['sync_timestamp']}")

# Save sync timestamp for next delta sync
last_sync = sync_result['sync_timestamp']

# Later - Delta sync (only changes)
delta = client.sync_summaries(last_sync_timestamp=last_sync, mode="delta")
print(f"New: {len(delta['added'])}, Modified: {len(delta['modified'])}, Deleted: {len(delta['deleted'])}")
```

---

## Step 5: Implement Sync (JavaScript)

```javascript
async syncSummaries(lastSyncTimestamp = null, mode = 'delta') {
    const params = { mode };
    if (lastSyncTimestamp) {
        params.last_sync_timestamp = lastSyncTimestamp;
    }

    const response = await this.client.post('/sync/summaries', null, {
        headers: this._getHeaders(),
        params
    });

    return response.data;
}

// Usage - Initial sync (full)
client.syncSummaries(null, 'full')
    .then(syncResult => {
        console.log(`Synced ${syncResult.added.length} summaries`);
        console.log(`Sync timestamp: ${syncResult.sync_timestamp}`);

        // Save for next delta sync
        const lastSync = syncResult.sync_timestamp;

        // Later - Delta sync
        return client.syncSummaries(lastSync, 'delta');
    })
    .then(delta => {
        console.log(`New: ${delta.added.length}, Modified: ${delta.modified.length}, Deleted: ${delta.deleted.length}`);
    });
```

---

## Step 6: Refresh Access Token (Python)

Access tokens expire after 1 hour. Use refresh token to get new access token.

```python
def refresh_access_token(self) -> dict:
    """Refresh access token using refresh token."""
    if not self.refresh_token:
        raise ValueError("No refresh token available")

    response = self.client.post(
        "/auth/refresh",
        json={"refresh_token": self.refresh_token}
    )
    response.raise_for_status()
    data = response.json()

    # Update access token
    self.access_token = data["access_token"]

    return data

# Usage
try:
    summaries = client.get_summaries()
except httpx.HTTPStatusError as e:
    if e.response.status_code == 401:
        # Token expired, refresh
        client.refresh_access_token()
        summaries = client.get_summaries()
    else:
        raise
```

---

## Step 6: Refresh Access Token (JavaScript)

```javascript
async refreshAccessToken() {
    if (!this.refreshToken) {
        throw new Error('No refresh token available');
    }

    const response = await this.client.post('/auth/refresh', {
        refresh_token: this.refreshToken
    });

    // Update access token
    this.accessToken = response.data.access_token;

    return response.data;
}

// Usage with automatic retry
async getSummariesWithRefresh() {
    try {
        return await this.getSummaries();
    } catch (error) {
        if (error.response?.status === 401) {
            // Token expired, refresh and retry
            await this.refreshAccessToken();
            return await this.getSummaries();
        }
        throw error;
    }
}
```

---

## Complete Example (Python)

`complete_client.py`:

```python
import httpx
from typing import Optional
from datetime import datetime

class BiteSizeClient:
    def __init__(self, base_url: str = "http://localhost:8000/v1"):
        self.base_url = base_url
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.client = httpx.Client(base_url=base_url, timeout=30.0)

    def login(self, telegram_user_id: int, telegram_auth_token: str) -> dict:
        """Exchange Telegram auth token for JWT tokens."""
        response = self.client.post(
            "/auth/telegram-login",
            json={
                "telegram_user_id": telegram_user_id,
                "telegram_auth_token": telegram_auth_token
            }
        )
        response.raise_for_status()
        data = response.json()
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        return data

    def refresh_access_token(self) -> dict:
        """Refresh access token."""
        response = self.client.post(
            "/auth/refresh",
            json={"refresh_token": self.refresh_token}
        )
        response.raise_for_status()
        data = response.json()
        self.access_token = data["access_token"]
        return data

    def _get_headers(self) -> dict:
        if not self.access_token:
            raise ValueError("Not logged in")
        return {"Authorization": f"Bearer {self.access_token}"}

    def _request_with_auth_retry(self, method: str, endpoint: str, **kwargs):
        """Make request with automatic token refresh on 401."""
        try:
            response = self.client.request(
                method, endpoint, headers=self._get_headers(), **kwargs
            )
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401 and self.refresh_token:
                # Token expired, refresh and retry
                self.refresh_access_token()
                response = self.client.request(
                    method, endpoint, headers=self._get_headers(), **kwargs
                )
                response.raise_for_status()
                return response
            raise

    def get_summaries(self, limit: int = 20, offset: int = 0, topic: Optional[str] = None) -> dict:
        params = {"limit": limit, "offset": offset}
        if topic:
            params["topic"] = topic
        return self._request_with_auth_retry("GET", "/summaries", params=params).json()

    def get_summary(self, request_id: str) -> dict:
        return self._request_with_auth_retry("GET", f"/summaries/{request_id}").json()

    def sync_summaries(self, last_sync_timestamp: Optional[str] = None, mode: str = "delta") -> dict:
        params = {"mode": mode}
        if last_sync_timestamp:
            params["last_sync_timestamp"] = last_sync_timestamp
        return self._request_with_auth_retry("POST", "/sync/summaries", params=params).json()

    def close(self):
        self.client.close()

# Example usage
if __name__ == "__main__":
    client = BiteSizeClient()

    # Login
    telegram_user_id = 123456789
    auth_token = "1a2b3c4d5e6f7g8h9i0j"
    client.login(telegram_user_id, auth_token)
    print("✅ Logged in")

    # Fetch summaries
    summaries = client.get_summaries(limit=5)
    print(f"📚 Fetched {len(summaries['items'])} summaries")

    for summary in summaries['items']:
        print(f"\n📄 {summary['title']}")
        print(f"   {summary['tldr']}")

    # Sync
    sync_result = client.sync_summaries(mode="full")
    print(f"\n🔄 Synced {len(sync_result['added'])} summaries")

    client.close()
```

---

## Testing Your Client

```bash
# Python
python complete_client.py

# Expected output:
# ✅ Logged in
# 📚 Fetched 5 summaries
#
# 📄 Example Article Title
#    Short summary of the article...
# ...
# 🔄 Synced 150 summaries
```

---

## Error Handling

### Common Errors

**401 Unauthorized:**

```python
# Token expired or invalid
# Solution: Refresh token or re-login
```

**429 Too Many Requests:**

```python
# Rate limit exceeded
# Solution: Implement exponential backoff
import time

for attempt in range(3):
    try:
        summaries = client.get_summaries()
        break
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            wait = 2 ** attempt  # 1s, 2s, 4s
            time.sleep(wait)
        else:
            raise
```

**500 Internal Server Error:**

```python
# Server error
# Check API logs: docker logs bite-size-reader
```

---

## Next Steps

**Extend the client:**

- Add search functionality (`GET /summaries/search?q=query`)
- Implement collections (`GET /collections`, `POST /collections`)
- Add offline support (cache summaries locally)
- Handle sync conflicts (compare timestamps)

**Build a UI:**

- React Native app
- Flutter app
- Swift iOS app
- Kotlin Android app

**See full API spec:** [MOBILE_API_SPEC.md](../MOBILE_API_SPEC.md)

---

## See Also

- [MOBILE_API_SPEC.md](../MOBILE_API_SPEC.md) - Complete API reference
- [FAQ § Integration](../FAQ.md#integration) - Integration questions
- [TROUBLESHOOTING § Mobile API](../TROUBLESHOOTING.md#mobile-api-issues)

---

**Last Updated:** 2026-02-09
