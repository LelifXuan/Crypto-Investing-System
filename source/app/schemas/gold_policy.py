"""Gold policy write schemas — POST /gold/policy request/response.

The gold-allocation page read path (``gold_policy_versions`` → latest
version → workbench decisions) had no write counterpart: the only writer
of this table was a test fixture. This module declares the request
contract for creating the next versioned policy row.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class GoldPolicyWriteRequest(BaseModel):
    """One versioned gold allocation policy.

    All money fields are in ``base_currency``. The endpoint stores them
    as ``Numeric`` (AGENTS.md §三: no float for money); floats here are
    the JSON transport only and are converted to ``Decimal`` at the
    service boundary.
    """

    base_currency: str = Field(default="USD", min_length=1, max_length=16)
    portfolio_total: float = Field(gt=0)
    gold_current_value: float = Field(ge=0)
    available_cash: float | None = Field(default=None, ge=0)
    target_min: float = Field(ge=0, le=1)
    target_max: float = Field(ge=0, le=1)
    base_dca_amount: float = Field(gt=0)
    fixed_dip_add_amount: float = Field(gt=0)
    cooldown_days: int = Field(default=14, ge=0, le=365)
    quote_max_age_seconds: int = Field(default=300, ge=30, le=86400)
    confirmations_required: int = Field(default=3, ge=1, le=10)
    drawdown_threshold: float = Field(default=0.08, ge=0, le=1)
    pause_base_when_overweight: bool = False

    @model_validator(mode="after")
    def check_ranges(self) -> "GoldPolicyWriteRequest":
        if self.target_min > self.target_max:
            raise ValueError("target_min must not exceed target_max")
        if self.gold_current_value > self.portfolio_total:
            raise ValueError("gold_current_value must not exceed portfolio_total")
        return self


class GoldPolicyWriteRead(BaseModel):
    policy_id: str
    version: int
    base_currency: str
    portfolio_total: str
    gold_current_value: str
    available_cash: str | None
    target_min: str
    target_max: str
    base_dca_amount: str
    fixed_dip_add_amount: str
    cooldown_days: int
    quote_max_age_seconds: int
    confirmations_required: int
    drawdown_threshold: str
    pause_base_when_overweight: bool
