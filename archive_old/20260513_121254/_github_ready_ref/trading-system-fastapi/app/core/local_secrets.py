from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


@dataclass(slots=True)
class GateAPICredentials:
    api_key: str
    api_secret: str
    passphrase: str | None = None
    label: str | None = None
    updated_at: datetime | None = None


class LocalSecretStore:
    def __init__(
        self,
        base_dir: str | Path | None = None,
        key_filename: str | None = None,
        store_filename: str | None = None,
    ) -> None:
        self.base_dir = Path(base_dir or settings.local_secrets_dir)
        self.key_path = self.base_dir / (key_filename or settings.local_secret_key_filename)
        self.store_path = self.base_dir / (store_filename or settings.local_secret_store_filename)

    def _ensure_base_dir(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.base_dir, 0o700)
        except PermissionError:  # pragma: no cover
            pass

    def _load_or_create_key(self) -> bytes:
        self._ensure_base_dir()
        if self.key_path.exists():
            return self.key_path.read_bytes()
        key = Fernet.generate_key()
        self.key_path.write_bytes(key)
        try:
            os.chmod(self.key_path, 0o600)
        except PermissionError:  # pragma: no cover
            pass
        return key

    def _fernet(self) -> Fernet:
        return Fernet(self._load_or_create_key())

    def _read_all(self) -> dict[str, Any]:
        if not self.store_path.exists():
            return {"providers": {}}
        encrypted = self.store_path.read_bytes()
        if not encrypted:
            return {"providers": {}}
        try:
            plaintext = self._fernet().decrypt(encrypted)
        except InvalidToken as exc:
            raise ValueError("local secret store cannot be decrypted with current key") from exc
        payload = json.loads(plaintext.decode("utf-8"))
        payload.setdefault("providers", {})
        return payload

    def _write_all(self, payload: dict[str, Any]) -> None:
        self._ensure_base_dir()
        encrypted = self._fernet().encrypt(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        self.store_path.write_bytes(encrypted)
        try:
            os.chmod(self.store_path, 0o600)
        except PermissionError:  # pragma: no cover
            pass

    def gate_credentials_status(self) -> dict[str, Any]:
        payload = self._read_all()
        entry = payload.get("providers", {}).get("gateio")
        if not entry:
            return {"configured": False, "updated_at": None, "label": None}
        return {
            "configured": True,
            "updated_at": entry.get("updated_at"),
            "label": entry.get("label"),
        }

    def save_gate_credentials(
        self,
        api_key: str,
        api_secret: str,
        passphrase: str | None = None,
        label: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        payload = self._read_all()
        providers = payload.setdefault("providers", {})
        providers["gateio"] = {
            "api_key": api_key,
            "api_secret": api_secret,
            "passphrase": passphrase,
            "label": label,
            "updated_at": now,
        }
        self._write_all(payload)
        return {"configured": True, "updated_at": now, "label": label}

    def load_gate_credentials(self) -> GateAPICredentials | None:
        payload = self._read_all()
        entry = payload.get("providers", {}).get("gateio")
        if not entry:
            return None
        updated_at_raw = entry.get("updated_at")
        updated_at = datetime.fromisoformat(updated_at_raw) if updated_at_raw else None
        return GateAPICredentials(
            api_key=str(entry["api_key"]),
            api_secret=str(entry["api_secret"]),
            passphrase=entry.get("passphrase"),
            label=entry.get("label"),
            updated_at=updated_at,
        )

    def delete_gate_credentials(self) -> bool:
        payload = self._read_all()
        providers = payload.setdefault("providers", {})
        if "gateio" not in providers:
            return False
        providers.pop("gateio", None)
        self._write_all(payload)
        return True


secret_store = LocalSecretStore()
