"""Trade model - Grouped trades from executions."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from trading_journal.core.database import Base


def utcnow() -> datetime:
    """Return current UTC time as a timezone-aware datetime."""
    return datetime.now(UTC)


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

    # Timestamps (timezone-aware)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
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

    # ===========================================
    # Trade Open Snapshot (Greeks & IV at entry)
    # ===========================================
    underlying_price_open: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    iv_open: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))  # e.g., 0.35 for 35%
    iv_percentile_52w_open: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))  # 0-100
    iv_rank_52w_open: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))  # 0-100
    iv_percentile_custom_open: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    iv_rank_custom_open: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    iv_custom_period_days: Mapped[int | None] = mapped_column(Integer)  # Custom lookback period
    delta_open: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    gamma_open: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    theta_open: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    vega_open: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    rho_open: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    pop_open: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))  # Probability of Profit 0-100

    # Risk analytics at open
    max_profit: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    max_risk: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    collateral_calculated: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    collateral_ibkr: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    # ===========================================
    # Trade Close Snapshot (Greeks & IV at exit)
    # ===========================================
    underlying_price_close: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    iv_close: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    delta_close: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    gamma_close: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    theta_close: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    vega_close: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    rho_close: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    pnl_percent: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))  # % of max profit achieved

    # ===========================================
    # Greeks metadata
    # ===========================================
    greeks_source: Mapped[str | None] = mapped_column(String(20))  # IBKR, POLYGON, CALCULATED
    greeks_pending: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ===========================================
    # Tag relationship (many-to-many)
    # ===========================================
    tag_list: Mapped[list["Tag"]] = relationship(
        "Tag",
        secondary="trade_tags",
        back_populates="trades",
    )

    @property
    def days_held(self) -> int | None:
        """Calculate days held from open to close (or current date if still open)."""
        if self.opened_at is None:
            return None
        end_date = self.closed_at if self.closed_at else datetime.now(UTC)
        # Convert to date for calendar day calculation
        open_date = self.opened_at.date() if isinstance(self.opened_at, datetime) else self.opened_at
        close_date = end_date.date() if isinstance(end_date, datetime) else end_date
        return (close_date - open_date).days

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<Trade(id={self.id}, "
            f"underlying={self.underlying}, "
            f"strategy={self.strategy_type}, "
            f"status={self.status}, "
            f"pnl={self.total_pnl})>"
        )


# Import Tag at the end to avoid circular import
from trading_journal.models.tag import Tag  # noqa: E402, F401
