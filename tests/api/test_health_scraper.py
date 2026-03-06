from fastapi.testclient import TestClient


def test_health_detailed_includes_scraper_component(client: TestClient) -> None:
    response = client.get("/health/detailed")
    assert response.status_code == 200

    payload = response.json()["data"]
    components = payload["components"]

    assert "scraper" in components
    scraper = components["scraper"]
    assert "status" in scraper
    assert "provider_order_effective" in scraper or "error" in scraper
