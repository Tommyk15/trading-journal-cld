"""IV History Service - IV rank and percentile calculations."""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.models.underlying_iv_history import UnderlyingIVHistory

logger = logging.getLogger(__name__)

# Default lookback periods
DEFAULT_LOOKBACK_DAYS = 252  # ~1 trading year (52 weeks)
CUSTOM_LOOKBACK_DAYS = 30  # Default custom period


class IVHistoryService:
    """Service for IV history management and rank/percentile calculations.

    IV Rank = (Current IV - Period Low) / (Period High - Period Low) * 100
    IV Percentile = % of days in period where IV was lower than current IV

    Note: Data is collected forward-only since Polygon.io Options Starter
    tier doesn't provide historical IV data.
    """

    def __init__(self, session: AsyncSession):
        """Initialize IV History service.

        Args:
            session: Database session
        """
        self.session = session

    async def record_iv(
        self,
        underlying: str,
        iv: Decimal,
        underlying_price: Decimal | None = None,
        iv_high: Decimal | None = None,
        iv_low: Decimal | None = None,
        data_source: str = "POLYGON",
    ) -> UnderlyingIVHistory:
        """Record a daily IV observation.

        Args:
            underlying: Underlying symbol
            iv: Implied volatility value
            underlying_price: Underlying price at time of IV capture
            iv_high: Intraday IV high (optional)
            iv_low: Intraday IV low (optional)
            data_source: Source of IV data

        Returns:
            Created or updated UnderlyingIVHistory record
        """
        today = datetime.now(UTC).date()

        # Check if we already have a record for today
        stmt = select(UnderlyingIVHistory).where(
            UnderlyingIVHistory.underlying == underlying,
            UnderlyingIVHistory.recorded_date == today,
        )
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing record
            existing.iv = iv
            if underlying_price is not None:
                existing.underlying_price = underlying_price
            if iv_high is not None:
                existing.iv_high = iv_high
            if iv_low is not None:
                existing.iv_low = iv_low
            await self.session.flush()
            return existing

        # Create new record
        record = UnderlyingIVHistory(
            underlying=underlying,
            recorded_date=today,
            iv=iv,
            iv_high=iv_high,
            iv_low=iv_low,
            underlying_price=underlying_price,
            data_source=data_source,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_iv_history(
        self,
        underlying: str,
        days: int = DEFAULT_LOOKBACK_DAYS,
    ) -> list[UnderlyingIVHistory]:
        """Get IV history for an underlying.

        Args:
            underlying: Underlying symbol
            days: Number of days to look back

        Returns:
            List of IV history records, oldest first
        """
        start_date = datetime.now(UTC).date() - timedelta(days=days)

        stmt = (
            select(UnderlyingIVHistory)
            .where(
                UnderlyingIVHistory.underlying == underlying,
                UnderlyingIVHistory.recorded_date >= start_date,
            )
            .order_by(UnderlyingIVHistory.recorded_date.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def calculate_iv_rank(
        self,
        underlying: str,
        current_iv: Decimal,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    ) -> Decimal | None:
        """Calculate IV Rank for an underlying.

        IV Rank = (Current IV - Period Low) / (Period High - Period Low) * 100

        Args:
            underlying: Underlying symbol
            current_iv: Current implied volatility
            lookback_days: Number of days to look back

        Returns:
            IV Rank as percentage (0-100) or None if insufficient data
        """
        history = await self.get_iv_history(underlying, lookback_days)

        if len(history) < 5:  # Require minimum data points
            logger.warning(
                f"Insufficient IV history for {underlying}: {len(history)} records"
            )
            return None

        iv_values = [record.iv for record in history]
        period_low = min(iv_values)
        period_high = max(iv_values)

        if period_high == period_low:
            return Decimal("50")  # No range, return 50%

        iv_rank = (current_iv - period_low) / (period_high - period_low) * 100
        return Decimal(str(round(float(iv_rank), 2)))

    async def calculate_iv_percentile(
        self,
        underlying: str,
        current_iv: Decimal,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    ) -> Decimal | None:
        """Calculate IV Percentile for an underlying.

        IV Percentile = % of days in period where IV was lower than current IV

        Args:
            underlying: Underlying symbol
            current_iv: Current implied volatility
            lookback_days: Number of days to look back

        Returns:
            IV Percentile as percentage (0-100) or None if insufficient data
        """
        history = await self.get_iv_history(underlying, lookback_days)

        if len(history) < 5:  # Require minimum data points
            logger.warning(
                f"Insufficient IV history for {underlying}: {len(history)} records"
            )
            return None

        iv_values = [record.iv for record in history]
        days_below = sum(1 for iv in iv_values if iv < current_iv)

        iv_percentile = (days_below / len(iv_values)) * 100
        return Decimal(str(round(iv_percentile, 2)))

    async def get_iv_metrics(
        self,
        underlying: str,
        current_iv: Decimal,
        custom_period_days: int | None = None,
    ) -> dict:
        """Get all IV metrics for an underlying.

        Args:
            underlying: Underlying symbol
            current_iv: Current implied volatility
            custom_period_days: Custom lookback period in days

        Returns:
            Dictionary with IV rank and percentile for 52-week and custom periods
        """
        # 52-week metrics
        iv_rank_52w = await self.calculate_iv_rank(underlying, current_iv, DEFAULT_LOOKBACK_DAYS)
        iv_percentile_52w = await self.calculate_iv_percentile(
            underlying, current_iv, DEFAULT_LOOKBACK_DAYS
        )

        result = {
            "iv_rank_52w": iv_rank_52w,
            "iv_percentile_52w": iv_percentile_52w,
            "iv_rank_custom": None,
            "iv_percentile_custom": None,
            "custom_period_days": custom_period_days,
        }

        # Custom period metrics
        if custom_period_days:
            result["iv_rank_custom"] = await self.calculate_iv_rank(
                underlying, current_iv, custom_period_days
            )
            result["iv_percentile_custom"] = await self.calculate_iv_percentile(
                underlying, current_iv, custom_period_days
            )

        return result

    async def get_iv_statistics(
        self,
        underlying: str,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    ) -> dict | None:
        """Get IV statistics for an underlying.

        Args:
            underlying: Underlying symbol
            lookback_days: Number of days to look back

        Returns:
            Dictionary with min, max, mean, current IV and data count
        """
        history = await self.get_iv_history(underlying, lookback_days)

        if not history:
            return None

        iv_values = [float(record.iv) for record in history]

        return {
            "underlying": underlying,
            "period_days": lookback_days,
            "data_points": len(history),
            "iv_min": Decimal(str(min(iv_values))),
            "iv_max": Decimal(str(max(iv_values))),
            "iv_mean": Decimal(str(round(sum(iv_values) / len(iv_values), 6))),
            "iv_current": history[-1].iv if history else None,
            "first_date": history[0].recorded_date if history else None,
            "last_date": history[-1].recorded_date if history else None,
        }

    async def cleanup_old_data(self, days_to_keep: int = 400) -> int:
        """Remove IV history older than specified days.

        Args:
            days_to_keep: Number of days of history to retain

        Returns:
            Number of records deleted
        """
        from sqlalchemy import delete

        cutoff_date = datetime.now(UTC).date() - timedelta(days=days_to_keep)

        stmt = delete(UnderlyingIVHistory).where(
            UnderlyingIVHistory.recorded_date < cutoff_date
        )
        result = await self.session.execute(stmt)
        await self.session.commit()

        return result.rowcount
