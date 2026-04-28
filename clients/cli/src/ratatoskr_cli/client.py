"""Ratatoskr API HTTP client."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

import httpx
from ratatoskr_cli.exceptions import APIError


class RatatoskrClient:
    """HTTP client for Ratatoskr REST API."""

    def __init__(self, base_url: str, access_token: str, timeout: float = 30.0) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Make request, unwrap envelope, raise on error."""
        resp = self._client.request(method, path, **kwargs)

        if resp.status_code == 204:
            return None

        try:
            body = resp.json()
        except Exception:
            resp.raise_for_status()
            return None

        if not body.get("success", False):
            error = body.get("error", {})
            raise APIError(
                code=error.get("code", "UNKNOWN"),
                message=error.get("message", resp.text[:200]),
                status_code=resp.status_code,
            )

        return body.get("data")

    # ---- Auth ----

    def whoami(self) -> dict[str, Any]:
        return self._request("GET", "/v1/auth/me")

    # ---- Summaries ----

    def quick_save(
        self,
        url: str,
        *,
        title: str | None = None,
        selected_text: str | None = None,
        tag_names: list[str] | None = None,
        summarize: bool = True,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"url": url, "summarize": summarize}
        if title:
            body["title"] = title
        if selected_text:
            body["selected_text"] = selected_text
        if tag_names:
            body["tag_names"] = tag_names
        return self._request("POST", "/v1/quick-save", json=body)

    def list_summaries(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        is_read: bool | None = None,
        is_favorited: bool | None = None,
        tag: str | None = None,
        sort: str = "created_at_desc",
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit, "offset": offset, "sort": sort}
        if is_read is not None:
            params["is_read"] = str(is_read).lower()
        if is_favorited is not None:
            params["is_favorited"] = str(is_favorited).lower()
        if tag:
            params["tag"] = tag
        return self._request("GET", "/v1/summaries", params=params)

    def get_summary(self, summary_id: int) -> dict[str, Any]:
        return self._request("GET", f"/v1/summaries/{summary_id}")

    def get_summary_content(self, summary_id: int) -> dict[str, Any]:
        return self._request("GET", f"/v1/summaries/{summary_id}/content")

    def delete_summary(self, summary_id: int) -> Any:
        return self._request("DELETE", f"/v1/summaries/{summary_id}")

    def toggle_favorite(self, summary_id: int) -> dict[str, Any]:
        return self._request("POST", f"/v1/summaries/{summary_id}/favorite")

    def mark_read(self, summary_id: int) -> dict[str, Any]:
        return self._request("PATCH", f"/v1/summaries/{summary_id}", json={"is_read": True})

    # ---- Search ----

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        offset: int = 0,
        language: str | None = None,
        tags: list[str] | None = None,
        domains: list[str] | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"q": query, "limit": limit, "offset": offset}
        if language:
            params["language"] = language
        if tags:
            params["tags"] = ",".join(tags)
        if domains:
            params["domains"] = ",".join(domains)
        return self._request("GET", "/v1/search", params=params)

    # ---- Tags ----

    def list_tags(self) -> dict[str, Any]:
        return self._request("GET", "/v1/tags")

    def create_tag(self, name: str, color: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"name": name}
        if color:
            body["color"] = color
        return self._request("POST", "/v1/tags", json=body)

    def delete_tag(self, tag_id: int) -> Any:
        return self._request("DELETE", f"/v1/tags/{tag_id}")

    def attach_tags(self, summary_id: int, tag_names: list[str]) -> dict[str, Any]:
        return self._request(
            "POST", f"/v1/summaries/{summary_id}/tags", json={"tag_names": tag_names}
        )

    def detach_tag(self, summary_id: int, tag_id: int) -> Any:
        return self._request("DELETE", f"/v1/summaries/{summary_id}/tags/{tag_id}")

    # ---- Collections ----

    def list_collections(self) -> dict[str, Any]:
        return self._request("GET", "/v1/collections")

    def create_collection(self, name: str, description: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"name": name}
        if description:
            body["description"] = description
        return self._request("POST", "/v1/collections", json=body)

    def delete_collection(self, collection_id: int) -> Any:
        return self._request("DELETE", f"/v1/collections/{collection_id}")

    def add_to_collection(self, collection_id: int, summary_id: int) -> dict[str, Any]:
        return self._request(
            "POST", f"/v1/collections/{collection_id}/items", json={"summary_id": summary_id}
        )

    # ---- Aggregations ----

    def create_aggregation_bundle(
        self,
        items: list[dict[str, Any]],
        *,
        lang_preference: str = "auto",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"items": items, "lang_preference": lang_preference}
        if metadata is not None:
            body["metadata"] = metadata
        return self._request("POST", "/v1/aggregations", json=body)

    def get_aggregation_bundle(self, session_id: int) -> dict[str, Any]:
        return self._request("GET", f"/v1/aggregations/{session_id}")

    def list_aggregation_bundles(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        return self._request("GET", "/v1/aggregations", params=params)

    # ---- Import/Export ----

    def export_data(self, fmt: str = "json") -> bytes:
        """Export data -- returns raw bytes (JSON/CSV/HTML)."""
        resp = self._client.get("/v1/export", params={"format": fmt})
        resp.raise_for_status()
        return resp.content

    def import_file(self, file_path: Path, *, summarize: bool = False) -> dict[str, Any]:
        """Upload import file (multipart)."""
        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f)}
            data = {"options": '{"summarize": ' + str(summarize).lower() + "}"}
            # Need to remove Content-Type header for multipart
            headers = dict(self._client.headers)
            headers.pop("Content-Type", None)
            resp = self._client.post("/v1/import", files=files, data=data, headers=headers)

        body = resp.json()
        if not body.get("success"):
            error = body.get("error", {})
            raise APIError(error.get("code", "UNKNOWN"), error.get("message", "Import failed"))
        return body.get("data")

    # ---- Admin ----

    def admin_users(self) -> dict[str, Any]:
        return self._request("GET", "/v1/admin/users")

    def admin_health(self) -> dict[str, Any]:
        return self._request("GET", "/v1/admin/health/content")

    def admin_jobs(self) -> dict[str, Any]:
        return self._request("GET", "/v1/admin/jobs")

    def health_check(self) -> dict[str, Any]:
        return self._request("GET", "/health")
