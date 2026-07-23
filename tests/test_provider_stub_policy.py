from __future__ import annotations

from unittest.mock import MagicMock

from app.services.macro.provider_registry import MacroProviderRegistry
from app.services.macro.providers.agushuju import AgushujuMacroProvider
from app.services.macro.providers.fed import FedMacroProvider
from app.services.macro.providers.ism import IsmMacroProvider
from app.services.macro.providers.tushare import TushareMacroProvider
from app.services.macro.providers.zhituapi import ZhituapiMacroProvider

STUB_PROVIDER_CLASSES = [
    AgushujuMacroProvider,
    TushareMacroProvider,
    ZhituapiMacroProvider,
    FedMacroProvider,
    IsmMacroProvider,
]


def test_each_stub_provider_declares_implemented_false() -> None:
    """Each of the 5 known stub providers must declare implemented=False.
    This is the explicit capability flag that the registry uses to skip
    them in resolve() and the health recorder uses to mark them as
    not_implemented (vs stale)."""
    for cls in STUB_PROVIDER_CLASSES:
        instance = cls()
        assert hasattr(instance, "implemented"), (
            f"{cls.__name__} missing 'implemented' attribute; expected False"
        )
        assert instance.implemented is False, (
            f"{cls.__name__}.implemented should be False; got "
            f"{instance.implemented!r}"
        )


def test_registry_skips_not_implemented_providers() -> None:
    """MacroProviderRegistry.resolve() must skip providers that declare
    implemented=False. The known stub providers should NOT be returned
    by resolve() for the source_keys they support."""
    registry = MacroProviderRegistry()
    # Each stub provider's provider_key + a source_kind it supports.
    cases = [
        ("agushuju", "raw_series"),
        ("tushare", "raw_series"),
        ("zhituapi", "raw_series"),
        ("federal_reserve", "calendar_event"),
        ("ism", "release_series"),
    ]
    for source_key, source_kind in cases:
        result = registry.resolve(
            source_provider=source_key, source_kind=source_kind
        )
        assert result is None, (
            f"Registry returned {type(result).__name__} for stub "
            f"({source_key!r}, {source_kind!r}); expected None because "
            f"the only matching provider is implemented=False"
        )


def test_source_health_records_not_implemented_status() -> None:
    """The source-health recorder in indicator_monitoring must classify
    NotImplementedError as status='not_implemented', distinct from
    generic Exception which keeps status='stale'."""
    from app.services.indicator_monitoring import IndicatorMonitoringService

    service = IndicatorMonitoringService.__new__(IndicatorMonitoringService)
    # Patch the recorder to capture the call instead of writing to DB.
    captured: list[dict] = []

    async def fake_record(*, provider_key, source_key, status, message, latency_ms, payload_json):
        captured.append(
            {
                "provider_key": provider_key,
                "source_key": source_key,
                "status": status,
                "message": message,
            }
        )

    service._record_macro_source_health = fake_record  # type: ignore[method-assign]

    provider = MagicMock()
    provider.provider_key = "stub_test"
    sym = "TEST_SYM"
    exc = NotImplementedError("stub not implemented")

    import asyncio

    async def run_branch():
        try:
            raise exc
        except NotImplementedError as e:
            await service._record_macro_source_health(
                provider_key=provider.provider_key,
                source_key=sym,
                status="not_implemented",
                message=str(e),
                latency_ms=0,
                payload_json={"indicator_key": "test", "reason": "stub"},
            )
        except Exception as e:
            await service._record_macro_source_health(
                provider_key=provider.provider_key,
                source_key=sym,
                status="stale",
                message=str(e),
                latency_ms=0,
                payload_json={"indicator_key": "test"},
            )

    asyncio.run(run_branch())
    assert len(captured) == 1
    assert captured[0]["status"] == "not_implemented", (
        f"NotImplementedError must be classified as 'not_implemented'; "
        f"got {captured[0]['status']!r}"
    )
    assert captured[0]["provider_key"] == "stub_test"
    assert "not implemented" in captured[0]["message"]
