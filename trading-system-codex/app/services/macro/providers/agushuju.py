from __future__ import annotations

from app.services.macro.cache_store import CacheStore
from app.services.macro.providers.base import MacroFetchResult
from app.services.macro.secret_loader import SecretLoader

UTC = __import__("datetime").timezone.utc


class AgushujuMacroProvider:
    provider_key = "agushuju"

    def __init__(self, secrets: SecretLoader | None = None, cache: CacheStore | None = None):
        self.secrets = secrets or SecretLoader()
        self.cache = cache

    def supports(self, source_provider: str, source_kind: str) -> bool:
        return source_provider == self.provider_key and source_kind in (
            "raw_series",
            "release_series",
        )

    async def fetch_latest(self, source_key: str) -> MacroFetchResult:
        raise NotImplementedError(f"agushuju fetch_latest not yet implemented for {source_key}")

    async def healthcheck(self) -> tuple[str, str | None]:
        key = self.secrets.get("AGUSHUJU_API_KEY")
        if not key:
            return "auth_missing", "AGUSHUJU_API_KEY not set"
        try:
            return (
                "unknown",
                "agushuju healthcheck requires SDK integration; key is present but "
                "full connectivity test is not yet implemented",
            )
        except Exception as exc:
            return "unhealthy", str(exc)

    async def connectivity_check(self) -> dict:
        key = self.secrets.get("AGUSHUJU_API_KEY")
        if not key:
            return {
                "source": "agushuju",
                "status": "auth_missing",
                "latency_ms": 0,
                "auth": "missing",
                "error": "AGUSHUJU_API_KEY not set",
            }
        return {
            "source": "agushuju",
            "status": "unknown",
            "latency_ms": 0,
            "auth": "present",
            "error": "agushuju connectivity check requires SDK integration; key is present",
        }
