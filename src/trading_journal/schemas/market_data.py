"""Schemas for market data API responses."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class LegMarketData(BaseModel):
    """Market data for a single leg of a position."""

    strike: float | None = Field(None, description="Strike price (None for stocks)")
    expiration: str | None = Field(None, description="Expiration date (None for stocks)")
    option_type: str | None = Field(None, description="C or P (None for stocks)")
    security_type: str = Field("OPT", description="OPT or STK")
    quantity: int
    price: float | None = Field(None, description="Current option price (mid or last)")
    market_value: float | None = Field(None, description="Leg market value")
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    iv: float | None = Field(None, description="Implied volatility")
    source: str = Field(..., description="Data source (IBKR, POLYGON, YFINANCE)")


class PositionMarketDataResponse(BaseModel):
    """Market data for a single trade/position."""

    trade_id: int
    underlying: str
    underlying_price: float | None = Field(None, description="Current underlying price")
    legs: list[LegMarketData] = Field(default_factory=list)
    total_market_value: float | None = Field(None, description="Total position market value")
    total_cost_basis: float = Field(..., description="Total cost basis")
    unrealized_pnl: float | None = Field(None, description="Unrealized P&L in dollars")
    unrealized_pnl_percent: float | None = Field(None, description="Unrealized P&L percentage")
    net_delta: float | None = None
    net_gamma: float | None = None
    net_theta: float | None = None
    net_vega: float | None = None
    source: str = Field(..., description="Primary data source")
    timestamp: datetime = Field(..., description="Data timestamp")
    is_stale: bool = Field(False, description="True if data is from cache")


class PositionsMarketDataResponse(BaseModel):
    """Market data for all open positions."""

    positions: list[PositionMarketDataResponse] = Field(
        default_factory=list, description="Market data for each position"
    )
    net_unrealized_pnl: float | None = Field(None, description="Net unrealized P&L across all positions")
    net_unrealized_pnl_percent: float | None = Field(None, description="Net unrealized P&L percentage")
    total_market_value: float | None = Field(None, description="Total market value of all positions")
    total_cost_basis: float = Field(..., description="Total cost basis of all positions")
    total_delta: float | None = Field(None, description="Portfolio net delta")
    total_theta: float | None = Field(None, description="Portfolio net theta")
    ibkr_connected: bool = Field(..., description="Whether IBKR is connected")
    source: str = Field(..., description="Primary data source used")
    timestamp: datetime = Field(..., description="Data timestamp")
    cache_status: str = Field(..., description="Cache status: fresh, stale, or partial")


class StockQuoteResponse(BaseModel):
    """Stock quote response."""

    symbol: str
    price: float | None = None
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    close: float | None = None
    volume: int | None = None
    source: str


class OptionQuoteResponse(BaseModel):
    """Option quote response."""

    symbol: str
    underlying: str
    strike: float
    expiration: str
    option_type: str
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    mid: float | None = None
    volume: int | None = None
    open_interest: int | None = None
    source: str


class OptionGreeksResponse(BaseModel):
    """Option Greeks response."""

    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    rho: float | None = None
    iv: float | None = None
    source: str


class OptionDataResponse(BaseModel):
    """Combined option quote and Greeks response."""

    quote: OptionQuoteResponse
    greeks: OptionGreeksResponse


class AccountPnLResponse(BaseModel):
    """Account-level P&L response (IBKR only)."""

    account: str | None = None
    daily_pnl: float | None = None
    unrealized_pnl: float | None = None
    realized_pnl: float | None = None
    connected: bool = Field(..., description="Whether IBKR is connected")


class PortfolioPositionResponse(BaseModel):
    """Portfolio position from IBKR."""

    symbol: str
    underlying: str
    security_type: str
    strike: float | None = None
    expiration: str | None = None
    option_type: str | None = None
    position: int
    market_price: float | None = None
    market_value: float
    avg_cost: float
    unrealized_pnl: float
    realized_pnl: float


class PortfolioResponse(BaseModel):
    """Portfolio response from IBKR."""

    positions: list[PortfolioPositionResponse] = Field(default_factory=list)
    total_market_value: float = Field(..., description="Total market value")
    total_unrealized_pnl: float = Field(..., description="Total unrealized P&L")
    connected: bool = Field(..., description="Whether IBKR is connected")
    timestamp: datetime
