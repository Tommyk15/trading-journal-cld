"""Dashboard service - aggregates metrics for the main dashboard."""

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.schemas.analytics import StrategyStats, UnderlyingStats
from trading_journal.schemas.dashboard import (
    DashboardSummary,
    MetricsTimePoint,
    MetricsTimeSeriesResponse,
    PortfolioGreeksSummary,
    StreakInfo,
    TimePeriod,
)
from trading_journal.services.analytics_service import AnalyticsService
from trading_journal.services.greeks_service import GreeksService
from trading_journal.services.performance_metrics_service import PerformanceMetricsService


class DashboardService:
    """Service for aggregating dashboard metrics."""

    def __init__(self, session: AsyncSession):
        """Initialize dashboard service.

        Args:
            session: Database session
        """
        self.session = session
        self.analytics = AnalyticsService(session)
        self.performance = PerformanceMetricsService(session)
        self.greeks = GreeksService(session)

    def _get_date_range(self, period: TimePeriod) -> tuple[datetime | None, datetime | None]:
        """Get start and end dates for a time period.

        Args:
            period: Time period enum

        Returns:
            Tuple of (start_date, end_date) as naive datetimes
        """
        now = datetime.now()
        today = now.date()

        if period == TimePeriod.ALL:
            return None, None
        elif period == TimePeriod.YTD:
            start = datetime(today.year, 1, 1)
            return start, now
        elif period == TimePeriod.MONTHLY:
            start = datetime(today.year, today.month, 1)
            return start, now
        elif period == TimePeriod.WEEKLY:
            # Start of current week (Monday)
            days_since_monday = today.weekday()
            week_start = today - timedelta(days=days_since_monday)
            start = datetime(week_start.year, week_start.month, week_start.day)
            return start, now

        return None, None

    async def get_summary(
        self,
        period: TimePeriod = TimePeriod.ALL,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> DashboardSummary:
        """Get comprehensive dashboard summary.

        Args:
            period: Time period for filtering
            start_date: Optional explicit start date (overrides period)
            end_date: Optional explicit end date (overrides period)

        Returns:
            DashboardSummary with all metrics
        """
        # Determine date range
        if start_date is None and end_date is None:
            start_date, end_date = self._get_date_range(period)

        # Fetch all metrics in parallel (conceptually - we await each)
        win_rate_data = await self.analytics.get_win_rate(
            start_date=start_date,
            end_date=end_date,
        )

        drawdown_data = await self.performance.get_drawdown_analysis()

        sharpe_data = await self.performance.get_sharpe_ratio(
            start_date=start_date,
            end_date=end_date,
        )

        sortino_data = await self.performance.get_sortino_ratio(
            start_date=start_date,
            end_date=end_date,
        )

        streak_data = await self.performance.get_streak_info(
            start_date=start_date,
            end_date=end_date,
        )

        expectancy_data = await self.performance.get_expectancy(
            start_date=start_date,
            end_date=end_date,
        )

        # Get strategy breakdown for best/worst
        strategy_breakdown = await self.analytics.get_strategy_breakdown(
            start_date=start_date,
            end_date=end_date,
        )

        # Get underlying breakdown for best/worst
        underlying_breakdown = await self.analytics.get_underlying_breakdown(
            start_date=start_date,
            end_date=end_date,
        )

        # Get daily P&L for avg profit per day
        daily_pnl = await self.performance.get_daily_pnl(
            start_date=start_date,
            end_date=end_date,
        )

        # Get portfolio Greeks
        portfolio_greeks_data = await self.greeks.get_portfolio_greeks_summary()

        # Calculate avg profit per day
        trading_days = len(daily_pnl)
        total_pnl = win_rate_data.get("largest_win", Decimal("0.00")) * 0  # Reset
        if daily_pnl:
            total_pnl = sum(d["daily_pnl"] for d in daily_pnl)
        avg_profit_per_day = total_pnl / trading_days if trading_days > 0 else Decimal("0.00")

        # Determine best/worst strategy
        best_strategy = None
        worst_strategy = None
        if strategy_breakdown:
            best_strategy = StrategyStats(
                strategy_type=strategy_breakdown[0]["strategy_type"],
                total_trades=strategy_breakdown[0]["total_trades"],
                winning_trades=strategy_breakdown[0]["winning_trades"],
                losing_trades=strategy_breakdown[0]["losing_trades"],
                win_rate=strategy_breakdown[0]["win_rate"],
                total_pnl=strategy_breakdown[0]["total_pnl"],
                total_commission=strategy_breakdown[0]["total_commission"],
                net_pnl=strategy_breakdown[0]["net_pnl"],
                average_pnl=strategy_breakdown[0]["average_pnl"],
            )
            worst_strategy = StrategyStats(
                strategy_type=strategy_breakdown[-1]["strategy_type"],
                total_trades=strategy_breakdown[-1]["total_trades"],
                winning_trades=strategy_breakdown[-1]["winning_trades"],
                losing_trades=strategy_breakdown[-1]["losing_trades"],
                win_rate=strategy_breakdown[-1]["win_rate"],
                total_pnl=strategy_breakdown[-1]["total_pnl"],
                total_commission=strategy_breakdown[-1]["total_commission"],
                net_pnl=strategy_breakdown[-1]["net_pnl"],
                average_pnl=strategy_breakdown[-1]["average_pnl"],
            )

        # Determine best/worst ticker
        best_ticker = None
        worst_ticker = None
        if underlying_breakdown:
            best_ticker = UnderlyingStats(
                underlying=underlying_breakdown[0]["underlying"],
                total_trades=underlying_breakdown[0]["total_trades"],
                winning_trades=underlying_breakdown[0]["winning_trades"],
                losing_trades=underlying_breakdown[0]["losing_trades"],
                win_rate=underlying_breakdown[0]["win_rate"],
                total_pnl=underlying_breakdown[0]["total_pnl"],
                total_commission=underlying_breakdown[0]["total_commission"],
                net_pnl=underlying_breakdown[0]["net_pnl"],
                average_pnl=underlying_breakdown[0]["average_pnl"],
            )
            worst_ticker = UnderlyingStats(
                underlying=underlying_breakdown[-1]["underlying"],
                total_trades=underlying_breakdown[-1]["total_trades"],
                winning_trades=underlying_breakdown[-1]["winning_trades"],
                losing_trades=underlying_breakdown[-1]["losing_trades"],
                win_rate=underlying_breakdown[-1]["win_rate"],
                total_pnl=underlying_breakdown[-1]["total_pnl"],
                total_commission=underlying_breakdown[-1]["total_commission"],
                net_pnl=underlying_breakdown[-1]["net_pnl"],
                average_pnl=underlying_breakdown[-1]["average_pnl"],
            )

        # Build portfolio Greeks summary
        portfolio_greeks = None
        if portfolio_greeks_data["position_count"] > 0:
            portfolio_greeks = PortfolioGreeksSummary(
                total_delta=portfolio_greeks_data["total_delta"],
                total_gamma=portfolio_greeks_data["total_gamma"],
                total_theta=portfolio_greeks_data["total_theta"],
                total_vega=portfolio_greeks_data["total_vega"],
                position_count=portfolio_greeks_data["position_count"],
                last_updated=portfolio_greeks_data["last_updated"],
            )

        # Calculate total P&L from win rate data
        winners_total = win_rate_data["average_win"] * win_rate_data["winning_trades"]
        losers_total = win_rate_data["average_loss"] * win_rate_data["losing_trades"]
        calculated_total_pnl = winners_total - losers_total

        return DashboardSummary(
            total_pnl=calculated_total_pnl,
            total_trades=win_rate_data["total_trades"],
            win_rate=win_rate_data["win_rate"],
            avg_winner=win_rate_data["average_win"],
            avg_loser=win_rate_data["average_loss"],
            profit_factor=win_rate_data["profit_factor"],
            max_drawdown_percent=drawdown_data["max_drawdown_percentage"],
            avg_profit_per_day=avg_profit_per_day,
            trading_days=trading_days,
            best_strategy=best_strategy,
            worst_strategy=worst_strategy,
            best_ticker=best_ticker,
            worst_ticker=worst_ticker,
            sharpe_ratio=sharpe_data["sharpe_ratio"],
            sortino_ratio=sortino_data["sortino_ratio"],
            expectancy=expectancy_data["expectancy"],
            streak_info=StreakInfo(
                max_consecutive_wins=streak_data["max_consecutive_wins"],
                max_consecutive_losses=streak_data["max_consecutive_losses"],
                current_streak=streak_data["current_streak"],
                current_streak_type=streak_data["current_streak_type"],
            ),
            portfolio_greeks=portfolio_greeks,
        )

    async def get_metrics_timeseries(
        self,
        period: TimePeriod = TimePeriod.ALL,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> MetricsTimeSeriesResponse:
        """Get metrics time series for charts.

        Args:
            period: Time period for filtering
            start_date: Optional explicit start date (overrides period)
            end_date: Optional explicit end date (overrides period)

        Returns:
            MetricsTimeSeriesResponse with time series data
        """
        # Determine date range
        if start_date is None and end_date is None:
            start_date, end_date = self._get_date_range(period)

        # Get daily P&L data
        daily_pnl = await self.performance.get_daily_pnl(
            start_date=start_date,
            end_date=end_date,
        )

        if not daily_pnl:
            return MetricsTimeSeriesResponse(
                data_points=[],
                period=period,
                start_date=start_date.date() if start_date else None,
                end_date=end_date.date() if end_date else None,
            )

        # Build time series with rolling metrics
        data_points = []
        cumulative_wins = 0
        cumulative_losses = 0
        cumulative_win_amount = Decimal("0.00")
        cumulative_loss_amount = Decimal("0.00")
        peak_equity = Decimal("0.00")

        for day in daily_pnl:
            cumulative_pnl = day["cumulative_pnl"]
            cumulative_wins += day["winning_trades"]
            cumulative_losses += day["losing_trades"]
            cumulative_win_amount += day.get("win_amount", Decimal("0.00"))
            cumulative_loss_amount += day.get("loss_amount", Decimal("0.00"))
            total_trades = cumulative_wins + cumulative_losses

            # Calculate rolling win rate
            win_rate = (cumulative_wins / total_trades * 100) if total_trades > 0 else 0.0

            # Track peak for drawdown
            if cumulative_pnl > peak_equity:
                peak_equity = cumulative_pnl

            # Calculate drawdown
            drawdown = peak_equity - cumulative_pnl if peak_equity > 0 else Decimal("0.00")
            drawdown_pct = float(drawdown / peak_equity * 100) if peak_equity > 0 else 0.0

            # Calculate rolling profit factor
            profit_factor = None
            if cumulative_loss_amount > 0:
                profit_factor = float(cumulative_win_amount / cumulative_loss_amount)

            # Calculate rolling avg winner and avg loser
            avg_winner = cumulative_win_amount / cumulative_wins if cumulative_wins > 0 else None
            avg_loser = cumulative_loss_amount / cumulative_losses if cumulative_losses > 0 else None

            data_points.append(MetricsTimePoint(
                date=day["date"],
                cumulative_pnl=cumulative_pnl,
                trade_count=total_trades,
                win_rate=win_rate,
                profit_factor=profit_factor,
                drawdown_percent=drawdown_pct,
                avg_winner=avg_winner,
                avg_loser=avg_loser,
            ))

        return MetricsTimeSeriesResponse(
            data_points=data_points,
            period=period,
            start_date=daily_pnl[0]["date"] if daily_pnl else None,
            end_date=daily_pnl[-1]["date"] if daily_pnl else None,
        )
