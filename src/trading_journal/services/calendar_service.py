"""Calendar service - aggregates trades and positions by time periods."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.models.position import Position
from trading_journal.models.trade import Trade


class CalendarService:
    """Service for calendar-based data aggregation."""

    def __init__(self, session: AsyncSession):
        """Initialize calendar service.

        Args:
            session: Database session
        """
        self.session = session

    async def get_upcoming_expirations(
        self,
        days_ahead: int = 30,
        underlying: Optional[str] = None,
    ) -> list[dict]:
        """Get upcoming option expirations.

        Args:
            days_ahead: Number of days to look ahead (default 30)
            underlying: Optional filter by underlying

        Returns:
            List of expiration dates with position details
        """
        end_date = datetime.utcnow() + timedelta(days=days_ahead)

        stmt = (
            select(Position)
            .where(
                Position.expiration.isnot(None),
                Position.expiration <= end_date,
                Position.expiration >= datetime.utcnow(),
            )
            .order_by(Position.expiration)
        )

        if underlying:
            stmt = stmt.where(Position.underlying == underlying)

        result = await self.session.execute(stmt)
        positions = list(result.scalars().all())

        # Group by expiration date
        from collections import defaultdict

        by_expiration = defaultdict(list)
        for position in positions:
            if position.expiration:
                exp_date = position.expiration.date()
                by_expiration[exp_date].append(position)

        # Format response
        expirations = []
        for exp_date, exp_positions in sorted(by_expiration.items()):
            days_until = (exp_date - datetime.utcnow().date()).days

            expirations.append({
                "expiration_date": exp_date,
                "days_until_expiration": days_until,
                "total_positions": len(exp_positions),
                "underlyings": list(set(p.underlying for p in exp_positions)),
                "positions": [
                    {
                        "id": p.id,
                        "underlying": p.underlying,
                        "option_type": p.option_type,
                        "strike": p.strike,
                        "quantity": p.quantity,
                        "unrealized_pnl": p.unrealized_pnl,
                    }
                    for p in exp_positions
                ],
            })

        return expirations

    async def get_trades_by_week(
        self,
        year: int,
        underlying: Optional[str] = None,
        strategy_type: Optional[str] = None,
    ) -> list[dict]:
        """Get trades grouped by week.

        Args:
            year: Year to analyze
            underlying: Optional filter by underlying
            strategy_type: Optional filter by strategy

        Returns:
            List of weekly statistics
        """
        start_date = datetime(year, 1, 1)
        end_date = datetime(year, 12, 31, 23, 59, 59)

        stmt = (
            select(Trade)
            .where(
                Trade.closed_at.isnot(None),
                Trade.closed_at >= start_date,
                Trade.closed_at <= end_date,
            )
            .order_by(Trade.closed_at)
        )

        if underlying:
            stmt = stmt.where(Trade.underlying == underlying)
        if strategy_type:
            stmt = stmt.where(Trade.strategy_type == strategy_type)

        result = await self.session.execute(stmt)
        trades = list(result.scalars().all())

        # Group by ISO week
        from collections import defaultdict

        by_week = defaultdict(list)
        for trade in trades:
            if trade.closed_at:
                week_num = trade.closed_at.isocalendar()[1]
                week_key = f"{year}-W{week_num:02d}"
                by_week[week_key].append(trade)

        # Calculate weekly stats
        weekly_stats = []
        for week_key, week_trades in sorted(by_week.items()):
            winning = [t for t in week_trades if t.realized_pnl > 0]
            losing = [t for t in week_trades if t.realized_pnl < 0]
            total_pnl = sum(t.realized_pnl for t in week_trades)

            weekly_stats.append({
                "week": week_key,
                "total_trades": len(week_trades),
                "winning_trades": len(winning),
                "losing_trades": len(losing),
                "total_pnl": total_pnl,
                "win_rate": (len(winning) / len(week_trades) * 100) if week_trades else 0.0,
            })

        return weekly_stats

    async def get_trades_calendar(
        self,
        start_date: datetime,
        end_date: datetime,
        underlying: Optional[str] = None,
    ) -> dict:
        """Get calendar view of trades with daily details.

        Args:
            start_date: Start date for calendar
            end_date: End date for calendar
            underlying: Optional filter by underlying

        Returns:
            Dictionary mapping dates to trade lists
        """
        stmt = (
            select(Trade)
            .where(
                Trade.closed_at.isnot(None),
                Trade.closed_at >= start_date,
                Trade.closed_at <= end_date,
            )
            .order_by(Trade.closed_at)
        )

        if underlying:
            stmt = stmt.where(Trade.underlying == underlying)

        result = await self.session.execute(stmt)
        trades = list(result.scalars().all())

        # Group by date
        from collections import defaultdict

        by_date = defaultdict(list)
        for trade in trades:
            if trade.closed_at:
                date_key = trade.closed_at.date()
                by_date[date_key].append({
                    "id": trade.id,
                    "underlying": trade.underlying,
                    "strategy_type": trade.strategy_type,
                    "opened_at": trade.opened_at,
                    "closed_at": trade.closed_at,
                    "realized_pnl": trade.realized_pnl,
                    "num_legs": trade.num_legs,
                })

        # Convert to sorted list format
        calendar_data = {}
        for date_key, date_trades in sorted(by_date.items()):
            calendar_data[str(date_key)] = {
                "date": date_key,
                "trades_count": len(date_trades),
                "total_pnl": sum(t["realized_pnl"] for t in date_trades),
                "trades": date_trades,
            }

        return calendar_data

    async def get_expiration_calendar(
        self,
        start_date: datetime,
        end_date: datetime,
        underlying: Optional[str] = None,
    ) -> dict:
        """Get calendar view of option expirations.

        Args:
            start_date: Start date for calendar
            end_date: End date for calendar
            underlying: Optional filter by underlying

        Returns:
            Dictionary mapping dates to expiring positions
        """
        stmt = (
            select(Position)
            .where(
                Position.expiration.isnot(None),
                Position.expiration >= start_date,
                Position.expiration <= end_date,
            )
            .order_by(Position.expiration)
        )

        if underlying:
            stmt = stmt.where(Position.underlying == underlying)

        result = await self.session.execute(stmt)
        positions = list(result.scalars().all())

        # Group by expiration date
        from collections import defaultdict

        by_date = defaultdict(list)
        for position in positions:
            if position.expiration:
                date_key = position.expiration.date()
                by_date[date_key].append({
                    "id": position.id,
                    "underlying": position.underlying,
                    "option_type": position.option_type,
                    "strike": position.strike,
                    "quantity": position.quantity,
                    "unrealized_pnl": position.unrealized_pnl,
                })

        # Convert to sorted format
        calendar_data = {}
        for date_key, date_positions in sorted(by_date.items()):
            calendar_data[str(date_key)] = {
                "date": date_key,
                "positions_count": len(date_positions),
                "total_quantity": sum(abs(p["quantity"]) for p in date_positions),
                "positions": date_positions,
            }

        return calendar_data

    async def get_monthly_summary(
        self,
        year: int,
        month: int,
        underlying: Optional[str] = None,
    ) -> dict:
        """Get detailed summary for a specific month.

        Args:
            year: Year
            month: Month (1-12)
            underlying: Optional filter by underlying

        Returns:
            Monthly summary with trade and position data
        """
        # Calculate month bounds
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1) - timedelta(seconds=1)
        else:
            end_date = datetime(year, month + 1, 1) - timedelta(seconds=1)

        # Get trades closed in this month
        trades_stmt = (
            select(Trade)
            .where(
                Trade.closed_at.isnot(None),
                Trade.closed_at >= start_date,
                Trade.closed_at <= end_date,
            )
        )

        if underlying:
            trades_stmt = trades_stmt.where(Trade.underlying == underlying)

        result = await self.session.execute(trades_stmt)
        trades = list(result.scalars().all())

        # Get positions expiring in this month
        positions_stmt = (
            select(Position)
            .where(
                Position.expiration.isnot(None),
                Position.expiration >= start_date,
                Position.expiration <= end_date,
            )
        )

        if underlying:
            positions_stmt = positions_stmt.where(Position.underlying == underlying)

        result = await self.session.execute(positions_stmt)
        positions = list(result.scalars().all())

        # Calculate statistics
        winning_trades = [t for t in trades if t.realized_pnl > 0]
        losing_trades = [t for t in trades if t.realized_pnl < 0]
        total_pnl = sum(t.realized_pnl for t in trades)
        total_commission = sum(t.total_commission for t in trades)

        return {
            "year": year,
            "month": month,
            "total_trades": len(trades),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": (len(winning_trades) / len(trades) * 100) if trades else 0.0,
            "total_pnl": total_pnl,
            "total_commission": total_commission,
            "net_pnl": total_pnl - total_commission,
            "positions_expiring": len(positions),
            "unique_underlyings_traded": len(set(t.underlying for t in trades)),
        }

    async def get_day_of_week_analysis(
        self,
        underlying: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[dict]:
        """Analyze performance by day of week.

        Args:
            underlying: Optional filter by underlying
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of statistics by day of week
        """
        stmt = select(Trade).where(Trade.closed_at.isnot(None), Trade.status == "CLOSED")

        if underlying:
            stmt = stmt.where(Trade.underlying == underlying)
        if start_date:
            stmt = stmt.where(Trade.closed_at >= start_date)
        if end_date:
            stmt = stmt.where(Trade.closed_at <= end_date)

        result = await self.session.execute(stmt)
        trades = list(result.scalars().all())

        # Group by day of week
        from collections import defaultdict

        by_day = defaultdict(list)
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        for trade in trades:
            if trade.closed_at:
                day_of_week = trade.closed_at.weekday()
                by_day[day_of_week].append(trade)

        # Calculate stats for each day
        day_stats = []
        for day_num in range(7):
            day_trades = by_day.get(day_num, [])
            if day_trades:
                winning = [t for t in day_trades if t.realized_pnl > 0]
                losing = [t for t in day_trades if t.realized_pnl < 0]
                total_pnl = sum(t.realized_pnl for t in day_trades)

                day_stats.append({
                    "day_of_week": day_names[day_num],
                    "day_number": day_num,
                    "total_trades": len(day_trades),
                    "winning_trades": len(winning),
                    "losing_trades": len(losing),
                    "win_rate": (len(winning) / len(day_trades) * 100),
                    "total_pnl": total_pnl,
                    "average_pnl": total_pnl / len(day_trades),
                })

        return day_stats
