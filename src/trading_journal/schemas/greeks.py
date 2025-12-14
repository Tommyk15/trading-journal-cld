"""Schemas for Greeks data."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class GreeksFetchRequest(BaseModel):
    """Request to fetch Greeks from IBKR."""

    host: str | None = Field(None, description="IBKR host (optional)")
    port: int | None = Field(None, description="IBKR port (optional)")


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
    delta: Decimal | None
    gamma: Decimal | None
    theta: Decimal | None
    vega: Decimal | None
    rho: Decimal | None
    implied_volatility: Decimal | None
    underlying_price: Decimal | None
    option_price: Decimal | None
    model_type: str

    model_config = ConfigDict(from_attributes=True)


class GreeksHistoryResponse(BaseModel):
    """Response containing Greeks history."""

    greeks: list[GreeksResponse] = Field(..., description="List of Greeks snapshots")
    total: int = Field(..., description="Total number of records")
    position_id: int = Field(..., description="Position ID")
