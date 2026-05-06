from __future__ import annotations


class BlsMacroProvider:
    provider_key = "bls"

    def supports(self, source_provider: str, source_kind: str) -> bool:
        return source_provider == self.provider_key and source_kind == "release_series"

    async def fetch_latest(self, source_key: str):
        raise NotImplementedError("bls release series is resolved via macro calendar fallback")

    async def healthcheck(self) -> tuple[str, str | None]:
        return "healthy", None
