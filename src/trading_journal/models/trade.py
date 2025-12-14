"""Trade model - Grouped trades from executions."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from trading_journal.core.database import Base


class Trade(Base):
    """Grouped trade - result of trade grouping algorithm."""

    __tablename__ = "trades"
    __table_args__ = {"extend_existing": True}

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Trade identification
    underlying: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    strategy_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # Strategy types: Single, Vertical Call Spread, Vertical Put Spread,
    # Iron Condor, Butterfly, Complex, etc.

    # Trade status
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # Status: OPEN, CLOSED, EXPIRED, ROLLED

    # Timestamps
    opened_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # P&L tracking
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total_pnl: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))

    # Cost basis
    opening_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    closing_proceeds: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    total_commission: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))

    # Trade structure
    num_legs: Mapped[int] = mapped_column(Integer, nullable=False)
    num_executions: Mapped[int] = mapped_column(Integer, nullable=False)

    # Additional metadata
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[str | None] = mapped_column(String(255))  # Comma-separated tags

    # Roll tracking
    is_roll: Mapped[bool] = mapped_column(default=False, nullable=False)
    rolled_from_trade_id: Mapped[int | None] = mapped_column(Integer)
    rolled_to_trade_id: Mapped[int | None] = mapped_column(Integer)
    roll_chain_id: Mapped[int | None] = mapped_column(Integer, index=True)
    # roll_chain_id groups all trades in a roll sequence (shared ID)

    # Assignment tracking (option assigned/exercised to stock)
    is_assignment: Mapped[bool] = mapped_column(default=False, nullable=False)
    assigned_from_trade_id: Mapped[int | None] = mapped_column(Integer)
    # assigned_from_trade_id links to the option trade that was assigned

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<Trade(id={self.id}, "
            f"underlying={self.underlying}, "
            f"strategy={self.strategy_type}, "
            f"status={self.status}, "
            f"pnl={self.total_pnl})>"
        )
