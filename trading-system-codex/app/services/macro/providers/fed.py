from __future__ import annotations


class FedMacroProvider:
    provider_key = "federal_reserve"

    def supports(self, source_provider: str, source_kind: str) -> bool:
        return source_provider == self.provider_key and source_kind in {
            "calendar_event",
            "release_series",
        }

    async def fetch_latest(self, source_key: str):
        raise NotImplementedError(
            "federal reserve calendar events are resolved via macro calendar fallback"
        )

    async def healthcheck(self) -> tuple[str, str | None]:
        return "healthy", None
