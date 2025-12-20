"""Tag model for categorizing trades."""

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from trading_journal.core.database import Base


def utcnow() -> datetime:
    """Return current UTC time as a timezone-aware datetime."""
    return datetime.now(UTC)


# Association table for many-to-many relationship between trades and tags
trade_tags = Table(
    "trade_tags",
    Base.metadata,
    Column("trade_id", Integer, ForeignKey("trades.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Tag(Base):
    """Tag for categorizing trades."""

    __tablename__ = "tags"
    __table_args__ = {"extend_existing": True}

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Tag name (unique)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)

    # Color for UI display (hex color code, e.g., "#3B82F6")
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#6B7280")

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationship to trades (many-to-many)
    trades: Mapped[list["Trade"]] = relationship(
        "Trade",
        secondary=trade_tags,
        back_populates="tag_list",
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<Tag(id={self.id}, name={self.name}, color={self.color})>"


# Import Trade at the end to avoid circular import
from trading_journal.models.trade import Trade  # noqa: E402, F401
