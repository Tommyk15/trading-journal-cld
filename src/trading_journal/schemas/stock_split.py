"""Pydantic schemas for StockSplit model."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class StockSplitBase(BaseModel):
    """Base stock split schema."""

    symbol: str = Field(..., description="Stock symbol", max_length=10)
    split_date: datetime = Field(..., description="Date the split took effect")
    ratio_from: int = Field(..., ge=1, description="Original shares (e.g., 4 for 4:1 reverse)")
    ratio_to: int = Field(..., ge=1, description="New shares (e.g., 1 for 4:1 reverse)")
    description: str | None = Field(None, description="Optional description", max_length=255)


class StockSplitCreate(StockSplitBase):
    """Schema for creating a stock split."""

    pass


class StockSplitResponse(StockSplitBase):
    """Schema for stock split response."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Database ID")
    created_at: datetime = Field(..., description="Record creation timestamp")
    adjustment_factor: Decimal = Field(..., description="Quantity adjustment factor")
    price_factor: Decimal = Field(..., description="Price adjustment factor")
    is_reverse_split: bool = Field(..., description="Whether this is a reverse split")


class StockSplitList(BaseModel):
    """Schema for list of stock splits."""

    splits: list[StockSplitResponse]
    total: int


class SplitAdjustment(BaseModel):
    """Schema for split-adjusted values."""

    original_quantity: int | float
    original_price: Decimal
    adjusted_quantity: float
    adjusted_price: Decimal
    splits_applied: list[StockSplitResponse]
