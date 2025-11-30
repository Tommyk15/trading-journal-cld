"""Schemas for Greeks data."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class GreeksFetchRequest(BaseModel):
    """Request to fetch Greeks from IBKR."""

    host: Optional[str] = Field(None, description="IBKR host (optional)")
    port: Optional[int] = Field(None, description="IBKR port (optional)")


class GreeksFetchResponse(BaseModel):
    """Response from Greeks fetch operation."""

    positions_processed: int = Field(..., description="Number of positions processed")
    greeks_fetched: int = Field(..., description="Number of Greeks fetched")
    errors: int = Field(..., description="Number of errors")
    message: str = Field(..., description="Summary message")


class GreeksResponse(BaseModel):
    """Greeks data for a position."""

    id: int
    position_id: int
    timestamp: datetime
    delta: Optional[Decimal]
    gamma: Optional[Decimal]
    theta: Optional[Decimal]
    vega: Optional[Decimal]
    rho: Optional[Decimal]
    implied_volatility: Optional[Decimal]
    underlying_price: Optional[Decimal]
    option_price: Optional[Decimal]
    model_type: str

    class Config:
        from_attributes = True


class GreeksHistoryResponse(BaseModel):
    """Response containing Greeks history."""

    greeks: list[GreeksResponse] = Field(..., description="List of Greeks snapshots")
    total: int = Field(..., description="Total number of records")
    position_id: int = Field(..., description="Position ID")
