"""UnderlyingIVHistory model - Historical IV data for IV rank/percentile calculations."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from trading_journal.core.database import Base


class UnderlyingIVHistory(Base):
    """Historical implied volatility data for an underlying.

    Stores daily IV values for calculating IV rank and IV percentile.
    Data is forward-only (collected going forward) since Polygon.io
    Options Starter tier doesn't provide historical IV data.

    IV Rank = (Current IV - 52-week Low) / (52-week High - 52-week Low) * 100
    IV Percentile = % of days in period where IV was lower than current IV
    """

    __tablename__ = "underlying_iv_history"
    __table_args__ = (
        UniqueConstraint("underlying", "recorded_date", name="uix_underlying_date"),
    )

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Underlying identification
    underlying: Mapped[str] = mapped_column(String(10), nullable=False, index=True)

    # Date of IV observation (one record per underlying per day)
    recorded_date: Mapped[datetime] = mapped_column(Date, nullable=False, index=True)

    # IV values
    iv: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)  # e.g., 0.35 for 35%
    iv_high: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))  # Intraday high
    iv_low: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))  # Intraday low

    # Underlying price at time of IV capture
    underlying_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))

    # Data source
    data_source: Mapped[str] = mapped_column(String(20), nullable=False)  # IBKR, POLYGON

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<UnderlyingIVHistory(underlying={self.underlying}, "
            f"date={self.recorded_date}, "
            f"iv={self.iv})>"
        )
