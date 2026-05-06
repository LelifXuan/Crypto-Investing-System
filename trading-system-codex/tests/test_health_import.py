from fastapi.testclient import TestClient

from app.main import app, create_app


def test_app_import() -> None:
    assert app.title


def test_health_summary_endpoint() -> None:
    with TestClient(create_app(enable_lifespan=False)) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["checks"]["live"] == "/health/live"


def test_dashboard_page_renders_html() -> None:
    with TestClient(create_app(enable_lifespan=False)) as client:
        response = client.get("/dashboard")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'data-page="monitoring-overview"' in response.text
