"""Pydantic schemas for Trade model."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TradeBase(BaseModel):
    """Base trade schema."""

    underlying: str = Field(..., description="Underlying symbol", max_length=10)
    strategy_type: str = Field(..., description="Strategy classification", max_length=50)
    status: str = Field(..., description="Trade status (OPEN, CLOSED, EXPIRED)", max_length=20)
    notes: Optional[str] = Field(None, description="User notes")
    tags: Optional[str] = Field(None, description="Comma-separated tags", max_length=255)


class TradeCreate(TradeBase):
    """Schema for creating a trade."""

    opened_at: datetime = Field(..., description="Opening timestamp")
    closed_at: Optional[datetime] = Field(None, description="Closing timestamp")
    realized_pnl: Decimal = Field(default=Decimal("0.00"), description="Realized P&L")
    unrealized_pnl: Decimal = Field(default=Decimal("0.00"), description="Unrealized P&L")
    total_pnl: Decimal = Field(default=Decimal("0.00"), description="Total P&L")
    opening_cost: Decimal = Field(..., description="Opening cost")
    closing_proceeds: Optional[Decimal] = Field(None, description="Closing proceeds")
    total_commission: Decimal = Field(default=Decimal("0.00"), description="Total commissions")
    num_legs: int = Field(..., description="Number of legs")
    num_executions: int = Field(..., description="Number of executions")


class TradeUpdate(BaseModel):
    """Schema for updating a trade."""

    notes: Optional[str] = None
    tags: Optional[str] = None
    status: Optional[str] = None


class TradeResponse(TradeBase):
    """Schema for trade response."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Database ID")
    opened_at: datetime = Field(..., description="Opening timestamp")
    closed_at: Optional[datetime] = Field(None, description="Closing timestamp")
    realized_pnl: Decimal = Field(..., description="Realized P&L")
    unrealized_pnl: Decimal = Field(..., description="Unrealized P&L")
    total_pnl: Decimal = Field(..., description="Total P&L")
    opening_cost: Decimal = Field(..., description="Opening cost")
    closing_proceeds: Optional[Decimal] = Field(None, description="Closing proceeds")
    total_commission: Decimal = Field(..., description="Total commissions")
    num_legs: int = Field(..., description="Number of legs")
    num_executions: int = Field(..., description="Number of executions")
    is_roll: bool = Field(..., description="Whether this is a roll")
    rolled_from_trade_id: Optional[int] = Field(None, description="Rolled from trade ID")
    rolled_to_trade_id: Optional[int] = Field(None, description="Rolled to trade ID")
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Record update timestamp")


class TradeList(BaseModel):
    """Schema for list of trades."""

    trades: list[TradeResponse]
    total: int
    limit: int
    offset: int


class TradeProcessRequest(BaseModel):
    """Schema for trade processing request."""

    underlying: Optional[str] = Field(None, description="Filter by underlying")
    start_date: Optional[datetime] = Field(None, description="Start date filter")
    end_date: Optional[datetime] = Field(None, description="End date filter")


class TradeProcessResponse(BaseModel):
    """Schema for trade processing response."""

    executions_processed: int = Field(..., description="Number of executions processed")
    trades_created: int = Field(..., description="Number of trades created")
    trades_updated: int = Field(..., description="Number of trades updated")
    message: str = Field(..., description="Result message")
