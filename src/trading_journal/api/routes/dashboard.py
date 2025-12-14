"""API routes for dashboard summary and metrics."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.core.database import get_db
from trading_journal.schemas.dashboard import (
    DashboardSummary,
    MetricsTimeSeriesResponse,
    TimePeriod,
)
from trading_journal.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
async def get_dashboard_summary(
    period: TimePeriod = Query(TimePeriod.ALL, description="Time period filter"),
    start_date: str | None = Query(None, description="Start date (ISO format, overrides period)"),
    end_date: str | None = Query(None, description="End date (ISO format, overrides period)"),
    session: AsyncSession = Depends(get_db),
):
    """Get comprehensive dashboard summary.

    Aggregates all key trading metrics including:
    - Core metrics: P&L, trades, win rate, profit factor
    - Risk metrics: Sharpe ratio, Sortino ratio, drawdown
    - Performance: Best/worst strategy and ticker
    - Portfolio Greeks: Aggregated delta, gamma, theta, vega

    Args:
        period: Time period (all, ytd, monthly, weekly)
        start_date: Optional explicit start date (overrides period)
        end_date: Optional explicit end date (overrides period)
        session: Database session

    Returns:
        Comprehensive dashboard summary
    """
    from datetime import datetime

    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None

    service = DashboardService(session)
    summary = await service.get_summary(
        period=period,
        start_date=start_dt,
        end_date=end_dt,
    )

    return summary


@router.get("/metrics-timeseries", response_model=MetricsTimeSeriesResponse)
async def get_metrics_timeseries(
    period: TimePeriod = Query(TimePeriod.ALL, description="Time period filter"),
    start_date: str | None = Query(None, description="Start date (ISO format, overrides period)"),
    end_date: str | None = Query(None, description="End date (ISO format, overrides period)"),
    session: AsyncSession = Depends(get_db),
):
    """Get metrics time series for charts.

    Returns time series data for:
    - Cumulative P&L
    - Rolling win rate
    - Rolling profit factor
    - Drawdown percentage

    Args:
        period: Time period (all, ytd, monthly, weekly)
        start_date: Optional explicit start date (overrides period)
        end_date: Optional explicit end date (overrides period)
        session: Database session

    Returns:
        Time series data for dashboard charts
    """
    from datetime import datetime

    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None

    service = DashboardService(session)
    timeseries = await service.get_metrics_timeseries(
        period=period,
        start_date=start_dt,
        end_date=end_dt,
    )

    return timeseries
