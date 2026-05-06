from pathlib import Path

from app.core.local_secrets import LocalSecretStore


def test_local_secret_roundtrip(tmp_path: Path) -> None:
    store = LocalSecretStore(base_dir=tmp_path)
    initial = store.gate_credentials_status()
    assert initial["configured"] is False

    saved = store.save_gate_credentials(api_key="k", api_secret="s", label="demo")
    assert saved["configured"] is True

    creds = store.load_gate_credentials()
    assert creds is not None
    assert creds.api_key == "k"
    assert creds.api_secret == "s"
    assert creds.label == "demo"

    assert store.delete_gate_credentials() is True
    assert store.gate_credentials_status()["configured"] is False
