"""Schemas for positions."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PositionSyncRequest(BaseModel):
    """Request to sync positions from IBKR."""

    host: str | None = Field(None, description="IBKR host (optional)")
    port: int | None = Field(None, description="IBKR port (optional)")


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
    option_type: str | None
    strike: Decimal | None
    expiration: datetime | None
    quantity: int
    avg_cost: Decimal
    current_price: Decimal | None
    unrealized_pnl: Decimal
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PositionList(BaseModel):
    """Response containing list of positions."""

    positions: list[PositionResponse] = Field(..., description="List of positions")
    total: int = Field(..., description="Total number of positions")
