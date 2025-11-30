"""Greeks model - Historical Greeks data for options."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from trading_journal.core.database import Base


class Greeks(Base):
    """Historical Greeks data for option positions."""

    __tablename__ = "greeks"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to position
    position_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("positions.id"), nullable=False, index=True
    )

    # Timestamp
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    # Greeks values
    delta: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    gamma: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    theta: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    vega: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    rho: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))

    # Implied volatility
    implied_volatility: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))

    # Underlying price at time of Greeks calculation
    underlying_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    option_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))

    # Model type used for calculation
    model_type: Mapped[str] = mapped_column(String(20), default="IBKR", nullable=False)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<Greeks(position_id={self.position_id}, "
            f"timestamp={self.timestamp}, "
            f"delta={self.delta}, "
            f"gamma={self.gamma}, "
            f"theta={self.theta})>"
        )
