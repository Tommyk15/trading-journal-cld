"""Schemas for calendar data aggregation."""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class PositionSummary(BaseModel):
    """Summary of a position for calendar views."""

    id: int
    underlying: str
    option_type: Optional[str]
    strike: Optional[Decimal]
    quantity: int
    unrealized_pnl: Decimal


class ExpirationDate(BaseModel):
    """Details about an expiration date."""

    expiration_date: date_type = Field(..., description="Expiration date")
    days_until_expiration: int = Field(..., description="Days until expiration")
    total_positions: int = Field(..., description="Number of positions expiring")
    underlyings: list[str] = Field(..., description="List of underlying symbols")
    positions: list[PositionSummary] = Field(..., description="Positions expiring on this date")


class UpcomingExpirationsResponse(BaseModel):
    """Response containing upcoming expirations."""

    expirations: list[ExpirationDate] = Field(..., description="List of upcoming expirations")
    total_expirations: int = Field(..., description="Total number of expiration dates")


class WeeklyStats(BaseModel):
    """Statistics for a specific week."""

    week: str = Field(..., description="Week in YYYY-Www format")
    total_trades: int = Field(..., description="Total trades")
    winning_trades: int = Field(..., description="Winning trades")
    losing_trades: int = Field(..., description="Losing trades")
    total_pnl: Decimal = Field(..., description="Total P&L")
    win_rate: float = Field(..., description="Win rate percentage")


class WeeklyStatsResponse(BaseModel):
    """Response containing weekly statistics."""

    weeks: list[WeeklyStats] = Field(..., description="List of weekly statistics")
    total_weeks: int = Field(..., description="Total number of weeks")


class TradeSummary(BaseModel):
    """Summary of a trade for calendar views."""

    id: int
    underlying: str
    strategy_type: str
    opened_at: datetime
    closed_at: datetime
    realized_pnl: Decimal
    num_legs: int


class CalendarDayTrades(BaseModel):
    """Trades for a specific calendar day."""

    date: date_type = Field(..., description="Date")
    trades_count: int = Field(..., description="Number of trades")
    total_pnl: Decimal = Field(..., description="Total P&L for the day")
    trades: list[TradeSummary] = Field(..., description="Trades closed on this day")


class TradesCalendarResponse(BaseModel):
    """Response containing calendar view of trades."""

    calendar: dict[str, CalendarDayTrades] = Field(
        ..., description="Dictionary mapping date strings to trade data"
    )
    total_days: int = Field(..., description="Total number of days with trades")


class CalendarDayExpirations(BaseModel):
    """Expirations for a specific calendar day."""

    date: date_type = Field(..., description="Date")
    positions_count: int = Field(..., description="Number of positions expiring")
    total_quantity: int = Field(..., description="Total quantity expiring")
    positions: list[PositionSummary] = Field(..., description="Positions expiring on this day")


class ExpirationCalendarResponse(BaseModel):
    """Response containing calendar view of expirations."""

    calendar: dict[str, CalendarDayExpirations] = Field(
        ..., description="Dictionary mapping date strings to expiration data"
    )
    total_days: int = Field(..., description="Total number of days with expirations")


class MonthlySummary(BaseModel):
    """Summary statistics for a specific month."""

    year: int = Field(..., description="Year")
    month: int = Field(..., description="Month (1-12)")
    total_trades: int = Field(..., description="Total trades")
    winning_trades: int = Field(..., description="Winning trades")
    losing_trades: int = Field(..., description="Losing trades")
    win_rate: float = Field(..., description="Win rate percentage")
    total_pnl: Decimal = Field(..., description="Total P&L")
    total_commission: Decimal = Field(..., description="Total commission")
    net_pnl: Decimal = Field(..., description="Net P&L after commission")
    positions_expiring: int = Field(..., description="Positions expiring this month")
    unique_underlyings_traded: int = Field(..., description="Number of unique underlyings traded")


class DayOfWeekStats(BaseModel):
    """Statistics for a specific day of week."""

    day_of_week: str = Field(..., description="Day name (Monday, Tuesday, etc.)")
    day_number: int = Field(..., description="Day number (0=Monday, 6=Sunday)")
    total_trades: int = Field(..., description="Total trades")
    winning_trades: int = Field(..., description="Winning trades")
    losing_trades: int = Field(..., description="Losing trades")
    win_rate: float = Field(..., description="Win rate percentage")
    total_pnl: Decimal = Field(..., description="Total P&L")
    average_pnl: Decimal = Field(..., description="Average P&L per trade")


class DayOfWeekAnalysisResponse(BaseModel):
    """Response containing day of week analysis."""

    days: list[DayOfWeekStats] = Field(..., description="Statistics by day of week")
