"""Schemas for positions."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class PositionSyncRequest(BaseModel):
    """Request to sync positions from IBKR."""

    host: Optional[str] = Field(None, description="IBKR host (optional)")
    port: Optional[int] = Field(None, description="IBKR port (optional)")


class PositionSyncResponse(BaseModel):
    """Response from position sync operation."""

    fetched: int = Field(..., description="Number of positions fetched from IBKR")
    created: int = Field(..., description="Number of new positions created")
    updated: int = Field(..., description="Number of positions updated")
    errors: int = Field(..., description="Number of errors")
    message: str = Field(..., description="Summary message")


class PositionResponse(BaseModel):
    """Position data."""

    id: int
    trade_id: int
    underlying: str
    option_type: Optional[str]
    strike: Optional[Decimal]
    expiration: Optional[datetime]
    quantity: int
    avg_cost: Decimal
    current_price: Optional[Decimal]
    unrealized_pnl: Decimal
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PositionList(BaseModel):
    """Response containing list of positions."""

    positions: list[PositionResponse] = Field(..., description="List of positions")
    total: int = Field(..., description="Total number of positions")
