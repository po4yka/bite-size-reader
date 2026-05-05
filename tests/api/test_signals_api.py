from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from app.api.routers.auth.tokens import create_access_token
from app.db.models import FeedItem, Source, Subscription, User, UserSignal

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


def _headers(user_id: int) -> dict[str, str]:
    token = create_access_token(user_id, client_id="test")
    return {"Authorization": f"Bearer {token}"}


def test_signal_feed_feedback_and_source_health(client: TestClient, db):
    user = User.create(telegram_user_id=777001, username="signals-user", is_owner=False)
    source = Source.create(
        kind="rss",
        external_id="https://example.com/feed.xml",
        url="https://example.com/feed.xml",
        title="Example Feed",
        fetch_error_count=1,
        last_error="timeout",
    )
    Subscription.create(user=user, source=source, is_active=True)
    item = FeedItem.create(
        source=source,
        external_id="guid-1",
        canonical_url="https://example.com/post",
        title="Signal item",
    )
    signal = UserSignal.create(
        user=user,
        feed_item=item,
        status="candidate",
        heuristic_score=0.8,
        final_score=0.8,
    )

    headers = _headers(user.telegram_user_id)
    with patch("app.api.routers.auth.dependencies.Config.get_allowed_user_ids", return_value=[]):
        list_response = client.get("/v1/signals", headers=headers)
        health_response = client.get("/v1/signals/sources/health", headers=headers)
        source_active_response = client.post(
            f"/v1/signals/sources/{source.id}/active",
            headers=headers,
            json={"is_active": False},
        )
        feedback_response = client.post(
            f"/v1/signals/{signal.id}/feedback",
            headers=headers,
            json={"action": "like"},
        )

    assert list_response.status_code == 200
    assert list_response.json()["data"]["signals"][0]["feed_item_title"] == "Signal item"
    assert health_response.status_code == 200
    health_rows = health_response.json()["data"]["sources"]
    assert health_rows[0]["title"] == "Example Feed"
    assert health_rows[0]["fetch_error_count"] == 1
    assert health_rows[0]["last_error"] == "timeout"
    assert source_active_response.status_code == 200
    assert Source.get_by_id(source.id).is_active is False
    assert feedback_response.status_code == 200
    signal = UserSignal.get_by_id(signal.id)
    assert signal.status == "liked"


def test_signal_health_reports_vector_readiness(client: TestClient, db):
    user = User.create(telegram_user_id=777002, username="signals-health", is_owner=False)
    headers = _headers(user.telegram_user_id)

    with patch("app.api.routers.auth.dependencies.Config.get_allowed_user_ids", return_value=[]):
        response = client.get("/v1/signals/health", headers=headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert "vector" in data
    assert "ready" in data["vector"]
    assert "sources" in data
