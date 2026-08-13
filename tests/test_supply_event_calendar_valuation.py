"""API guards for quantity, current valuation and undated BNB coverage."""

from decimal import Decimal
from pathlib import Path

from app.api.v1.endpoints.market_events import _display_value, _payload_decimal


ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = (ROOT / "app" / "api" / "v1" / "endpoints" / "market_events.py").read_text(
    encoding="utf-8"
)
SCHEMA = (ROOT / "app" / "schemas" / "market.py").read_text(encoding="utf-8")


def test_supply_payload_decimal_preserves_exact_quantity() -> None:
    assert _payload_decimal({"nominal_unlock_qty": "9920000"}, "nominal_unlock_qty") == Decimal(
        "9920000"
    )
    assert _payload_decimal({}, "nominal_unlock_qty") is None
    assert _display_value(Decimal("9920000"), Decimal("57.661")) == Decimal("571997120.00")


def test_bnb_is_coverage_not_a_fabricated_dated_node() -> None:
    assert '_BNB_UNSCHEDULED_QUANTITY = Decimal("20000000")' in ENDPOINT
    assert '"schedule_status": "no_verified_future_nodes"' in ENDPOINT
    assert '"event_at"' not in ENDPOINT.split('"asset": "BNB"', maxsplit=1)[1]


def test_calendar_schema_exposes_decimal_valuation_fields() -> None:
    assert "unlock_quantity: Decimal | None" in SCHEMA
    assert "market_value: Decimal | None" in SCHEMA
    assert "coverage: list[SupplyEventAssetCoverage]" in SCHEMA
