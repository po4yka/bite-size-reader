# Mobile API - Quick Start Guide

This guide helps you get the Mobile API up and running for the Bite-Size Reader Android app.

## Overview

The Mobile API is a RESTful API built with FastAPI that provides:
- **Summary retrieval** - Get all your article summaries
- **Request submission** - Submit new URLs for processing
- **Search** - Full-text search across summaries
- **Database sync** - Sync entire database to mobile device
- **Authentication** - JWT-based auth with Telegram login

### What Changed (2025-12-07)
- OpenAPI `/v1` spec now defines typed envelopes for all success responses and standardized `ErrorResponse` for 401/403/404/409/410/422/429/500 with correlation IDs.
- Added concrete schemas for summaries, requests/status, search pagination, duplicate checks, user preferences/stats, and sync (session/full/delta/apply with conflicts).
- Servers block documents production/staging/local URLs; array query params are encoded as repeated keys (e.g., `tags=ai&tags=travel`).

## Quick Start

### 1. Install Dependencies

```bash
pip install fastapi uvicorn pyjwt python-multipart
```

Or add to `requirements.txt`:
```
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
pyjwt>=2.8.0
python-multipart>=0.0.6
```

### 2. Configure Environment

Add to your `.env`:

```bash
# JWT Secret (generate with: openssl rand -hex 32)
JWT_SECRET_KEY=your-secret-key-here

# API Host/Port
API_HOST=0.0.0.0
API_PORT=8000
```

### 3. Run the API Server

```bash
# Development mode (with auto-reload)
uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000

# Production mode
uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 4. Test the API

Visit the auto-generated documentation:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

## API Endpoints

### Authentication

#### POST `/v1/auth/telegram-login`
Login with Telegram credentials.

**Request:**
```json
{
  "telegram_user_id": 123456789,
  "auth_hash": "abc123...",
  "timestamp": 1700000000,
  "username": "johndoe"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGc...",
    "refresh_token": "eyJhbGc...",
    "expires_in": 3600,
    "token_type": "Bearer"
  }
}
```

#### POST `/v1/auth/refresh`
Refresh an expired access token.

**Request:**
```json
{
  "refresh_token": "eyJhbGc..."
}
```

### Summaries

#### GET `/v1/summaries`
Get paginated list of summaries.

**Query Parameters:**
- `limit` (int, default=20)
- `offset` (int, default=0)
- `is_read` (bool, optional)
- `lang` (string: en/ru/auto)

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response:**
```json
{
  "success": true,
  "data": {
    "summaries": [...],
    "pagination": {
      "total": 247,
      "limit": 20,
      "offset": 0,
      "has_more": true
    },
    "stats": {
      "total_summaries": 247,
      "unread_count": 42
    }
  }
}
```

#### GET `/v1/summaries/{summary_id}`
Get full summary details.

#### PATCH `/v1/summaries/{summary_id}`
Update summary (e.g., mark as read).

**Request:**
```json
{
  "is_read": true
}
```

### Requests

#### POST `/v1/requests`
Submit new URL for processing.

**Request:**
```json
{
  "type": "url",
  "input_url": "https://example.com/article",
  "lang_preference": "auto"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "request_id": 100,
    "correlation_id": "req-abc123",
    "status": "pending",
    "estimated_wait_seconds": 15
  }
}
```

#### GET `/v1/requests/{request_id}/status`
Poll for processing status.

### Search

#### GET `/v1/search?q=blockchain`
Full-text search across summaries.

**Query Parameters:**
- `q` (string, required) - Search query
- `limit` (int, default=20)
- `offset` (int, default=0)

### Sync

#### GET `/v1/sync/full`
Initiate full database sync.

#### GET `/v1/sync/delta?since=2025-11-15T00:00:00Z`
Get incremental updates.

#### POST `/v1/sync/upload-changes`
Upload local changes to server.

### User

#### GET `/v1/user/stats`
Get user statistics.

#### GET `/v1/user/preferences`
Get user preferences.

## Testing with cURL

### 1. Login

```bash
curl -X POST http://localhost:8000/v1/auth/telegram-login \
  -H "Content-Type: application/json" \
  -d '{
    "telegram_user_id": 123456789,
    "auth_hash": "test-hash",
    "timestamp": 1700000000,
    "username": "testuser"
  }'
```

Save the `access_token` from the response.

### 2. Get Summaries

```bash
curl -X GET "http://localhost:8000/v1/summaries?limit=10" \
  -H "Authorization: Bearer <access_token>"
```

### 3. Submit URL

```bash
curl -X POST http://localhost:8000/v1/requests \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "url",
    "input_url": "https://example.com/article",
    "lang_preference": "auto"
  }'
```

### 4. Check Status

```bash
curl -X GET http://localhost:8000/v1/requests/100/status \
  -H "Authorization: Bearer <access_token>"
```

## Testing with Python

```python
import httpx

BASE_URL = "http://localhost:8000/v1"

# Login
response = httpx.post(
    f"{BASE_URL}/auth/telegram-login",
    json={
        "telegram_user_id": 123456789,
        "auth_hash": "test-hash",
        "timestamp": 1700000000,
        "username": "testuser"
    }
)
access_token = response.json()["data"]["access_token"]

