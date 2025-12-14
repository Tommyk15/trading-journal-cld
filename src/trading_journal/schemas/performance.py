"""Schemas for performance metrics and time-series data."""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class CumulativePnLPoint(BaseModel):
    """Single point in cumulative P&L time series."""

    timestamp: datetime = Field(..., description="Trade close timestamp")
    trade_id: int = Field(..., description="Trade ID")
    trade_pnl: Decimal = Field(..., description="P&L for this trade")
    cumulative_pnl: Decimal = Field(..., description="Cumulative P&L up to this point")
    underlying: str = Field(..., description="Underlying symbol")
    strategy_type: str = Field(..., description="Strategy type")


class CumulativePnLResponse(BaseModel):
    """Response containing cumulative P&L time series."""

    data_points: list[CumulativePnLPoint] = Field(..., description="Time series data")
    total_trades: int = Field(..., description="Total number of trades")


class DailyPnLPoint(BaseModel):
    """Single point in daily P&L time series."""

    date: date_type = Field(..., description="Date")
    trades_count: int = Field(..., description="Number of trades on this day")
    daily_pnl: Decimal = Field(..., description="P&L for this day")
    cumulative_pnl: Decimal = Field(..., description="Cumulative P&L up to this day")
    winning_trades: int = Field(..., description="Number of winning trades")
    losing_trades: int = Field(..., description="Number of losing trades")


class DailyPnLResponse(BaseModel):
    """Response containing daily P&L time series."""

    data_points: list[DailyPnLPoint] = Field(..., description="Daily time series data")
    total_days: int = Field(..., description="Total number of trading days")


class DrawdownAnalysis(BaseModel):
    """Drawdown analysis and statistics."""

    max_drawdown: Decimal = Field(..., description="Maximum drawdown amount")
    max_drawdown_percentage: float = Field(..., description="Maximum drawdown as percentage")
    current_drawdown: Decimal = Field(..., description="Current drawdown amount")
    current_drawdown_percentage: float = Field(..., description="Current drawdown as percentage")
    peak_equity: Decimal = Field(..., description="Peak equity level")
    current_equity: Decimal = Field(..., description="Current equity level")


class SharpeRatioAnalysis(BaseModel):
    """Sharpe ratio and risk-adjusted metrics."""

    sharpe_ratio: float | None = Field(None, description="Sharpe ratio")
    average_daily_return: Decimal = Field(..., description="Average daily return")
    daily_volatility: Decimal = Field(..., description="Daily volatility (std dev)")
    annualized_return: Decimal = Field(..., description="Annualized return")
    annualized_volatility: Decimal = Field(..., description="Annualized volatility")
    total_days: int = Field(..., description="Number of trading days analyzed")


class StrategyProfitCurvePoint(BaseModel):
    """Single point in a strategy profit curve."""

    timestamp: datetime = Field(..., description="Trade close timestamp")
    trade_id: int = Field(..., description="Trade ID")
    trade_pnl: Decimal = Field(..., description="P&L for this trade")
    cumulative_pnl: Decimal = Field(..., description="Cumulative P&L for this strategy")


class StrategyProfitCurve(BaseModel):
    """Profit curve for a single strategy."""

    total_trades: int = Field(..., description="Total trades for this strategy")
    final_pnl: Decimal = Field(..., description="Final cumulative P&L")
    curve: list[StrategyProfitCurvePoint] = Field(..., description="Time series data")


class StrategyProfitCurvesResponse(BaseModel):
    """Response containing profit curves for all strategies."""

    strategies: dict[str, StrategyProfitCurve] = Field(
        ..., description="Mapping of strategy types to their profit curves"
    )


class EquityCurveSummary(BaseModel):
    """Summary of equity curve with key metrics."""

    total_trades: int = Field(..., description="Total number of trades")
    starting_equity: Decimal = Field(..., description="Starting equity (usually 0)")
    ending_equity: Decimal = Field(..., description="Ending equity")
    total_return: Decimal = Field(..., description="Total return")
    data_points: int = Field(..., description="Number of data points in curve")
    first_trade_date: datetime | None = Field(None, description="Date of first trade")
    last_trade_date: datetime | None = Field(None, description="Date of last trade")
