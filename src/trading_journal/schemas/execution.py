"""Pydantic schemas for Execution model."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ExecutionBase(BaseModel):
    """Base execution schema."""

    exec_id: str = Field(..., description="IBKR execution ID")
    order_id: int = Field(..., description="IBKR order ID")
    perm_id: int = Field(..., description="IBKR permanent ID")
    execution_time: datetime = Field(..., description="Execution timestamp")
    underlying: str = Field(..., description="Underlying symbol", max_length=10)
    security_type: str = Field(..., description="Security type (OPT, STK)", max_length=10)
    exchange: str = Field(..., description="Exchange", max_length=20)
    currency: str = Field(default="USD", description="Currency", max_length=3)
    option_type: Optional[str] = Field(None, description="Option type (C or P)", max_length=1)
    strike: Optional[Decimal] = Field(None, description="Strike price")
    expiration: Optional[datetime] = Field(None, description="Expiration date")
    multiplier: Optional[int] = Field(None, description="Contract multiplier")
    side: str = Field(..., description="Side (BOT or SLD)", max_length=10)
    quantity: int = Field(..., description="Quantity executed")
    price: Decimal = Field(..., description="Execution price")
    commission: Decimal = Field(default=Decimal("0.00"), description="Commission paid")
    net_amount: Decimal = Field(..., description="Net amount (price * qty * multiplier)")
    account_id: str = Field(..., description="Account ID", max_length=50)


class ExecutionCreate(ExecutionBase):
    """Schema for creating an execution."""

    pass


class ExecutionResponse(ExecutionBase):
    """Schema for execution response."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Database ID")
    created_at: datetime = Field(..., description="Record creation timestamp")


class ExecutionList(BaseModel):
    """Schema for list of executions."""

    executions: list[ExecutionResponse]
    total: int
    limit: int
    offset: int


class ExecutionSyncRequest(BaseModel):
    """Schema for IBKR sync request."""

    days_back: int = Field(default=7, ge=1, le=30, description="Days to look back")
    host: Optional[str] = Field(None, description="IBKR host override")
    port: Optional[int] = Field(None, description="IBKR port override")


class ExecutionSyncResponse(BaseModel):
    """Schema for IBKR sync response."""

    fetched: int = Field(..., description="Number of executions fetched from IBKR")
    new: int = Field(..., description="Number of new executions created")
    existing: int = Field(..., description="Number of existing executions skipped")
    errors: int = Field(..., description="Number of errors encountered")
    message: str = Field(..., description="Result message")
