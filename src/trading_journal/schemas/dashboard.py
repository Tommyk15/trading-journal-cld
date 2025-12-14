"""Schemas for dashboard summary and metrics."""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field

from .analytics import StrategyStats, UnderlyingStats


class TimePeriod(str, Enum):
    """Time period for filtering metrics."""

    ALL = "all"
    YTD = "ytd"
    MONTHLY = "monthly"
    WEEKLY = "weekly"


class PortfolioGreeksSummary(BaseModel):
    """Aggregated Greeks across all open positions."""

    total_delta: Decimal = Field(..., description="Sum of delta across all positions")
    total_gamma: Decimal = Field(..., description="Sum of gamma across all positions")
    total_theta: Decimal = Field(..., description="Sum of theta across all positions")
    total_vega: Decimal = Field(..., description="Sum of vega across all positions")
    position_count: int = Field(..., description="Number of positions with Greeks")
    last_updated: datetime | None = Field(None, description="Timestamp of most recent Greeks data")


class StreakInfo(BaseModel):
    """Information about win/loss streaks."""

    max_consecutive_wins: int = Field(..., description="Maximum consecutive winning trades")
    max_consecutive_losses: int = Field(..., description="Maximum consecutive losing trades")
    current_streak: int = Field(..., description="Current streak length")
    current_streak_type: str = Field(..., description="Current streak type: 'win', 'loss', or 'none'")


class DashboardSummary(BaseModel):
    """Comprehensive dashboard summary with all key metrics."""

    # Core metrics
    total_pnl: Decimal = Field(..., description="Total realized P&L")
    total_trades: int = Field(..., description="Total number of closed trades")
    win_rate: float = Field(..., description="Win rate percentage")
    avg_winner: Decimal = Field(..., description="Average winning trade P&L")
    avg_loser: Decimal = Field(..., description="Average losing trade P&L (absolute)")
    profit_factor: float | None = Field(None, description="Profit factor (total wins / total losses)")
    max_drawdown_percent: float = Field(..., description="Maximum drawdown percentage")

    # Daily metrics
    avg_profit_per_day: Decimal = Field(..., description="Average profit per trading day")
    trading_days: int = Field(..., description="Number of trading days")

    # Best/Worst performers
    best_strategy: StrategyStats | None = Field(None, description="Best performing strategy by P&L")
    worst_strategy: StrategyStats | None = Field(None, description="Worst performing strategy by P&L")
    best_ticker: UnderlyingStats | None = Field(None, description="Best performing ticker by P&L")
    worst_ticker: UnderlyingStats | None = Field(None, description="Worst performing ticker by P&L")

    # Risk metrics
    sharpe_ratio: float | None = Field(None, description="Sharpe ratio")
    sortino_ratio: float | None = Field(None, description="Sortino ratio (downside deviation)")
    expectancy: Decimal = Field(..., description="Expected value per trade")

    # Streak info
    streak_info: StreakInfo = Field(..., description="Win/loss streak information")

    # Portfolio Greeks
    portfolio_greeks: PortfolioGreeksSummary | None = Field(
        None, description="Aggregated Greeks for open positions"
    )


class MetricsTimePoint(BaseModel):
    """Single point in the metrics time series."""

    date: date_type = Field(..., description="Date of the data point")
    cumulative_pnl: Decimal = Field(..., description="Cumulative P&L up to this date")
    trade_count: int = Field(..., description="Cumulative trade count up to this date")
    win_rate: float = Field(..., description="Rolling win rate up to this date")
    profit_factor: float | None = Field(None, description="Rolling profit factor up to this date")
    drawdown_percent: float = Field(..., description="Drawdown percentage at this date")


class MetricsTimeSeriesResponse(BaseModel):
    """Response containing metrics time series for charts."""

    data_points: list[MetricsTimePoint] = Field(..., description="Time series data points")
    period: TimePeriod = Field(..., description="Time period for the data")
    start_date: date_type | None = Field(None, description="Start date of the data")
    end_date: date_type | None = Field(None, description="End date of the data")
