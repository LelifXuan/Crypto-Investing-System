from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from app.services.macro.secret_loader import redact


class CacheStore:
    def __init__(self, path: str | Path = "data/cache/macro_api/cache.sqlite"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS macro_cache_entries (
                    cache_key TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    sanitized_params_hash TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    ttl_seconds INTEGER NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )

    @staticmethod
    def _hash_params(params: Dict[str, Any]) -> str:
        safe = redact(params)
        encoded = json.dumps(safe, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def make_key(self, source: str, endpoint: str, params: Dict[str, Any]) -> Tuple[str, str]:
        p_hash = self._hash_params(params)
        raw = f"{source}:{endpoint}:{p_hash}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest(), p_hash

    def get(self, source: str, endpoint: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        key, _ = self.make_key(source, endpoint, params)
        now = int(time.time())
        with sqlite3.connect(self.path) as conn:
            row = conn.execute(
                "SELECT created_at, ttl_seconds, payload FROM macro_cache_entries WHERE cache_key=?",
                (key,),
            ).fetchone()
        if not row:
            return None
        created_at, ttl_seconds, payload = row
        if now - int(created_at) > int(ttl_seconds):
            return None
        return json.loads(payload)

    def set(self, source: str, endpoint: str, params: Dict[str, Any], payload: Dict[str, Any], ttl_seconds: int) -> None:
        key, p_hash = self.make_key(source, endpoint, params)
        now = int(time.time())
        safe_payload = redact(payload)
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO macro_cache_entries
                (cache_key, source, endpoint, sanitized_params_hash, created_at, ttl_seconds, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (key, source, endpoint, p_hash, now, ttl_seconds, json.dumps(safe_payload, ensure_ascii=False)),
            )
