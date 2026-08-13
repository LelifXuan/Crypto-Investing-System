"""Tests for the gold workbench aggregation (V5 page payload).

Covers:
- build_gold_decisions status precedence (READY_FIXED_ADD reachability,
  stale-quote, overweight, cooldown, confirmations gates)
- _gold_confirmations_passed counting
- GET /api/v1/gold/workbench contract (degraded setup_required shape)
- GET /api/v1/gold/workbench/charts/{snapshot_id} 404 for unknown id
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api.dependencies import get_db_session
from app.api.v1.endpoints.gold import _gold_confirmations_passed, _gold_quote_age_seconds
from app.db.models.market import GoldPolicyVersion
from app.main import create_app
from app.services.gold_workbench import build_gold_decisions


def _policy(**overrides) -> GoldPolicyVersion:
    base = dict(
        policy_id="p1",
        tenant_id="local_tenant",
        user_id="local_user",
        version=1,
        base_currency="USD",
        portfolio_total=200_000,
        gold_current_value=10_000,
        available_cash=25_000,
        target_min=0.05,
        target_max=0.15,
        base_dca_amount=500,
        fixed_dip_add_amount=1000,
        cooldown_days=14,
        quote_max_age_seconds=300,
        confirmations_required=3,
        drawdown_threshold=0.08,
        pause_base_when_overweight=False,
        created_at=datetime.now(timezone.utc),
    )
    base.update(overrides)
    return GoldPolicyVersion(**base)


def _decisions(policy_overrides=None, **kwargs):
    """Thin wrapper with sensible defaults so each test overrides one axis.

    ``policy_overrides`` mutate the GoldPolicyVersion fields; ``kwargs`` are
    passed straight to ``build_gold_decisions``.
    """
    params = dict(
        quote_age_seconds=60,
        drawdown_60d=-0.12,
        confirmations_passed=3,
        liquidity_shock=False,
        executed_today=False,
        last_dip_add_date=None,
    )
    params.update(kwargs)
    return build_gold_decisions(_policy(**(policy_overrides or {})), **params)


class TestBuildGoldDecisionsBaseDca:
    def test_execute_when_all_gates_clear(self):
        d = _decisions()
        assert d["base_dca"]["status"] == "EXECUTE"
        # Decimal serialized to fixed notation (no scientific), scale-preserving
        assert Decimal(d["base_dca"]["amount"]) == Decimal("500")

    def test_stale_quote_blocks_base(self):
        d = _decisions(quote_age_seconds=999_999)
        assert d["base_dca"]["status"] == "BLOCKED_STALE_QUOTE"
        assert Decimal(d["base_dca"]["amount"]) == 0

    def test_missing_quote_blocks_base(self):
        d = _decisions(quote_age_seconds=None)
        assert d["base_dca"]["status"] == "BLOCKED_STALE_QUOTE"

    def test_already_executed_today_blocks_base(self):
        d = _decisions(executed_today=True)
        assert d["base_dca"]["status"] == "ALREADY_EXECUTED"

    def test_insufficient_cash_blocks_base(self):
        d = _decisions(policy_overrides={"available_cash": 100})
        assert d["base_dca"]["status"] == "BLOCKED_INSUFFICIENT_CASH"

    def test_invalid_amount_blocks_base(self):
        d = _decisions(policy_overrides={"base_dca_amount": 0})
        assert d["base_dca"]["status"] == "BLOCKED_INVALID_AMOUNT"


class TestBuildGoldDecisionsDipAdd:
    def test_ready_fixed_add_reachable_with_confirmations(self):
        """Regression: the codex draft hard-coded confirmations_passed=0,
        which made READY_FIXED_ADD unreachable. With 3/3 confirmations and
        drawdown exceeded, the dip-add must trigger."""
        d = _decisions(confirmations_passed=3)
        assert d["dip_add"]["status"] == "READY_FIXED_ADD"
        assert Decimal(d["dip_add"]["amount"]) == Decimal("1000")

    def test_wait_drawdown_when_within_threshold(self):
        d = _decisions(drawdown_60d=-0.02)
        assert d["dip_add"]["status"] == "WAIT_DRAWDOWN"

    def test_setup_forming_when_confirmations_short(self):
        d = _decisions(confirmations_passed=2)
        assert d["dip_add"]["status"] == "SETUP_FORMING"
        assert d["dip_add"]["confirmations"]["passed"] == 2

    def test_liquidity_shock_blocks_dip(self):
        d = _decisions(liquidity_shock=True)
        assert d["dip_add"]["status"] == "BLOCKED_LIQUIDITY_SHOCK"

    def test_cooldown_blocks_dip(self):
        recent = date.today() - timedelta(days=2)
        d = _decisions(last_dip_add_date=recent)
        assert d["dip_add"]["status"] == "COOLDOWN"


class TestBuildGoldDecisionsAllocation:
    def test_underweight_when_below_min(self):
        d = _decisions(policy_overrides={"gold_current_value": 4_000})
        assert d["strategic_allocation"]["allocation_state"] == "STRATEGIC_UNDERWEIGHT"
        # gap = 200000 * 0.05 - 4000 = 6000
        assert Decimal(d["strategic_allocation"]["gap_amount"]) == Decimal("6000")

    def test_within_range(self):
        d = _decisions(policy_overrides={"gold_current_value": 20_000})
        assert d["strategic_allocation"]["allocation_state"] == "STRATEGIC_WITHIN_RANGE"
        assert Decimal(d["strategic_allocation"]["gap_amount"]) == 0

    def test_overweight_no_sell(self):
        d = _decisions(policy_overrides={"gold_current_value": 40_000})
        assert d["strategic_allocation"]["allocation_state"] == "STRATEGIC_OVERWEIGHT_NO_SELL"

    def test_overweight_pause_when_policy_says_so(self):
        d = _decisions(
            policy_overrides={"gold_current_value": 40_000, "pause_base_when_overweight": True}
        )
        assert d["base_dca"]["status"] == "PAUSED_BY_EXPLICIT_PORTFOLIO_POLICY"

    def test_decimal_amounts_serialized_without_scientific_notation(self):
        d = _decisions()
        assert Decimal(d["portfolio"]["portfolio_total"]) == Decimal("200000")
        assert Decimal(d["strategic_allocation"]["current_weight"]) == Decimal("0.05")


class TestConfirmationsPassed:
    def test_counts_all_five_when_everything_passes(self):
        tech = {
            "rsi_14": 30,
            "boll_pct_b": 0.1,
            "ema20_distance": -0.03,
            "cci_20": -90,
        }
        market = {"volume_zscore": 2.0}
        assert _gold_confirmations_passed(market, tech) == 5

    def test_counts_zero_when_nothing_passes(self):
        tech = {"rsi_14": 60, "boll_pct_b": 0.6, "ema20_distance": 0.01, "cci_20": 10}
        market = {"volume_zscore": -0.5}
        assert _gold_confirmations_passed(market, tech) == 0

    def test_handles_missing_values(self):
        assert _gold_confirmations_passed({}, {}) == 0


class TestQuoteAgeFreshness:
    """A daily-candle workbench must not flag today's/yesterday's bar stale.
    The policy's quote_max_age_seconds (e.g. 30s) targets an intraday live
    feed; applied verbatim to a 00:00-UTC daily bar it would permanently
    block the DCA gates (BLOCKED_STALE_QUOTE)."""

    def test_today_bar_is_fresh(self):
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        assert _gold_quote_age_seconds({"updated_at": ts}) == 0

    def test_yesterday_bar_is_fresh(self):
        ts = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        assert _gold_quote_age_seconds({"updated_at": ts}) == 0

    def test_two_day_old_bar_is_stale(self):
        ts = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
        age = _gold_quote_age_seconds({"updated_at": ts})
        assert age is not None and age > 86400

    def test_missing_timestamp_is_unknown(self):
        assert _gold_quote_age_seconds({"updated_at": None}) is None


async def _dummy_db_session():
    yield None


def _client() -> TestClient:
    app = create_app(enable_lifespan=False)
    app.dependency_overrides[get_db_session] = _dummy_db_session
    return TestClient(app)


class TestWorkbenchEndpoint:
    def test_workbench_returns_setup_required_without_policy(self):
        """With no DB session the endpoint must degrade to a structured
        setup_required payload — not 500 — and still ship the full shell
        blocks gold_v5.js renders (hero / workbench grid / governance)."""
        with _client() as client:
            resp = client.get("/api/v1/gold/workbench")
        assert resp.status_code == 200
        data = resp.json()
        assert data["refresh_state"] == "setup_required"
        assert data["snapshot"]["status"] == "setup_required"
        assert "strategic_allocation" in data
        assert "base_dca" in data
        assert "dip_add" in data
        assert "technical_summary" in data
        assert "derivatives" in data
        assert "market_scenarios" in data
        assert "source_manifest" in data

    def test_workbench_chart_token_shows_zero_count_without_session(self):
        with _client() as client:
            data = client.get("/api/v1/gold/workbench").json()
        token = data["chart_series_or_chart_token"]
        assert "snapshot_id" in token
        assert token["count"] == 0
        # count=0 means the frontend renders the empty state instead of
        # 5 dead canvases — assert the contract gold_v5.js gates on.
        assert token["path"].startswith("/api/v1/gold/workbench/charts/")

    def test_workbench_source_manifest_has_source_keys(self):
        with _client() as client:
            data = client.get("/api/v1/gold/workbench").json()
        keys = [entry["source_key"] for entry in data["source_manifest"]]
        assert "gold_policy" in keys
        assert "gold_spot_quote" in keys
        assert "gold_derivatives" in keys

    def test_unknown_chart_snapshot_returns_404(self):
        with _client() as client:
            resp = client.get("/api/v1/gold/workbench/charts/does-not-exist")
        assert resp.status_code == 404
