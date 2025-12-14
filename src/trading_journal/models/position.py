"""Position model - Current open positions."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from trading_journal.core.database import Base


class Position(Base):
    """Current open position - linked to a trade."""

    __tablename__ = "positions"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to trade
    trade_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("trades.id"), nullable=False, index=True
    )

    # Contract details
    underlying: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    option_type: Mapped[str | None] = mapped_column(String(1))  # C or P (NULL for stocks)
    strike: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    expiration: Mapped[datetime | None] = mapped_column(DateTime, index=True)

    # Position details
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_cost: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))

    # P&L
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False
    )

    def __repr__(self) -> str:
        """String representation."""
        position_str = f"{self.underlying}"
        if self.option_type:
            position_str += f" {self.strike}{self.option_type}"
        return (
            f"<Position(id={self.id}, "
            f"trade_id={self.trade_id}, "
            f"{position_str}, "
            f"qty={self.quantity})>"
        )
