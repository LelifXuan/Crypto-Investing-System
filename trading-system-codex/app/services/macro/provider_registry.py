from __future__ import annotations

from app.services.macro.providers.bls import BlsMacroProvider
from app.services.macro.providers.china import ChinaMacroProvider
from app.services.macro.providers.fed import FedMacroProvider
from app.services.macro.providers.fred import FredMacroProvider
from app.services.macro.providers.ism import IsmMacroProvider


class MacroProviderRegistry:
    def __init__(self) -> None:
        self._providers = [
            FredMacroProvider(),
            BlsMacroProvider(),
            IsmMacroProvider(),
            FedMacroProvider(),
            ChinaMacroProvider(),
        ]

    def resolve(self, *, source_provider: str, source_kind: str):
        for provider in self._providers:
            if provider.supports(source_provider, source_kind):
                return provider
        return None

    def providers(self) -> list:
        return list(self._providers)
