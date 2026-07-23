from __future__ import annotations


class ChinaMacroProvider:
    provider_key = "china_public"

    def supports(self, source_provider: str, source_kind: str) -> bool:
        return source_provider in {"china_public", "cnbs"} and source_kind in {
            "raw_series",
            "release_series",
        }

    async def fetch_latest(self, source_key: str):
        raise NotImplementedError(
            "china public provider is scaffolded but not live for every indicator yet"
        )

    async def healthcheck(self) -> tuple[str, str | None]:
        return "pending", "china provider scaffolded; individual indicators may remain pending"
