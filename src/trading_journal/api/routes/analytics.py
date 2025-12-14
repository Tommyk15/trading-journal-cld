"""API routes for trade analytics and statistics."""


from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.core.database import get_db
from trading_journal.schemas.analytics import (
    MonthlyPerformance,
    MonthlyStats,
    StrategyBreakdown,
    StrategyStats,
    TradeDurationStats,
    UnderlyingBreakdown,
    UnderlyingStats,
    WinRateStats,
)
from trading_journal.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/win-rate", response_model=WinRateStats)
async def get_win_rate(
    underlying: str | None = Query(None, description="Filter by underlying symbol"),
    strategy_type: str | None = Query(None, description="Filter by strategy type"),
    start_date: str | None = Query(None, description="Start date (ISO format)"),
    end_date: str | None = Query(None, description="End date (ISO format)"),
    session: AsyncSession = Depends(get_db),
):
    """Get win rate and related statistics.

    Calculates the percentage of winning trades, average wins/losses,
    and other performance metrics.

    Args:
        underlying: Optional filter by underlying
        strategy_type: Optional filter by strategy
        start_date: Optional start date filter
        end_date: Optional end date filter
        session: Database session

    Returns:
        Win rate statistics
    """
    from datetime import datetime

    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None

    service = AnalyticsService(session)
    stats = await service.get_win_rate(
        underlying=underlying,
        strategy_type=strategy_type,
        start_date=start_dt,
        end_date=end_dt,
    )

    return WinRateStats(**stats)


@router.get("/strategy-breakdown", response_model=StrategyBreakdown)
async def get_strategy_breakdown(
    underlying: str | None = Query(None, description="Filter by underlying symbol"),
    start_date: str | None = Query(None, description="Start date (ISO format)"),
    end_date: str | None = Query(None, description="End date (ISO format)"),
    session: AsyncSession = Depends(get_db),
):
    """Get performance breakdown by strategy type.

    Shows how different strategies (vertical spreads, iron condors, etc.)
    are performing in terms of win rate and P&L.

    Args:
        underlying: Optional filter by underlying
        start_date: Optional start date filter
        end_date: Optional end date filter
        session: Database session

    Returns:
        Strategy breakdown statistics
    """
    from datetime import datetime

    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None

    service = AnalyticsService(session)
    strategies = await service.get_strategy_breakdown(
        underlying=underlying,
        start_date=start_dt,
        end_date=end_dt,
    )

    total_trades = sum(s["total_trades"] for s in strategies)

    return StrategyBreakdown(
        strategies=[StrategyStats(**s) for s in strategies],
        total_trades=total_trades,
    )


@router.get("/underlying-breakdown", response_model=UnderlyingBreakdown)
async def get_underlying_breakdown(
    strategy_type: str | None = Query(None, description="Filter by strategy type"),
    start_date: str | None = Query(None, description="Start date (ISO format)"),
    end_date: str | None = Query(None, description="End date (ISO format)"),
    session: AsyncSession = Depends(get_db),
):
    """Get performance breakdown by underlying symbol.

    Shows which stocks/indices are most profitable and which
    strategies work best for each.

    Args:
        strategy_type: Optional filter by strategy
        start_date: Optional start date filter
        end_date: Optional end date filter
        session: Database session

    Returns:
        Underlying breakdown statistics
    """
    from datetime import datetime

    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None

    service = AnalyticsService(session)
    underlyings = await service.get_underlying_breakdown(
        strategy_type=strategy_type,
        start_date=start_dt,
        end_date=end_dt,
    )

    total_trades = sum(u["total_trades"] for u in underlyings)

    return UnderlyingBreakdown(
        underlyings=[UnderlyingStats(**u) for u in underlyings],
        total_trades=total_trades,
    )


@router.get("/monthly-performance", response_model=MonthlyPerformance)
async def get_monthly_performance(
    underlying: str | None = Query(None, description="Filter by underlying symbol"),
    strategy_type: str | None = Query(None, description="Filter by strategy type"),
    year: int | None = Query(None, description="Filter by year"),
    session: AsyncSession = Depends(get_db),
):
    """Get monthly performance breakdown.

    Shows performance trends over time, broken down by month.

    Args:
        underlying: Optional filter by underlying
        strategy_type: Optional filter by strategy
        year: Optional filter by year
        session: Database session

    Returns:
        Monthly performance statistics
    """
    service = AnalyticsService(session)
    months = await service.get_monthly_performance(
        underlying=underlying,
        strategy_type=strategy_type,
        year=year,
    )

    return MonthlyPerformance(
        months=[MonthlyStats(**m) for m in months],
        total_months=len(months),
    )


@router.get("/trade-duration", response_model=TradeDurationStats)
async def get_trade_duration_stats(
    underlying: str | None = Query(None, description="Filter by underlying symbol"),
    strategy_type: str | None = Query(None, description="Filter by strategy type"),
    session: AsyncSession = Depends(get_db),
):
    """Get statistics about trade durations.

    Shows how long trades are typically held, which can inform
    strategy selection and timing.

    Args:
        underlying: Optional filter by underlying
        strategy_type: Optional filter by strategy
        session: Database session

    Returns:
        Trade duration statistics
    """
    service = AnalyticsService(session)
    stats = await service.get_trade_duration_stats(
        underlying=underlying,
        strategy_type=strategy_type,
    )

    return TradeDurationStats(**stats)
