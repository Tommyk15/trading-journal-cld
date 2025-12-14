"""Performance metrics service - time-series P&L and performance tracking."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.models.trade import Trade


class PerformanceMetricsService:
    """Service for performance metrics and time-series data."""

    def __init__(self, session: AsyncSession):
        """Initialize performance metrics service.

        Args:
            session: Database session
        """
        self.session = session

    async def get_cumulative_pnl(
        self,
        underlying: str | None = None,
        strategy_type: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[dict]:
        """Get cumulative P&L over time.

        Args:
            underlying: Optional filter by underlying
            strategy_type: Optional filter by strategy
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of time-series data points with cumulative P&L
        """
        stmt = (
            select(Trade)
            .where(Trade.status == "CLOSED", Trade.closed_at.isnot(None))
            .order_by(Trade.closed_at)
        )

        if underlying:
            stmt = stmt.where(Trade.underlying == underlying)
        if strategy_type:
            stmt = stmt.where(Trade.strategy_type == strategy_type)
        if start_date:
            stmt = stmt.where(Trade.closed_at >= start_date)
        if end_date:
            stmt = stmt.where(Trade.closed_at <= end_date)

        result = await self.session.execute(stmt)
        trades = list(result.scalars().all())

        # Calculate cumulative P&L
        cumulative_pnl = Decimal("0.00")
        time_series = []

        for trade in trades:
            cumulative_pnl += trade.realized_pnl
            time_series.append({
                "timestamp": trade.closed_at,
                "trade_id": trade.id,
                "trade_pnl": trade.realized_pnl,
                "cumulative_pnl": cumulative_pnl,
                "underlying": trade.underlying,
                "strategy_type": trade.strategy_type,
            })

        return time_series

    async def get_daily_pnl(
        self,
        underlying: str | None = None,
        strategy_type: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[dict]:
        """Get daily aggregated P&L.

        Args:
            underlying: Optional filter by underlying
            strategy_type: Optional filter by strategy
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of daily P&L data points
        """
        stmt = (
            select(Trade)
            .where(Trade.status == "CLOSED", Trade.closed_at.isnot(None))
            .order_by(Trade.closed_at)
        )

        if underlying:
            stmt = stmt.where(Trade.underlying == underlying)
        if strategy_type:
            stmt = stmt.where(Trade.strategy_type == strategy_type)
        if start_date:
            stmt = stmt.where(Trade.closed_at >= start_date)
        if end_date:
            stmt = stmt.where(Trade.closed_at <= end_date)

        result = await self.session.execute(stmt)
        trades = list(result.scalars().all())

        # Group by date
        from collections import defaultdict

        by_date = defaultdict(list)
        for trade in trades:
            if trade.closed_at:
                date_key = trade.closed_at.date()
                by_date[date_key].append(trade)

        # Calculate daily stats
        daily_data = []
        cumulative_pnl = Decimal("0.00")

        for date_key in sorted(by_date.keys()):
            day_trades = by_date[date_key]
            day_pnl = sum(t.realized_pnl for t in day_trades)
            cumulative_pnl += day_pnl

            daily_data.append({
                "date": date_key,
                "trades_count": len(day_trades),
                "daily_pnl": day_pnl,
                "cumulative_pnl": cumulative_pnl,
                "winning_trades": len([t for t in day_trades if t.realized_pnl > 0]),
                "losing_trades": len([t for t in day_trades if t.realized_pnl < 0]),
            })

        return daily_data

    async def get_drawdown_analysis(
        self,
        underlying: str | None = None,
        strategy_type: str | None = None,
    ) -> dict:
        """Calculate drawdown statistics.

        Args:
            underlying: Optional filter by underlying
            strategy_type: Optional filter by strategy

        Returns:
            Dictionary with drawdown statistics
        """
        # Get cumulative P&L time series
        time_series = await self.get_cumulative_pnl(
            underlying=underlying,
            strategy_type=strategy_type,
        )

        if not time_series:
            return {
                "max_drawdown": Decimal("0.00"),
                "max_drawdown_percentage": 0.0,
                "current_drawdown": Decimal("0.00"),
                "current_drawdown_percentage": 0.0,
                "peak_equity": Decimal("0.00"),
                "current_equity": Decimal("0.00"),
            }

        # Calculate drawdowns
        peak_equity = Decimal("0.00")
        max_drawdown = Decimal("0.00")
        max_drawdown_pct = 0.0

        for point in time_series:
            equity = point["cumulative_pnl"]

            # Update peak
            if equity > peak_equity:
                peak_equity = equity

            # Calculate drawdown
            if peak_equity > 0:
                drawdown = peak_equity - equity
                drawdown_pct = float(drawdown / peak_equity * 100)

                if drawdown > max_drawdown:
                    max_drawdown = drawdown
                    max_drawdown_pct = drawdown_pct

        # Current drawdown
        current_equity = time_series[-1]["cumulative_pnl"] if time_series else Decimal("0.00")
        current_drawdown = peak_equity - current_equity if peak_equity > current_equity else Decimal("0.00")
        current_drawdown_pct = (
            float(current_drawdown / peak_equity * 100) if peak_equity > 0 else 0.0
        )

        return {
            "max_drawdown": max_drawdown,
            "max_drawdown_percentage": max_drawdown_pct,
            "current_drawdown": current_drawdown,
            "current_drawdown_percentage": current_drawdown_pct,
            "peak_equity": peak_equity,
            "current_equity": current_equity,
        }

    async def get_sharpe_ratio(
        self,
        underlying: str | None = None,
        strategy_type: str | None = None,
        risk_free_rate: float = 0.02,  # 2% annual risk-free rate
    ) -> dict:
        """Calculate Sharpe ratio and related risk metrics.

        Args:
            underlying: Optional filter by underlying
            strategy_type: Optional filter by strategy
            risk_free_rate: Annual risk-free rate (default 2%)

        Returns:
            Dictionary with risk-adjusted performance metrics
        """
        # Get daily P&L data
        daily_data = await self.get_daily_pnl(
            underlying=underlying,
            strategy_type=strategy_type,
        )

        if not daily_data or len(daily_data) < 2:
            return {
                "sharpe_ratio": None,
                "average_daily_return": Decimal("0.00"),
                "daily_volatility": Decimal("0.00"),
                "total_days": 0,
            }

        # Calculate returns
        daily_returns = [float(day["daily_pnl"]) for day in daily_data]

        # Calculate statistics
        import statistics

        avg_daily_return = statistics.mean(daily_returns)
        daily_volatility = statistics.stdev(daily_returns) if len(daily_returns) > 1 else 0.0

        # Annualize (252 trading days)
        annualized_return = avg_daily_return * 252
        annualized_volatility = daily_volatility * (252 ** 0.5)

        # Calculate Sharpe ratio
        sharpe_ratio = None
        if annualized_volatility > 0:
            sharpe_ratio = (annualized_return - risk_free_rate) / annualized_volatility

        return {
            "sharpe_ratio": sharpe_ratio,
            "average_daily_return": Decimal(str(avg_daily_return)),
            "daily_volatility": Decimal(str(daily_volatility)),
            "annualized_return": Decimal(str(annualized_return)),
            "annualized_volatility": Decimal(str(annualized_volatility)),
            "total_days": len(daily_data),
        }

    async def get_profit_curve_by_strategy(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict:
        """Get profit curves for each strategy type.

        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Dictionary mapping strategy types to their profit curves
        """
        stmt = (
            select(Trade)
            .where(Trade.status == "CLOSED", Trade.closed_at.isnot(None))
            .order_by(Trade.closed_at)
        )

        if start_date:
            stmt = stmt.where(Trade.closed_at >= start_date)
        if end_date:
            stmt = stmt.where(Trade.closed_at <= end_date)

        result = await self.session.execute(stmt)
        trades = list(result.scalars().all())

        # Group by strategy
        from collections import defaultdict

        by_strategy = defaultdict(list)
        for trade in trades:
            by_strategy[trade.strategy_type].append(trade)

        # Calculate cumulative P&L for each strategy
        strategy_curves = {}
        for strategy_type, strategy_trades in by_strategy.items():
            cumulative_pnl = Decimal("0.00")
            curve = []

            for trade in sorted(strategy_trades, key=lambda t: t.closed_at):
                cumulative_pnl += trade.realized_pnl
                curve.append({
                    "timestamp": trade.closed_at,
                    "trade_id": trade.id,
                    "trade_pnl": trade.realized_pnl,
                    "cumulative_pnl": cumulative_pnl,
                })

            strategy_curves[strategy_type] = {
                "total_trades": len(strategy_trades),
                "final_pnl": cumulative_pnl,
                "curve": curve,
            }

        return strategy_curves

    async def get_equity_curve_summary(
        self,
        underlying: str | None = None,
        strategy_type: str | None = None,
    ) -> dict:
        """Get summary of equity curve with key metrics.

        Args:
            underlying: Optional filter by underlying
            strategy_type: Optional filter by strategy

        Returns:
            Dictionary with equity curve summary
        """
        time_series = await self.get_cumulative_pnl(
            underlying=underlying,
            strategy_type=strategy_type,
        )

        if not time_series:
            return {
                "total_trades": 0,
                "starting_equity": Decimal("0.00"),
                "ending_equity": Decimal("0.00"),
                "total_return": Decimal("0.00"),
                "data_points": 0,
            }

        starting_equity = Decimal("0.00")  # Starting from 0
        ending_equity = time_series[-1]["cumulative_pnl"]
        total_return = ending_equity - starting_equity

        return {
            "total_trades": len(time_series),
            "starting_equity": starting_equity,
            "ending_equity": ending_equity,
            "total_return": total_return,
            "data_points": len(time_series),
            "first_trade_date": time_series[0]["timestamp"] if time_series else None,
            "last_trade_date": time_series[-1]["timestamp"] if time_series else None,
        }
