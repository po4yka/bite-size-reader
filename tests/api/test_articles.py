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
    # Create summary with full json_payload to satisfy API response model
    full_payload = {
        "summary_250": "Short summary",
        "summary_1000": "Long summary",
        "tldr": "Too long",
        "key_ideas": ["Idea 1", "Idea 2"],
        "topic_tags": ["tag1", "tag2"],
        "entities": {"people": ["Person"], "organizations": ["Org"], "locations": ["Loc"]},
        "estimated_reading_time_min": 5,
        "key_stats": [{"label": "Stat", "value": 10, "unit": "%", "source_excerpt": "source"}],
        "answered_questions": ["Q1?"],
        "readability": {"method": "FK", "score": 50.0, "level": "Easy"},
        "seo_keywords": ["keyword"],
        "metadata": {
            "title": "Example Article",
            "domain": "example.com",
            "author": "Author",
            "published_at": "2023-01-01",
        },
        "confidence": 0.9,
        "hallucination_risk": "low",
    }
    summary = Summary.create(
        request=req,
        lang="en",
        json_payload=full_payload,
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
    # Response uses SummaryDetail model with camelCase keys
    assert data["summary"]["tldr"] == "Too long"
    assert data["request"]["url"] == "https://example.com/article"


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
    # Response uses SummaryDetail model with camelCase keys
    assert data["summary"]["tldr"] == "Too long"
    assert data["request"]["url"] == url


def test_get_article_by_url_not_found(client, article_data):
    user = article_data["user"]
    token = create_access_token(user.telegram_user_id, client_id="test")

    response = client.get(
        "/v1/articles/by-url",
        params={"url": "https://nonexistent.com"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
