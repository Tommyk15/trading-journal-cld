"""TradeLegGreeks model - Per-leg Greeks data for trades."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from trading_journal.core.database import Base


class TradeLegGreeks(Base):
    """Per-leg Greeks snapshot for a trade.

    Captures Greeks, bid/ask spread, open interest, and volume for each leg
    of a multi-leg options trade at a specific point in time (open or close).
    """

    __tablename__ = "trade_leg_greeks"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to trade
    trade_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("trades.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Snapshot type: OPEN or CLOSE
    snapshot_type: Mapped[str] = mapped_column(String(10), nullable=False)

    # Leg identification
    leg_index: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-based leg order
    underlying: Mapped[str] = mapped_column(String(10), nullable=False)
    option_type: Mapped[str | None] = mapped_column(String(1))  # C or P (NULL for stock)
    strike: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    expiration: Mapped[datetime | None] = mapped_column(DateTime)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)  # Signed: + for long, - for short

    # Greeks
    delta: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    gamma: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    theta: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    vega: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    rho: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    iv: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))  # Implied volatility

    # Price data
    underlying_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    option_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    bid: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    ask: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    bid_ask_spread: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))

    # Market data
    open_interest: Mapped[int | None] = mapped_column(Integer)
    volume: Mapped[int | None] = mapped_column(Integer)

    # Data source
    data_source: Mapped[str | None] = mapped_column(String(20))  # IBKR, POLYGON

    # Metadata
    captured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<TradeLegGreeks(trade_id={self.trade_id}, "
            f"leg={self.leg_index}, "
            f"type={self.snapshot_type}, "
            f"delta={self.delta})>"
        )
