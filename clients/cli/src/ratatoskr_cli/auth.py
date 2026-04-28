"""Ratatoskr CLI authentication and token management."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx
from ratatoskr_cli.config import load_config, save_config
from ratatoskr_cli.exceptions import AuthError

if TYPE_CHECKING:
    from ratatoskr_cli.client import RatatoskrClient
    from ratatoskr_cli.config import RatatoskrConfig


def login(server_url: str, user_id: int, client_id: str, secret: str) -> RatatoskrConfig:
    """Authenticate via secret-key login and return updated config with tokens."""
    resp = httpx.post(
        f"{server_url.rstrip('/')}/v1/auth/secret-login",
        json={"user_id": user_id, "client_id": client_id, "secret": secret},
        timeout=30.0,
    )

    body = resp.json()
    if not body.get("success", False):
        error = body.get("error", {})
        raise AuthError(f"Login failed: {error.get('message', resp.text[:200])}")

    data = body["data"]
    tokens = data.get("tokens", data)  # Handle both nested and flat response shapes

    expires_in = tokens.get("expires_in", 1800)
    expires_at = datetime.now(UTC).timestamp() + expires_in
    expires_at_iso = datetime.fromtimestamp(expires_at, tz=UTC).isoformat()

    config = load_config()
    config.server_url = server_url
    config.client_id = client_id
    config.user_id = user_id
    config.access_token = tokens["access_token"]
    config.refresh_token = tokens.get("refresh_token", config.refresh_token)
    config.token_expires_at = expires_at_iso
    save_config(config)

    return config


def refresh_if_needed(config: RatatoskrConfig) -> RatatoskrConfig:
    """Refresh access token if it's about to expire (within 5 minutes)."""
    if not config.token_expires_at or not config.refresh_token:
        return config

    try:
        expires_at = datetime.fromisoformat(config.token_expires_at)
    except (ValueError, TypeError):
        return config

    now = datetime.now(UTC)
    # Refresh if within 5 minutes of expiry
    if (expires_at - now).total_seconds() > 300:
        return config

    try:
        resp = httpx.post(
            f"{config.server_url.rstrip('/')}/v1/auth/refresh",
            json={"refresh_token": config.refresh_token},
            timeout=30.0,
        )
        body = resp.json()
        if body.get("success"):
            data = body["data"]
            tokens = data.get("tokens", data)
            config.access_token = tokens["access_token"]
            if tokens.get("refresh_token"):
                config.refresh_token = tokens["refresh_token"]
            expires_in = tokens.get("expires_in", 1800)
            expires_at_ts = datetime.now(UTC).timestamp() + expires_in
            config.token_expires_at = datetime.fromtimestamp(expires_at_ts, tz=UTC).isoformat()
            save_config(config)
    except Exception:
        pass  # If refresh fails, continue with current token -- it may still work

    return config


def ensure_authenticated(config: RatatoskrConfig) -> RatatoskrConfig:
    """Validate config has tokens and refresh if needed."""
    if not config.access_token:
        raise AuthError("Not authenticated. Run: ratatoskr login")
    return refresh_if_needed(config)


def get_client(ctx: dict) -> RatatoskrClient:
    """Build an authenticated RatatoskrClient from CLI context."""
    from ratatoskr_cli.client import RatatoskrClient
    from ratatoskr_cli.config import require_config

    config = require_config()
    config = ensure_authenticated(config)
    server = ctx.get("server") or config.server_url
    return RatatoskrClient(server, config.access_token)