# Get summaries
headers = {"Authorization": f"Bearer {access_token}"}
response = httpx.get(f"{BASE_URL}/summaries", headers=headers)
print(response.json())
```

## Architecture

```
FastAPI App
    ├── Routers (endpoints)
    │   ├── auth.py         - Authentication
    │   ├── summaries.py    - Summary CRUD
    │   ├── requests.py     - Request submission
    │   ├── search.py       - Search & discovery
    │   ├── sync.py         - Database sync
    │   └── user.py         - User preferences
    │
    ├── Middleware
    │   ├── correlation_id_middleware  - Request tracing
    │   └── rate_limit_middleware      - Rate limiting
    │
    ├── Models (Pydantic)
    │   ├── requests.py     - Request validation
    │   └── responses.py    - Response models
    │
    └── Database (Peewee ORM)
        └── Existing models in app/db/models.py
```

## Production Deployment

### Docker

Create `Dockerfile.api`:

```dockerfile
FROM python:3.13-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY app/ app/

# Expose port
EXPOSE 8000

# Run with Uvicorn
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

Build and run:

```bash
docker build -f Dockerfile.api -t bite-reader-api .
docker run -p 8000:8000 --env-file .env -v $(pwd)/data:/data bite-reader-api
```

### Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name bitsizereaderapi.po4yka.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Correlation-ID $request_id;
    }
}
```

### Systemd Service

Create `/etc/systemd/system/bite-reader-api.service`:

```ini
[Unit]
Description=Bite-Size Reader API
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/bite-size-reader
Environment="PATH=/opt/bite-size-reader/.venv/bin"
EnvironmentFile=/opt/bite-size-reader/.env
ExecStart=/opt/bite-size-reader/.venv/bin/uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --workers 4

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable bite-reader-api
sudo systemctl start bite-reader-api
sudo systemctl status bite-reader-api
```

## Security Considerations

### 1. JWT Secret

Generate a strong secret:

```bash
openssl rand -hex 32
```

Add to `.env`:
```
JWT_SECRET_KEY=<generated-secret>
```

### 2. CORS Configuration

Update `app/api/main.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-mobile-app.com"],  # Specific origins
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Correlation-ID"],
)
```

### 3. HTTPS Only

In production, always use HTTPS:
- Use Nginx with SSL/TLS certificates (Let's Encrypt)
- Enable HSTS headers
- Redirect HTTP to HTTPS

### 4. Rate Limiting

The API includes basic in-memory rate limiting. For production:

**Use Redis:**

```python
from redis import Redis
from fastapi_limiter import FastAPILimiter

@app.on_event("startup")
async def startup():
    redis = Redis(host="localhost", port=6379, decode_responses=True)
    await FastAPILimiter.init(redis)
```

**Apply limits:**

```python
from fastapi_limiter.depends import RateLimiter

@router.get("/summaries", dependencies=[Depends(RateLimiter(times=100, seconds=60))])
async def get_summaries(...):
    ...
```

## Monitoring & Logging

### Structured Logging

The API uses the existing logging infrastructure from `app/core/logging_utils.py`.

View logs:

```bash
# Development
uvicorn app.api.main:app --reload --log-level debug

# Production
journalctl -u bite-reader-api -f
```

### Health Checks

```bash
curl http://localhost:8000/health
```

### Metrics (Prometheus)

Add prometheus middleware:

```bash
pip install prometheus-fastapi-instrumentator
```

```python
from prometheus_fastapi_instrumentator import Instrumentator

@app.on_event("startup")
async def startup():
    Instrumentator().instrument(app).expose(app)
```

Metrics available at: `http://localhost:8000/metrics`

## Troubleshooting

### Issue: "Table does not exist"

**Solution:** Run database migrations first:

```bash
python -m app.cli.migrate_db
```

### Issue: "User not authorized"

**Solution:** Add your Telegram user ID to `ALLOWED_USER_IDS` in `.env`:

```bash
ALLOWED_USER_IDS=123456789,987654321
```

### Issue: "Rate limit exceeded"

**Solution:** Wait 60 seconds or increase rate limits in `app/api/middleware.py`.

### Issue: "Token has expired"

**Solution:** Use the refresh token endpoint to get a new access token:

```bash
curl -X POST http://localhost:8000/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "<refresh_token>"}'
```

## Next Steps

1. **Integrate with Telegram Bot**: The API runs alongside your existing Telegram bot
2. **Add Background Jobs**: Use Celery or FastAPI BackgroundTasks to process URLs asynchronously
3. **Implement Caching**: Add Redis caching for frequently accessed summaries
4. **Add WebSockets**: For real-time status updates instead of polling
5. **Build Android App**: Use the API with Retrofit + Room

## Resources

- **Full API Spec**: `docs/MOBILE_API_SPEC.md`
- **OpenAPI Schema**: http://localhost:8000/openapi.json
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Support

For issues or questions:
- Check logs: `journalctl -u bite-reader-api -f`
- Enable debug mode: `LOG_LEVEL=DEBUG`
- Review correlation IDs in responses for tracing

---

**Happy coding!** 🚀
