from unittest.mock import MagicMock, patch

import pytest
from ratatoskr_cli.client import RatatoskrClient
from ratatoskr_cli.exceptions import APIError


class TestRatatoskrClient:
    def test_success_response_unwrapping(self):
        """_request unwraps success envelope correctly."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"success": True, "data": {"id": 1, "title": "Test"}}

        client = RatatoskrClient("http://localhost:8000", "fake-token")
        with patch.object(client._client, "request", return_value=mock_resp):
            result = client._request("GET", "/v1/test")
        assert result == {"id": 1, "title": "Test"}

    def test_error_response_raises_api_error(self):
        """_request raises APIError on failure envelope."""
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {
            "success": False,
            "error": {"code": "VALIDATION_ERROR", "message": "Invalid input"},
        }

        client = RatatoskrClient("http://localhost:8000", "fake-token")
        with patch.object(client._client, "request", return_value=mock_resp):
            with pytest.raises(APIError) as exc_info:
                client._request("GET", "/v1/test")
            assert "VALIDATION_ERROR" in str(exc_info.value)

    def test_204_returns_none(self):
        """_request returns None for 204 No Content."""
        mock_resp = MagicMock()
        mock_resp.status_code = 204

        client = RatatoskrClient("http://localhost:8000", "fake-token")
        with patch.object(client._client, "request", return_value=mock_resp):
            assert client._request("DELETE", "/v1/test") is None

    def test_auth_header_set(self):
        """Client sets Authorization header."""
        client = RatatoskrClient("http://localhost:8000", "my-token")
        assert client._client.headers["authorization"] == "Bearer my-token"

    def test_create_aggregation_bundle_routes_to_api(self):
        """create_aggregation_bundle sends the expected POST request."""
        client = RatatoskrClient("http://localhost:8000", "my-token")
        items = [{"type": "url", "url": "https://example.com", "source_kind_hint": "x_post"}]

        with patch.object(client, "_request", return_value={"session": {"id": 1}}) as request:
            client.create_aggregation_bundle(items, lang_preference="ru", metadata={"kind": "cli"})

        request.assert_called_once_with(
            "POST",
            "/v1/aggregations",
            json={
                "items": items,
                "lang_preference": "ru",
                "metadata": {"kind": "cli"},
            },
        )

    def test_get_aggregation_bundle_routes_to_api(self):
        """get_aggregation_bundle targets the session detail route."""
        client = RatatoskrClient("http://localhost:8000", "my-token")

        with patch.object(client, "_request", return_value={"session": {"id": 42}}) as request:
            client.get_aggregation_bundle(42)

        request.assert_called_once_with("GET", "/v1/aggregations/42")

    def test_list_aggregation_bundles_routes_to_api(self):
        """list_aggregation_bundles targets the list route."""
        client = RatatoskrClient("http://localhost:8000", "my-token")

        with patch.object(client, "_request", return_value={"sessions": []}) as request:
            client.list_aggregation_bundles(limit=5, offset=10)

        request.assert_called_once_with(
            "GET", "/v1/aggregations", params={"limit": 5, "offset": 10}
        )
