import pytest

from app.api.routers.auth import create_access_token
from app.db.models import Request, Summary, User


@pytest.fixture
def article_user(db):
    return User.create(telegram_user_id=123456789, username="article_test_user")


@pytest.fixture
def article_data(db, article_user):
    # Create request
    req = Request.create(
        user_id=article_user.telegram_user_id,
        type="url",
        status="completed",
        input_url="https://example.com/article",
        normalized_url="https://example.com/article",
    )
    # Create summary
    summary = Summary.create(
        request=req,
        lang="en",
        json_payload={"tldr": "Too long", "metadata": {"title": "Example Article"}},
    )
    return {"user": article_user, "request": req, "summary": summary}


def test_get_article_by_id(client, article_data):
    user = article_data["user"]
    summary = article_data["summary"]

    token = create_access_token(user.telegram_user_id, client_id="test")

    response = client.get(
        f"/v1/articles/{summary.id}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["summary"]["id"] == summary.id
    assert data["request"]["input_url"] == "https://example.com/article"


def test_get_article_by_url(client, article_data):
    user = article_data["user"]
    summary = article_data["summary"]

    token = create_access_token(user.telegram_user_id, client_id="test")

    # Test strict match
    url = "https://example.com/article"
    response = client.get(
        "/v1/articles/by-url", params={"url": url}, headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["summary"]["id"] == summary.id
    assert data["request"]["input_url"] == url


def test_get_article_by_url_not_found(client, article_data):
    user = article_data["user"]
    token = create_access_token(user.telegram_user_id, client_id="test")

    response = client.get(
        "/v1/articles/by-url",
        params={"url": "https://nonexistent.com"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
