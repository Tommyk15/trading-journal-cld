"""Analytics service - provides trade statistics and insights."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.models.trade import Trade


class AnalyticsService:
    """Service for trade analytics and statistics."""

    def __init__(self, session: AsyncSession):
        """Initialize analytics service.

        Args:
            session: Database session
        """
        self.session = session

    async def get_win_rate(
        self,
        underlying: str | None = None,
        strategy_type: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict:
        """Calculate win rate and related statistics.

        Args:
            underlying: Optional filter by underlying
            strategy_type: Optional filter by strategy
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Dictionary with win rate statistics
        """
        stmt = select(Trade).where(Trade.status == "CLOSED")

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

        if not trades:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "breakeven_trades": 0,
                "win_rate": 0.0,
                "average_win": Decimal("0.00"),
                "average_loss": Decimal("0.00"),
                "largest_win": Decimal("0.00"),
                "largest_loss": Decimal("0.00"),
                "profit_factor": None,
            }

        # Categorize trades
        winning_trades = [t for t in trades if t.realized_pnl > 0]
        losing_trades = [t for t in trades if t.realized_pnl < 0]
        breakeven_trades = [t for t in trades if t.realized_pnl == 0]

        # Calculate statistics
        total_wins = sum(t.realized_pnl for t in winning_trades)
        total_losses = abs(sum(t.realized_pnl for t in losing_trades))

        avg_win = (
            total_wins / len(winning_trades) if winning_trades else Decimal("0.00")
        )
        avg_loss = (
            total_losses / len(losing_trades) if losing_trades else Decimal("0.00")
        )

        largest_win = max((t.realized_pnl for t in winning_trades), default=Decimal("0.00"))
        largest_loss = min((t.realized_pnl for t in losing_trades), default=Decimal("0.00"))

        # Profit factor: total wins / total losses
        profit_factor = None
        if total_losses > 0:
            profit_factor = float(total_wins / total_losses)

        return {
            "total_trades": len(trades),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "breakeven_trades": len(breakeven_trades),
            "win_rate": (len(winning_trades) / len(trades) * 100) if trades else 0.0,
            "average_win": avg_win,
            "average_loss": avg_loss,
            "largest_win": largest_win,
            "largest_loss": largest_loss,
            "profit_factor": profit_factor,
        }

    async def get_strategy_breakdown(
        self,
        underlying: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[dict]:
        """Get performance breakdown by strategy type.

        Args:
            underlying: Optional filter by underlying
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of strategy statistics
        """
        stmt = select(Trade).where(Trade.status == "CLOSED")

        if underlying:
            stmt = stmt.where(Trade.underlying == underlying)
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

        # Calculate stats for each strategy
        strategy_stats = []
        for strategy_type, strategy_trades in by_strategy.items():
            winning = [t for t in strategy_trades if t.realized_pnl > 0]
            losing = [t for t in strategy_trades if t.realized_pnl < 0]

            total_pnl = sum(t.realized_pnl for t in strategy_trades)
            total_commission = sum(t.total_commission for t in strategy_trades)

            strategy_stats.append({
                "strategy_type": strategy_type,
                "total_trades": len(strategy_trades),
                "winning_trades": len(winning),
                "losing_trades": len(losing),
                "win_rate": (len(winning) / len(strategy_trades) * 100) if strategy_trades else 0.0,
                "total_pnl": total_pnl,
                "total_commission": total_commission,
                "net_pnl": total_pnl - total_commission,
                "average_pnl": total_pnl / len(strategy_trades) if strategy_trades else Decimal("0.00"),
            })

        # Sort by total P&L descending
        strategy_stats.sort(key=lambda x: x["total_pnl"], reverse=True)

        return strategy_stats

    async def get_underlying_breakdown(
        self,
        strategy_type: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[dict]:
        """Get performance breakdown by underlying symbol.

        Args:
            strategy_type: Optional filter by strategy
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of underlying statistics
        """
        stmt = select(Trade).where(Trade.status == "CLOSED")

        if strategy_type:
            stmt = stmt.where(Trade.strategy_type == strategy_type)
        if start_date:
            stmt = stmt.where(Trade.closed_at >= start_date)
        if end_date:
            stmt = stmt.where(Trade.closed_at <= end_date)

        result = await self.session.execute(stmt)
        trades = list(result.scalars().all())

        # Group by underlying
        from collections import defaultdict

        by_underlying = defaultdict(list)
        for trade in trades:
            by_underlying[trade.underlying].append(trade)

        # Calculate stats for each underlying
        underlying_stats = []
        for underlying, underlying_trades in by_underlying.items():
            winning = [t for t in underlying_trades if t.realized_pnl > 0]
            losing = [t for t in underlying_trades if t.realized_pnl < 0]

            total_pnl = sum(t.realized_pnl for t in underlying_trades)
            total_commission = sum(t.total_commission for t in underlying_trades)

            underlying_stats.append({
                "underlying": underlying,
                "total_trades": len(underlying_trades),
                "winning_trades": len(winning),
                "losing_trades": len(losing),
                "win_rate": (len(winning) / len(underlying_trades) * 100) if underlying_trades else 0.0,
                "total_pnl": total_pnl,
                "total_commission": total_commission,
                "net_pnl": total_pnl - total_commission,
                "average_pnl": total_pnl / len(underlying_trades) if underlying_trades else Decimal("0.00"),
            })

        # Sort by total P&L descending
        underlying_stats.sort(key=lambda x: x["total_pnl"], reverse=True)

        return underlying_stats

    async def get_monthly_performance(
        self,
        underlying: str | None = None,
        strategy_type: str | None = None,
        year: int | None = None,
    ) -> list[dict]:
        """Get monthly performance breakdown.

        Args:
            underlying: Optional filter by underlying
            strategy_type: Optional filter by strategy
            year: Optional filter by year

        Returns:
            List of monthly statistics
        """
        stmt = select(Trade).where(Trade.status == "CLOSED", Trade.closed_at.isnot(None))

        if underlying:
            stmt = stmt.where(Trade.underlying == underlying)
        if strategy_type:
            stmt = stmt.where(Trade.strategy_type == strategy_type)
        if year:
            stmt = stmt.where(
                func.extract("year", Trade.closed_at) == year
            )

        result = await self.session.execute(stmt)
        trades = list(result.scalars().all())

        # Group by year-month
        from collections import defaultdict

        by_month = defaultdict(list)
        for trade in trades:
            if trade.closed_at:
                month_key = trade.closed_at.strftime("%Y-%m")
                by_month[month_key].append(trade)

        # Calculate stats for each month
        monthly_stats = []
        for month_key, month_trades in by_month.items():
            winning = [t for t in month_trades if t.realized_pnl > 0]
            losing = [t for t in month_trades if t.realized_pnl < 0]

            total_pnl = sum(t.realized_pnl for t in month_trades)
            total_commission = sum(t.total_commission for t in month_trades)

            monthly_stats.append({
                "month": month_key,
                "total_trades": len(month_trades),
                "winning_trades": len(winning),
                "losing_trades": len(losing),
                "win_rate": (len(winning) / len(month_trades) * 100) if month_trades else 0.0,
                "total_pnl": total_pnl,
                "total_commission": total_commission,
                "net_pnl": total_pnl - total_commission,
            })

        # Sort by month
        monthly_stats.sort(key=lambda x: x["month"])

        return monthly_stats

    async def get_trade_duration_stats(
        self,
        underlying: str | None = None,
        strategy_type: str | None = None,
    ) -> dict:
        """Get statistics about trade durations.

        Args:
            underlying: Optional filter by underlying
            strategy_type: Optional filter by strategy

        Returns:
            Dictionary with duration statistics
        """
        stmt = select(Trade).where(
            Trade.status == "CLOSED",
            Trade.closed_at.isnot(None)
        )

        if underlying:
            stmt = stmt.where(Trade.underlying == underlying)
        if strategy_type:
            stmt = stmt.where(Trade.strategy_type == strategy_type)

        result = await self.session.execute(stmt)
        trades = list(result.scalars().all())

        if not trades:
            return {
                "total_trades": 0,
                "average_duration_hours": 0.0,
                "shortest_duration_hours": 0.0,
                "longest_duration_hours": 0.0,
            }

        # Calculate durations
        durations = []
        for trade in trades:
            if trade.closed_at and trade.opened_at:
                duration = (trade.closed_at - trade.opened_at).total_seconds() / 3600
                durations.append(duration)

        if not durations:
            return {
                "total_trades": len(trades),
                "average_duration_hours": 0.0,
                "shortest_duration_hours": 0.0,
                "longest_duration_hours": 0.0,
            }

        return {
            "total_trades": len(trades),
            "average_duration_hours": sum(durations) / len(durations),
            "shortest_duration_hours": min(durations),
            "longest_duration_hours": max(durations),
        }
