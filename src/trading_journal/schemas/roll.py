"""Schemas for roll detection and tracking."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class RollDetectionRequest(BaseModel):
    """Request to detect rolls."""

    underlying: str | None = Field(None, description="Filter by underlying symbol")
    start_date: datetime | None = Field(None, description="Start date for analysis")
    end_date: datetime | None = Field(None, description="End date for analysis")


class RollDetectionResponse(BaseModel):
    """Response from roll detection."""

    trades_analyzed: int = Field(..., description="Number of trades analyzed")
    rolls_detected: int = Field(..., description="Number of roll relationships detected")
    roll_chains_found: int = Field(..., description="Number of unique roll chains found")
    message: str = Field(..., description="Summary message")


class RollChainTrade(BaseModel):
    """Trade summary in a roll chain."""

    id: int
    underlying: str
    strategy_type: str
    status: str
    opened_at: datetime
    closed_at: datetime | None
    total_pnl: Decimal
    num_legs: int
    is_roll: bool
    rolled_from_trade_id: int | None
    rolled_to_trade_id: int | None

    model_config = ConfigDict(from_attributes=True)


class RollChainResponse(BaseModel):
    """Response containing a complete roll chain."""

    chain_length: int = Field(..., description="Number of trades in the chain")
    total_pnl: Decimal = Field(..., description="Combined P&L for entire chain")
    trades: list[RollChainTrade] = Field(..., description="Trades in the chain")


class RollStatistics(BaseModel):
    """Statistics about rolled positions."""

    total_rolled_trades: int = Field(..., description="Total number of trades marked as rolls")
    unique_roll_chains: int = Field(..., description="Number of unique roll chains")
    max_chain_length: int = Field(..., description="Longest roll chain")
    average_chain_length: float = Field(..., description="Average length of roll chains")
    total_roll_pnl: Decimal = Field(..., description="Total P&L from all roll chains")
    average_roll_pnl: Decimal = Field(..., description="Average P&L per roll chain")
