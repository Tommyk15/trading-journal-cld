"""Schemas for trade analytics data."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class LegGreeksResponse(BaseModel):
    """Greeks data for a single trade leg."""

    leg_index: int = Field(..., description="Leg index (0-based)")
    option_type: str | None = Field(None, description="C for call, P for put")
    strike: Decimal | None = Field(None, description="Strike price")
    expiration: datetime | None = Field(None, description="Expiration date")
    quantity: int = Field(..., description="Signed quantity")

    delta: Decimal | None = Field(None, description="Delta")
    gamma: Decimal | None = Field(None, description="Gamma")
    theta: Decimal | None = Field(None, description="Theta")
    vega: Decimal | None = Field(None, description="Vega")
    rho: Decimal | None = Field(None, description="Rho")
    iv: Decimal | None = Field(None, description="Implied volatility")

    underlying_price: Decimal | None = Field(None, description="Underlying price")
    option_price: Decimal | None = Field(None, description="Option price")
    bid: Decimal | None = Field(None, description="Bid price")
    ask: Decimal | None = Field(None, description="Ask price")
    bid_ask_spread: Decimal | None = Field(None, description="Bid-ask spread")
    open_interest: int | None = Field(None, description="Open interest")
    volume: int | None = Field(None, description="Volume")

    data_source: str | None = Field(None, description="Data source (IBKR, POLYGON)")
    captured_at: datetime | None = Field(None, description="Timestamp of capture")

    model_config = ConfigDict(from_attributes=True)


class TradeAnalyticsResponse(BaseModel):
    """Complete analytics for a trade."""

    trade_id: int = Field(..., description="Trade ID")
    underlying: str = Field(..., description="Underlying symbol")
    strategy_type: str = Field(..., description="Strategy type")
    status: str = Field(..., description="Trade status")

    # Net Greeks
    net_delta: Decimal | None = Field(None, description="Net delta across all legs")
    net_gamma: Decimal | None = Field(None, description="Net gamma across all legs")
    net_theta: Decimal | None = Field(None, description="Net theta across all legs")
    net_vega: Decimal | None = Field(None, description="Net vega across all legs")

    # IV metrics
    trade_iv: Decimal | None = Field(None, description="Trade-level IV")
    iv_percentile_52w: Decimal | None = Field(None, description="52-week IV percentile")
    iv_rank_52w: Decimal | None = Field(None, description="52-week IV rank")
    iv_percentile_custom: Decimal | None = Field(None, description="Custom period IV percentile")
    iv_rank_custom: Decimal | None = Field(None, description="Custom period IV rank")

    # Risk analytics
    pop: Decimal | None = Field(None, description="Probability of profit (0-100)")
    breakevens: list[Decimal] = Field(default_factory=list, description="Breakeven prices")
    max_profit: Decimal | None = Field(None, description="Maximum profit")
    max_risk: Decimal | None = Field(None, description="Maximum risk")
    risk_reward_ratio: Decimal | None = Field(None, description="Risk/reward ratio")
    pnl_percent: Decimal | None = Field(None, description="P&L as % of max profit")

    # Collateral
    collateral_calculated: Decimal | None = Field(None, description="Calculated collateral")
    collateral_ibkr: Decimal | None = Field(None, description="IBKR reported margin")

    # Time
    dte: int | None = Field(None, description="Days to expiration")
    days_held: int | None = Field(None, description="Days position held")

    # Metadata
    greeks_source: str | None = Field(None, description="Source of Greeks data")
    greeks_pending: bool = Field(False, description="Whether Greeks fetch is pending")
    underlying_price: Decimal | None = Field(None, description="Current underlying price")


class TradeLegsResponse(BaseModel):
    """Response with leg-level Greeks for a trade."""

    trade_id: int = Field(..., description="Trade ID")
    snapshot_type: str = Field(..., description="OPEN or CLOSE")
    legs: list[LegGreeksResponse] = Field(..., description="List of leg Greeks")
    captured_at: datetime | None = Field(None, description="Timestamp of capture")


class FetchGreeksRequest(BaseModel):
    """Request to fetch Greeks for a trade."""

    source: str | None = Field(
        "POLYGON", description="Data source (POLYGON or IBKR)"
    )
    force_refresh: bool = Field(
        False, description="Force refresh even if data exists"
    )


class FetchGreeksResponse(BaseModel):
    """Response from fetching Greeks."""

    trade_id: int = Field(..., description="Trade ID")
    success: bool = Field(..., description="Whether fetch succeeded")
    legs_fetched: int = Field(0, description="Number of legs fetched")
    source: str | None = Field(None, description="Data source used")
    message: str = Field(..., description="Status message")


class BatchFetchResponse(BaseModel):
    """Response from batch fetching pending Greeks."""

    trades_processed: int = Field(..., description="Number of trades processed")
    trades_succeeded: int = Field(..., description="Number of successful fetches")
    trades_failed: int = Field(..., description="Number of failed fetches")
    message: str = Field(..., description="Status message")


class MarginSettingsResponse(BaseModel):
    """Margin settings for an underlying."""

    id: int = Field(..., description="Settings ID")
    underlying: str = Field(..., description="Underlying symbol")
    naked_put_margin_pct: Decimal = Field(..., description="Naked put margin %")
    naked_call_margin_pct: Decimal = Field(..., description="Naked call margin %")
    spread_margin_pct: Decimal = Field(..., description="Spread margin %")
    iron_condor_margin_pct: Decimal = Field(..., description="Iron condor margin %")
    notes: str | None = Field(None, description="Notes")
    created_at: datetime = Field(..., description="Created timestamp")
    updated_at: datetime = Field(..., description="Updated timestamp")

    model_config = ConfigDict(from_attributes=True)


class MarginSettingsCreate(BaseModel):
    """Request to create margin settings."""

    underlying: str = Field(..., description="Underlying symbol")
    naked_put_margin_pct: Decimal = Field(
        default=Decimal("20.00"), description="Naked put margin %"
    )
    naked_call_margin_pct: Decimal = Field(
        default=Decimal("20.00"), description="Naked call margin %"
    )
    spread_margin_pct: Decimal = Field(
        default=Decimal("100.00"), description="Spread margin %"
    )
    iron_condor_margin_pct: Decimal = Field(
        default=Decimal("100.00"), description="Iron condor margin %"
    )
    notes: str | None = Field(None, description="Notes")


class MarginSettingsUpdate(BaseModel):
    """Request to update margin settings."""

    naked_put_margin_pct: Decimal | None = Field(None, description="Naked put margin %")
    naked_call_margin_pct: Decimal | None = Field(None, description="Naked call margin %")
    spread_margin_pct: Decimal | None = Field(None, description="Spread margin %")
    iron_condor_margin_pct: Decimal | None = Field(None, description="Iron condor margin %")
    notes: str | None = Field(None, description="Notes")


class MarginSettingsList(BaseModel):
    """List of margin settings."""

    settings: list[MarginSettingsResponse] = Field(..., description="Margin settings")
    total: int = Field(..., description="Total count")
