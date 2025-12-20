"""Stock Split model for tracking corporate actions."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from trading_journal.core.database import Base


def utcnow_naive() -> datetime:
    """Return current UTC time as a timezone-naive datetime for DB storage."""
    return datetime.now(UTC).replace(tzinfo=None)


class StockSplit(Base):
    """Stock split record for adjusting historical quantities and prices.

    For a 4:1 reverse split (4 shares become 1):
        - ratio_from = 4, ratio_to = 1
        - Adjusted quantity = original_quantity / 4
        - Adjusted price = original_price * 4

    For a 2:1 forward split (1 share becomes 2):
        - ratio_from = 1, ratio_to = 2
        - Adjusted quantity = original_quantity * 2
        - Adjusted price = original_price / 2
    """

    __tablename__ = "stock_splits"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Symbol affected by the split
    symbol: Mapped[str] = mapped_column(String(10), nullable=False, index=True)

    # Split date (when the split took effect)
    split_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    # Split ratio: ratio_from shares become ratio_to shares
    # e.g., 4:1 reverse split = ratio_from=4, ratio_to=1
    # e.g., 2:1 forward split = ratio_from=1, ratio_to=2
    ratio_from: Mapped[int] = mapped_column(Integer, nullable=False)
    ratio_to: Mapped[int] = mapped_column(Integer, nullable=False)

    # Optional description
    description: Mapped[str | None] = mapped_column(String(255))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

    @property
    def adjustment_factor(self) -> Decimal:
        """Get the factor to multiply quantities by.

        For reverse splits (4:1), this returns 0.25 (divide quantity by 4)
        For forward splits (1:2), this returns 2.0 (multiply quantity by 2)
        """
        return Decimal(self.ratio_to) / Decimal(self.ratio_from)

    @property
    def price_factor(self) -> Decimal:
        """Get the factor to multiply prices by.

        For reverse splits (4:1), this returns 4.0 (multiply price by 4)
        For forward splits (1:2), this returns 0.5 (divide price by 2)
        """
        return Decimal(self.ratio_from) / Decimal(self.ratio_to)

    @property
    def is_reverse_split(self) -> bool:
        """Check if this is a reverse split (shares decrease)."""
        return self.ratio_from > self.ratio_to

    def __repr__(self) -> str:
        """String representation."""
        split_type = "reverse" if self.is_reverse_split else "forward"
        return (
            f"<StockSplit({self.symbol} {self.ratio_from}:{self.ratio_to} "
            f"{split_type} on {self.split_date.date()})>"
        )
