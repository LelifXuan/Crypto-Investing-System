from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("secret")
    assert verify_password("secret", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_token_roundtrip(monkeypatch) -> None:
    # Dedicated non-production key; monkeypatch restores the runtime setting.
    monkeypatch.setattr(settings, "jwt_secret_key", "test-only-not-a-secret-" * 4)
    token, _ = create_access_token(user_id="u1", username="admin", tenant_id="t1", roles=["admin"])
    payload = decode_access_token(token)
    assert payload.sub == "u1"
    assert payload.username == "admin"
    assert payload.roles == ["admin"]
