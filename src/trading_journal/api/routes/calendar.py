"""API routes for calendar data aggregation."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.core.database import get_db
from trading_journal.schemas.calendar import (
    CalendarDayExpirations,
    CalendarDayTrades,
    DayOfWeekAnalysisResponse,
    DayOfWeekStats,
    ExpirationCalendarResponse,
    ExpirationDate,
    MonthlySummary,
    TradesCalendarResponse,
    TradeSummary,
    UpcomingExpirationsResponse,
    WeeklyStats,
    WeeklyStatsResponse,
)
from trading_journal.services.calendar_service import CalendarService

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("/upcoming-expirations", response_model=UpcomingExpirationsResponse)
async def get_upcoming_expirations(
    days_ahead: int = Query(30, ge=1, le=365, description="Days to look ahead"),
    underlying: Optional[str] = Query(None, description="Filter by underlying symbol"),
    session: AsyncSession = Depends(get_db),
):
    """Get upcoming option expirations.

    Returns positions that will expire within the specified number of days,
    useful for monitoring positions that need attention.

    Args:
        days_ahead: Number of days to look ahead
        underlying: Optional filter by underlying
        session: Database session

    Returns:
        Upcoming expirations
    """
    service = CalendarService(session)
    expirations = await service.get_upcoming_expirations(
        days_ahead=days_ahead,
        underlying=underlying,
    )

    return UpcomingExpirationsResponse(
        expirations=[ExpirationDate(**exp) for exp in expirations],
        total_expirations=len(expirations),
    )


@router.get("/trades-by-week", response_model=WeeklyStatsResponse)
async def get_trades_by_week(
    year: int = Query(..., description="Year to analyze"),
    underlying: Optional[str] = Query(None, description="Filter by underlying symbol"),
    strategy_type: Optional[str] = Query(None, description="Filter by strategy type"),
    session: AsyncSession = Depends(get_db),
):
    """Get trades grouped by week.

    Provides weekly performance statistics for the specified year,
    useful for identifying patterns and trends.

    Args:
        year: Year to analyze
        underlying: Optional filter by underlying
        strategy_type: Optional filter by strategy
        session: Database session

    Returns:
        Weekly statistics
    """
    service = CalendarService(session)
    weeks = await service.get_trades_by_week(
        year=year,
        underlying=underlying,
        strategy_type=strategy_type,
    )

    return WeeklyStatsResponse(
        weeks=[WeeklyStats(**week) for week in weeks],
        total_weeks=len(weeks),
    )


@router.get("/trades-calendar", response_model=TradesCalendarResponse)
async def get_trades_calendar(
    start_date: str = Query(..., description="Start date (ISO format)"),
    end_date: str = Query(..., description="End date (ISO format)"),
    underlying: Optional[str] = Query(None, description="Filter by underlying symbol"),
    session: AsyncSession = Depends(get_db),
):
    """Get calendar view of trades.

    Returns trades organized by date, useful for building calendar
    visualizations and understanding trading activity patterns.

    Args:
        start_date: Start date
        end_date: End date
        underlying: Optional filter by underlying
        session: Database session

    Returns:
        Calendar view of trades
    """
    from datetime import datetime

    start_dt = datetime.fromisoformat(start_date)
    end_dt = datetime.fromisoformat(end_date)

    service = CalendarService(session)
    calendar_data = await service.get_trades_calendar(
        start_date=start_dt,
        end_date=end_dt,
        underlying=underlying,
    )

    # Convert to response format
    formatted_calendar = {}
    for date_str, day_data in calendar_data.items():
        formatted_calendar[date_str] = CalendarDayTrades(
            date=day_data["date"],
            trades_count=day_data["trades_count"],
            total_pnl=day_data["total_pnl"],
            trades=[TradeSummary(**t) for t in day_data["trades"]],
        )

    return TradesCalendarResponse(
        calendar=formatted_calendar,
        total_days=len(formatted_calendar),
    )


@router.get("/expiration-calendar", response_model=ExpirationCalendarResponse)
async def get_expiration_calendar(
    start_date: str = Query(..., description="Start date (ISO format)"),
    end_date: str = Query(..., description="End date (ISO format)"),
    underlying: Optional[str] = Query(None, description="Filter by underlying symbol"),
    session: AsyncSession = Depends(get_db),
):
    """Get calendar view of option expirations.

    Returns positions organized by expiration date, useful for
    visualizing when positions expire.

    Args:
        start_date: Start date
        end_date: End date
        underlying: Optional filter by underlying
        session: Database session

    Returns:
        Calendar view of expirations
    """
    from datetime import datetime

    start_dt = datetime.fromisoformat(start_date)
    end_dt = datetime.fromisoformat(end_date)

    service = CalendarService(session)
    calendar_data = await service.get_expiration_calendar(
        start_date=start_dt,
        end_date=end_dt,
        underlying=underlying,
    )

    # Convert to response format
    formatted_calendar = {}
    for date_str, day_data in calendar_data.items():
        formatted_calendar[date_str] = CalendarDayExpirations(
            date=day_data["date"],
            positions_count=day_data["positions_count"],
            total_quantity=day_data["total_quantity"],
            positions=day_data["positions"],
        )

    return ExpirationCalendarResponse(
        calendar=formatted_calendar,
        total_days=len(formatted_calendar),
    )


@router.get("/monthly-summary", response_model=MonthlySummary)
async def get_monthly_summary(
    year: int = Query(..., description="Year"),
    month: int = Query(..., ge=1, le=12, description="Month (1-12)"),
    underlying: Optional[str] = Query(None, description="Filter by underlying symbol"),
    session: AsyncSession = Depends(get_db),
):
    """Get detailed summary for a specific month.

    Provides comprehensive statistics for a month including trades,
    expirations, and performance metrics.

    Args:
        year: Year
        month: Month (1-12)
        underlying: Optional filter by underlying
        session: Database session

    Returns:
        Monthly summary
    """
    service = CalendarService(session)
    summary = await service.get_monthly_summary(
        year=year,
        month=month,
        underlying=underlying,
    )

    return MonthlySummary(**summary)


@router.get("/day-of-week-analysis", response_model=DayOfWeekAnalysisResponse)
async def get_day_of_week_analysis(
    underlying: Optional[str] = Query(None, description="Filter by underlying symbol"),
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    session: AsyncSession = Depends(get_db),
):
    """Analyze performance by day of week.

    Shows which days of the week are most profitable,
    useful for identifying patterns in trading performance.

    Args:
        underlying: Optional filter by underlying
        start_date: Optional start date filter
        end_date: Optional end date filter
        session: Database session

    Returns:
        Day of week analysis
    """
    from datetime import datetime

    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None

    service = CalendarService(session)
    stats = await service.get_day_of_week_analysis(
        underlying=underlying,
        start_date=start_dt,
        end_date=end_dt,
    )

    return DayOfWeekAnalysisResponse(
        days=[DayOfWeekStats(**day) for day in stats],
    )
