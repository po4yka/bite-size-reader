"""HTTP webhook dispatch adapter for automation rules."""

from __future__ import annotations

import httpx


class HttpWebhookDispatchAdapter:
    """Dispatch webhook payloads over HTTP."""

    def __init__(self, timeout_seconds: float = 5.0) -> None:
        self._timeout = timeout_seconds

    async def async_dispatch(self, url: str, payload: dict) -> int:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.status_code
