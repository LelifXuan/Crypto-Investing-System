from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.main import create_app


async def test_single_user_mode_returns_local_user(monkeypatch) -> None:
    monkeypatch.setattr(settings, "single_user_mode", True)
    monkeypatch.setattr(settings, "local_user_id", "local_user")
    monkeypatch.setattr(settings, "local_tenant_id", "local_tenant")
    monkeypatch.setattr(settings, "local_username", "local")
    monkeypatch.setattr(settings, "local_user_roles", ["admin", "viewer"])

    current_user = await get_current_user(credentials=None, session=None)

    assert current_user.user_id == "local_user"
    assert current_user.username == "local"
    assert current_user.roles == ["admin", "viewer"]


def test_local_only_middleware_blocks_non_local_host(monkeypatch) -> None:
    monkeypatch.setattr(settings, "local_only_enforced", True)
    monkeypatch.setattr(settings, "local_allowed_hosts", ["127.0.0.1"])

    with TestClient(create_app(enable_lifespan=False)) as client:
        response = client.get("/docs")

    assert response.status_code == 403
    assert response.json()["detail"] == "local-only mode enabled; remote access is blocked"
