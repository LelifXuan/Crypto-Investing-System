from decimal import Decimal

from app.db.models.instrument import Instrument
from app.integrations.gateio import GateIOPublicClient
from app.services.market import MarketService


def test_parse_spot_candle() -> None:
    row = ["1712140800", "1000", "68000", "68100", "67900", "67950", "12.5", "true"]
    candle = GateIOPublicClient.parse_spot_candle(row)
    assert candle.close == Decimal("68000")
    assert candle.open == Decimal("67950")
    assert candle.volume == Decimal("12.5")


def test_parse_futures_candle() -> None:
    row = {"t": 1712140800, "v": 200, "c": "68000", "h": "68100", "l": "67900", "o": "67950"}
    candle = GateIOPublicClient.parse_futures_candle(row)
    assert candle.close == Decimal("68000")
    assert candle.open == Decimal("67950")
    assert candle.volume == Decimal("200")


def test_parse_futures_trade() -> None:
    row = {
        "id": 7,
        "create_time": 1712140800,
        "contract": "ETH_USDT",
        "size": "-3",
        "price": "3000",
    }
    trade = GateIOPublicClient.parse_futures_trade(row)

    assert trade.contract == "ETH_USDT"
    assert trade.side == "sell"
    assert trade.size == Decimal("3")
    assert trade.price == Decimal("3000")


def test_parse_futures_order_book() -> None:
    row = {
        "id": 10,
        "current": 1712140800,
        "contract": "ETH_USDT",
        "bids": [["2999", "2"]],
        "asks": [{"p": "3001", "s": "4"}],
    }
    book = GateIOPublicClient.parse_futures_order_book(row)

    assert book.order_book_id == 10
    assert book.bids == [(Decimal("2999"), Decimal("2"))]
    assert book.asks == [(Decimal("3001"), Decimal("4"))]


def test_parse_futures_contract_stats() -> None:
    row = {"time": 1712140800, "contract": "ETH_USDT", "open_interest": "12", "volume": "99"}
    stats = GateIOPublicClient.parse_futures_contract_stats(row)

    assert stats.contract == "ETH_USDT"
    assert stats.open_interest == Decimal("12")
    assert stats.volume == Decimal("99")


def test_resolve_gate_reference_for_futures() -> None:
    instrument = Instrument(
        instrument_id="btc-usdt-perp",
        venue="GATEIO",
        symbol="BTC_USDT",
        asset_class="PERP",
        base_ccy="BTC",
        quote_ccy="USDT",
        settle_ccy="USDT",
        tick_size=Decimal("0.1"),
        lot_size=Decimal("0.001"),
        contract_multiplier=Decimal("1"),
        margin_model="ISOLATED",
        metadata_json={
            "gateio": {"product_type": "futures", "contract": "BTC_USDT", "settle": "usdt"}
        },
    )
    ref = MarketService.resolve_gate_reference(instrument)
    assert ref.product_type == "futures"
    assert ref.symbol == "BTC_USDT"
    assert ref.settle == "usdt"


def test_resolve_gate_reference_for_spot() -> None:
    instrument = Instrument(
        instrument_id="eth-usdt-spot",
        venue="GATEIO",
        symbol="ETH/USDT",
        asset_class="SPOT",
        base_ccy="ETH",
        quote_ccy="USDT",
        settle_ccy="USDT",
        tick_size=Decimal("0.01"),
        lot_size=Decimal("0.0001"),
        contract_multiplier=Decimal("1"),
        margin_model="NONE",
        metadata_json={"gateio": {"product_type": "spot", "currency_pair": "ETH_USDT"}},
    )
    ref = MarketService.resolve_gate_reference(instrument)
    assert ref.product_type == "spot"
    assert ref.symbol == "ETH_USDT"
    assert ref.settle is None
