"""MarginSettings model - Per-underlying margin configuration."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from trading_journal.core.database import Base


class MarginSettings(Base):
    """Per-underlying margin percentage configuration.

    Allows customization of margin requirements for collateral calculations.
    Different underlyings may have different margin requirements based on
    their volatility, liquidity, or broker-specific rules.
    """

    __tablename__ = "margin_settings"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Underlying identification (unique)
    underlying: Mapped[str] = mapped_column(String(10), unique=True, nullable=False, index=True)

    # Margin percentages for different strategy types
    naked_put_margin_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("20.00"), nullable=False
    )  # Default 20%
    naked_call_margin_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("20.00"), nullable=False
    )
    spread_margin_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("100.00"), nullable=False
    )  # Spreads typically require full width
    iron_condor_margin_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("100.00"), nullable=False
    )

    # Notes for why this underlying has custom settings
    notes: Mapped[str | None] = mapped_column(String(255))

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<MarginSettings(underlying={self.underlying}, "
            f"naked_put={self.naked_put_margin_pct}%)>"
        )
