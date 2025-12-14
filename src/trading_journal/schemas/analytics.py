"""Schemas for trade analytics and statistics."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class AnalyticsRequest(BaseModel):
    """Request for analytics data."""

    underlying: str | None = Field(None, description="Filter by underlying symbol")
    strategy_type: str | None = Field(None, description="Filter by strategy type")
    start_date: datetime | None = Field(None, description="Start date for analysis")
    end_date: datetime | None = Field(None, description="End date for analysis")


class WinRateStats(BaseModel):
    """Win rate statistics."""

    total_trades: int = Field(..., description="Total number of trades")
    winning_trades: int = Field(..., description="Number of winning trades")
    losing_trades: int = Field(..., description="Number of losing trades")
    breakeven_trades: int = Field(..., description="Number of breakeven trades")
    win_rate: float = Field(..., description="Win rate percentage")
    average_win: Decimal = Field(..., description="Average winning trade P&L")
    average_loss: Decimal = Field(..., description="Average losing trade P&L (absolute)")
    largest_win: Decimal = Field(..., description="Largest winning trade")
    largest_loss: Decimal = Field(..., description="Largest losing trade")
    profit_factor: float | None = Field(None, description="Profit factor (total wins / total losses)")


class StrategyStats(BaseModel):
    """Statistics for a specific strategy."""

    strategy_type: str = Field(..., description="Strategy type")
    total_trades: int = Field(..., description="Total trades for this strategy")
    winning_trades: int = Field(..., description="Winning trades")
    losing_trades: int = Field(..., description="Losing trades")
    win_rate: float = Field(..., description="Win rate percentage")
    total_pnl: Decimal = Field(..., description="Total P&L")
    total_commission: Decimal = Field(..., description="Total commission paid")
    net_pnl: Decimal = Field(..., description="Net P&L after commission")
    average_pnl: Decimal = Field(..., description="Average P&L per trade")


class StrategyBreakdown(BaseModel):
    """Breakdown of performance by strategy."""

    strategies: list[StrategyStats] = Field(..., description="List of strategy statistics")
    total_trades: int = Field(..., description="Total trades across all strategies")


class UnderlyingStats(BaseModel):
    """Statistics for a specific underlying."""

    underlying: str = Field(..., description="Underlying symbol")
    total_trades: int = Field(..., description="Total trades for this underlying")
    winning_trades: int = Field(..., description="Winning trades")
    losing_trades: int = Field(..., description="Losing trades")
    win_rate: float = Field(..., description="Win rate percentage")
    total_pnl: Decimal = Field(..., description="Total P&L")
    total_commission: Decimal = Field(..., description="Total commission paid")
    net_pnl: Decimal = Field(..., description="Net P&L after commission")
    average_pnl: Decimal = Field(..., description="Average P&L per trade")


class UnderlyingBreakdown(BaseModel):
    """Breakdown of performance by underlying."""

    underlyings: list[UnderlyingStats] = Field(..., description="List of underlying statistics")
    total_trades: int = Field(..., description="Total trades across all underlyings")


class MonthlyStats(BaseModel):
    """Statistics for a specific month."""

    month: str = Field(..., description="Month in YYYY-MM format")
    total_trades: int = Field(..., description="Total trades for this month")
    winning_trades: int = Field(..., description="Winning trades")
    losing_trades: int = Field(..., description="Losing trades")
    win_rate: float = Field(..., description="Win rate percentage")
    total_pnl: Decimal = Field(..., description="Total P&L")
    total_commission: Decimal = Field(..., description="Total commission paid")
    net_pnl: Decimal = Field(..., description="Net P&L after commission")


class MonthlyPerformance(BaseModel):
    """Monthly performance breakdown."""

    months: list[MonthlyStats] = Field(..., description="List of monthly statistics")
    total_months: int = Field(..., description="Number of months")


class TradeDurationStats(BaseModel):
    """Statistics about trade durations."""

    total_trades: int = Field(..., description="Total number of trades analyzed")
    average_duration_hours: float = Field(..., description="Average trade duration in hours")
    shortest_duration_hours: float = Field(..., description="Shortest trade duration")
    longest_duration_hours: float = Field(..., description="Longest trade duration")
