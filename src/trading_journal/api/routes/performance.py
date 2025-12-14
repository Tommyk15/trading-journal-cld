"""API routes for performance metrics and time-series data."""


from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.core.database import get_db
from trading_journal.schemas.performance import (
    CumulativePnLPoint,
    CumulativePnLResponse,
    DailyPnLPoint,
    DailyPnLResponse,
    DrawdownAnalysis,
    EquityCurveSummary,
    SharpeRatioAnalysis,
    StrategyProfitCurve,
    StrategyProfitCurvePoint,
    StrategyProfitCurvesResponse,
)
from trading_journal.services.performance_metrics_service import PerformanceMetricsService

router = APIRouter(prefix="/performance", tags=["performance"])


@router.get("/cumulative-pnl", response_model=CumulativePnLResponse)
async def get_cumulative_pnl(
    underlying: str | None = Query(None, description="Filter by underlying symbol"),
    strategy_type: str | None = Query(None, description="Filter by strategy type"),
    start_date: str | None = Query(None, description="Start date (ISO format)"),
    end_date: str | None = Query(None, description="End date (ISO format)"),
    session: AsyncSession = Depends(get_db),
):
    """Get cumulative P&L over time.

    Returns a time series showing how cumulative P&L has evolved
    with each trade. Useful for plotting equity curves.

    Args:
        underlying: Optional filter by underlying
        strategy_type: Optional filter by strategy
        start_date: Optional start date filter
        end_date: Optional end date filter
        session: Database session

    Returns:
        Cumulative P&L time series
    """
    from datetime import datetime

    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None

    service = PerformanceMetricsService(session)
    data = await service.get_cumulative_pnl(
        underlying=underlying,
        strategy_type=strategy_type,
        start_date=start_dt,
        end_date=end_dt,
    )

    return CumulativePnLResponse(
        data_points=[CumulativePnLPoint(**point) for point in data],
        total_trades=len(data),
    )


@router.get("/daily-pnl", response_model=DailyPnLResponse)
async def get_daily_pnl(
    underlying: str | None = Query(None, description="Filter by underlying symbol"),
    strategy_type: str | None = Query(None, description="Filter by strategy type"),
    start_date: str | None = Query(None, description="Start date (ISO format)"),
    end_date: str | None = Query(None, description="End date (ISO format)"),
    session: AsyncSession = Depends(get_db),
):
    """Get daily aggregated P&L.

    Returns daily statistics aggregating all trades closed on each day.
    Useful for understanding daily performance patterns.

    Args:
        underlying: Optional filter by underlying
        strategy_type: Optional filter by strategy
        start_date: Optional start date filter
        end_date: Optional end date filter
        session: Database session

    Returns:
        Daily P&L time series
    """
    from datetime import datetime

    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None

    service = PerformanceMetricsService(session)
    data = await service.get_daily_pnl(
        underlying=underlying,
        strategy_type=strategy_type,
        start_date=start_dt,
        end_date=end_dt,
    )

    return DailyPnLResponse(
        data_points=[DailyPnLPoint(**point) for point in data],
        total_days=len(data),
    )


@router.get("/drawdown", response_model=DrawdownAnalysis)
async def get_drawdown_analysis(
    underlying: str | None = Query(None, description="Filter by underlying symbol"),
    strategy_type: str | None = Query(None, description="Filter by strategy type"),
    session: AsyncSession = Depends(get_db),
):
    """Get drawdown analysis.

    Calculates maximum drawdown, current drawdown, and related metrics.
    Important for understanding risk and capital preservation.

    Args:
        underlying: Optional filter by underlying
        strategy_type: Optional filter by strategy
        session: Database session

    Returns:
        Drawdown analysis
    """
    service = PerformanceMetricsService(session)
    stats = await service.get_drawdown_analysis(
        underlying=underlying,
        strategy_type=strategy_type,
    )

    return DrawdownAnalysis(**stats)


@router.get("/sharpe-ratio", response_model=SharpeRatioAnalysis)
async def get_sharpe_ratio(
    underlying: str | None = Query(None, description="Filter by underlying symbol"),
    strategy_type: str | None = Query(None, description="Filter by strategy type"),
    risk_free_rate: float = Query(0.02, description="Annual risk-free rate (default 2%)"),
    session: AsyncSession = Depends(get_db),
):
    """Get Sharpe ratio and risk-adjusted metrics.

    Calculates the Sharpe ratio and related volatility metrics.
    Higher Sharpe ratios indicate better risk-adjusted returns.

    Args:
        underlying: Optional filter by underlying
        strategy_type: Optional filter by strategy
        risk_free_rate: Annual risk-free rate
        session: Database session

    Returns:
        Sharpe ratio analysis
    """
    service = PerformanceMetricsService(session)
    stats = await service.get_sharpe_ratio(
        underlying=underlying,
        strategy_type=strategy_type,
        risk_free_rate=risk_free_rate,
    )

    return SharpeRatioAnalysis(**stats)


@router.get("/strategy-curves", response_model=StrategyProfitCurvesResponse)
async def get_profit_curves_by_strategy(
    start_date: str | None = Query(None, description="Start date (ISO format)"),
    end_date: str | None = Query(None, description="End date (ISO format)"),
    session: AsyncSession = Depends(get_db),
):
    """Get profit curves for each strategy type.

    Returns separate equity curves for each strategy, allowing
    comparison of how different strategies perform over time.

    Args:
        start_date: Optional start date filter
        end_date: Optional end date filter
        session: Database session

    Returns:
        Profit curves by strategy
    """
    from datetime import datetime

    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None

    service = PerformanceMetricsService(session)
    curves = await service.get_profit_curve_by_strategy(
        start_date=start_dt,
        end_date=end_dt,
    )

    # Convert to response format
    strategies = {}
    for strategy_type, curve_data in curves.items():
        strategies[strategy_type] = StrategyProfitCurve(
            total_trades=curve_data["total_trades"],
            final_pnl=curve_data["final_pnl"],
            curve=[StrategyProfitCurvePoint(**point) for point in curve_data["curve"]],
        )

    return StrategyProfitCurvesResponse(strategies=strategies)


@router.get("/equity-summary", response_model=EquityCurveSummary)
async def get_equity_curve_summary(
    underlying: str | None = Query(None, description="Filter by underlying symbol"),
    strategy_type: str | None = Query(None, description="Filter by strategy type"),
    session: AsyncSession = Depends(get_db),
):
    """Get summary of equity curve.

    Provides a high-level summary of the equity curve including
    starting/ending equity, total return, and date range.

    Args:
        underlying: Optional filter by underlying
        strategy_type: Optional filter by strategy
        session: Database session

    Returns:
        Equity curve summary
    """
    service = PerformanceMetricsService(session)
    summary = await service.get_equity_curve_summary(
        underlying=underlying,
        strategy_type=strategy_type,
    )

    return EquityCurveSummary(**summary)
