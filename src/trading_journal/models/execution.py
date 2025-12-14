"""Execution model - Raw execution data from IBKR."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from trading_journal.core.database import Base


class Execution(Base):
    """Raw execution data from IBKR API."""

    __tablename__ = "executions"
    __table_args__ = {"extend_existing": True}

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to trade (nullable for executions not yet grouped)
    trade_id: Mapped[int | None] = mapped_column(ForeignKey("trades.id", ondelete="SET NULL"), index=True)

    # IBKR identifiers
    exec_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    order_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    perm_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Timestamps
    execution_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Contract details
    underlying: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    security_type: Mapped[str] = mapped_column(String(10), nullable=False)  # OPT, STK, etc.
    exchange: Mapped[str] = mapped_column(String(20), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)

    # Option-specific fields (NULL for stocks)
    option_type: Mapped[str | None] = mapped_column(String(1))  # C or P
    strike: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    expiration: Mapped[datetime | None] = mapped_column(DateTime)
    multiplier: Mapped[int | None] = mapped_column(Integer, default=100)

    # Execution details
    side: Mapped[str] = mapped_column(String(10), nullable=False)  # BOT or SLD
    open_close_indicator: Mapped[str | None] = mapped_column(String(1))  # O or C
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    commission: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))

    # Calculated fields
    net_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # Metadata
    account_id: Mapped[str] = mapped_column(String(50), nullable=False)

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<Execution(exec_id={self.exec_id}, "
            f"underlying={self.underlying}, "
            f"side={self.side}, "
            f"qty={self.quantity}, "
            f"price={self.price})>"
        )
