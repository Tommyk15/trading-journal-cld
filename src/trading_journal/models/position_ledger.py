"""Position Ledger model - Persistent position tracking."""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from sqlalchemy import DateTime, Integer, Numeric, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from trading_journal.core.database import Base


class PositionStatus(str, Enum):
    """Position status enum."""
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class PositionLedger(Base):
    """Persistent position ledger tracking current and historical positions.

    This table tracks the actual position state per leg, allowing the system to:
    1. Know current position before processing new executions
    2. Detect rolls (closing one leg, opening different leg same day)
    3. Track position lifecycle for analytics
    """

    __tablename__ = "position_ledger"
    __table_args__ = {"extend_existing": True}

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Position identification
    underlying: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    leg_key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # leg_key format: "YYYYMMDD_strike_type" e.g., "20251219_245.0_C" or "STK"

    # Position state
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Positive = long, Negative = short

    # Cost tracking
    avg_cost: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0.00"))
    total_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))

    # Lifecycle tracking
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=PositionStatus.OPEN.value)
    opened_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Link to current trade (if grouped)
    trade_id: Mapped[int | None] = mapped_column(ForeignKey("trades.id", ondelete="SET NULL"), index=True)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<PositionLedger(id={self.id}, "
            f"underlying={self.underlying}, "
            f"leg_key={self.leg_key}, "
            f"qty={self.quantity}, "
            f"status={self.status})>"
        )

    @property
    def is_flat(self) -> bool:
        """Check if position is flat (zero quantity)."""
        return self.quantity == 0

    @property
    def is_long(self) -> bool:
        """Check if position is long."""
        return self.quantity > 0

    @property
    def is_short(self) -> bool:
        """Check if position is short."""
        return self.quantity < 0
