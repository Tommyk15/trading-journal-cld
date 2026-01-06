"""Pydantic schemas for Trade model."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    pass


class TagInTrade(BaseModel):
    """Embedded tag schema for trade response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: str


class TradeBase(BaseModel):
    """Base trade schema."""

    underlying: str = Field(..., description="Underlying symbol", max_length=10)
    strategy_type: str = Field(..., description="Strategy classification", max_length=50)
    status: str = Field(..., description="Trade status (OPEN, CLOSED, EXPIRED)", max_length=20)
    notes: str | None = Field(None, description="User notes")
    tags: str | None = Field(None, description="Comma-separated tags", max_length=255)


class TradeCreate(TradeBase):
    """Schema for creating a trade."""

    opened_at: datetime = Field(..., description="Opening timestamp")
    closed_at: datetime | None = Field(None, description="Closing timestamp")
    realized_pnl: Decimal = Field(default=Decimal("0.00"), description="Realized P&L")
    unrealized_pnl: Decimal = Field(default=Decimal("0.00"), description="Unrealized P&L")
    total_pnl: Decimal = Field(default=Decimal("0.00"), description="Total P&L")
    opening_cost: Decimal = Field(..., description="Opening cost")
    closing_proceeds: Decimal | None = Field(None, description="Closing proceeds")
    total_commission: Decimal = Field(default=Decimal("0.00"), description="Total commissions")
    num_legs: int = Field(..., description="Number of legs")
    num_executions: int = Field(..., description="Number of executions")


class TradeUpdate(BaseModel):
    """Schema for updating a trade."""

    notes: str | None = None
    tags: str | None = None
    status: str | None = None


class TradeResponse(TradeBase):
    """Schema for trade response."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Database ID")
    opened_at: datetime = Field(..., description="Opening timestamp")
    closed_at: datetime | None = Field(None, description="Closing timestamp")
    realized_pnl: Decimal = Field(..., description="Realized P&L")
    unrealized_pnl: Decimal = Field(..., description="Unrealized P&L")
    total_pnl: Decimal = Field(..., description="Total P&L")
    opening_cost: Decimal = Field(..., description="Opening cost")
    closing_proceeds: Decimal | None = Field(None, description="Closing proceeds")
    total_commission: Decimal = Field(..., description="Total commissions")

    # Wash sale tracking
    wash_sale_adjustment: Decimal = Field(
        default=Decimal("0.00"),
        description="Wash sale disallowed loss added to cost basis"
    )
    wash_sale_from_trade_ids: str | None = Field(
        None, description="Comma-separated IDs of trades that triggered wash sale"
    )
    num_legs: int = Field(..., description="Number of legs")
    num_executions: int = Field(..., description="Number of executions")
    is_roll: bool = Field(..., description="Whether this is a roll")
    rolled_from_trade_id: int | None = Field(None, description="Rolled from trade ID")
    rolled_to_trade_id: int | None = Field(None, description="Rolled to trade ID")
    is_assignment: bool = Field(False, description="Whether this is from option assignment")
    assigned_from_trade_id: int | None = Field(None, description="Option trade that was assigned")
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Record update timestamp")

    # Trade Open Snapshot (Greeks & IV at entry)
    underlying_price_open: Decimal | None = Field(None, description="Underlying price at open")
    iv_open: Decimal | None = Field(None, description="IV at open (decimal, e.g. 0.35 for 35%)")
    iv_percentile_52w_open: Decimal | None = Field(None, description="IV percentile (52 week)")
    iv_rank_52w_open: Decimal | None = Field(None, description="IV rank (52 week)")
    delta_open: Decimal | None = Field(None, description="Net delta at open")
    gamma_open: Decimal | None = Field(None, description="Net gamma at open")
    theta_open: Decimal | None = Field(None, description="Net theta at open")
    vega_open: Decimal | None = Field(None, description="Net vega at open")
    pop_open: Decimal | None = Field(None, description="Probability of profit at open")
    max_profit: Decimal | None = Field(None, description="Maximum potential profit")
    max_risk: Decimal | None = Field(None, description="Maximum potential risk")

    # Trade Close Snapshot
    underlying_price_close: Decimal | None = Field(None, description="Underlying price at close")
    iv_close: Decimal | None = Field(None, description="IV at close")
    delta_close: Decimal | None = Field(None, description="Net delta at close")
    pnl_percent: Decimal | None = Field(None, description="P&L as % of max profit")

    # Greeks metadata
    greeks_source: str | None = Field(None, description="Data source (IBKR, POLYGON, etc)")
    greeks_pending: bool = Field(False, description="Whether Greeks fetch is pending")

    # Tags (many-to-many relationship)
    tag_list: list[TagInTrade] = Field(default_factory=list, description="Tags assigned to this trade")


class TradeList(BaseModel):
    """Schema for list of trades."""

    trades: list[TradeResponse]
    total: int
    limit: int
    offset: int


class TradeProcessRequest(BaseModel):
    """Schema for trade processing request."""

    underlying: str | None = Field(None, description="Filter by underlying")
    start_date: datetime | None = Field(None, description="Start date filter")
    end_date: datetime | None = Field(None, description="End date filter")


class TradeProcessResponse(BaseModel):
    """Schema for trade processing response."""

    executions_processed: int = Field(..., description="Number of executions processed")
    trades_created: int = Field(..., description="Number of trades created")
    trades_updated: int = Field(..., description="Number of trades updated")
    message: str = Field(..., description="Result message")
    greeks_fetched: int | None = Field(None, description="Number of trades with Greeks fetched")
    greeks_failed: int | None = Field(None, description="Number of trades where Greeks fetch failed")


class ManualTradeCreateRequest(BaseModel):
    """Schema for manual trade creation request."""

    execution_ids: list[int] = Field(..., description="List of execution IDs to group")
    strategy_type: str = Field(..., description="Strategy type", max_length=50)
    custom_strategy: str | None = Field(None, description="Custom strategy name if 'Custom' selected")
    notes: str | None = Field(None, description="Trade notes")
    tags: str | None = Field(None, description="Comma-separated tags", max_length=255)
    auto_match_closes: bool = Field(True, description="Auto-match closing transactions for opens using FIFO")


class TradeExecutionsUpdateRequest(BaseModel):
    """Schema for adding/removing executions from a trade."""

    add_execution_ids: list[int] | None = Field(None, description="Execution IDs to add")
    remove_execution_ids: list[int] | None = Field(None, description="Execution IDs to remove")


class SuggestedGroupLeg(BaseModel):
    """Schema for a leg within a suggested trade group."""

    option_type: str | None = Field(None, description="Option type (C or P)")
    strike: float | None = Field(None, description="Strike price")
    expiration: str | None = Field(None, description="Expiration date")
    security_type: str = Field(..., description="Security type (OPT, STK)")
    total_quantity: int = Field(..., description="Net quantity position")
    actions: list[str] = Field(..., description="Actions involved (BTO, BTC, STO, STC)")


class SuggestedGroup(BaseModel):
    """Schema for a suggested trade group."""

    execution_ids: list[int] = Field(..., description="Execution IDs in this group")
    suggested_strategy: str = Field(..., description="Suggested strategy type")
    underlying: str = Field(..., description="Underlying symbol")
    total_pnl: float = Field(..., description="Estimated P&L for this group")
    status: str = Field(..., description="Trade status (OPEN, CLOSED)")
    legs: list[SuggestedGroupLeg] = Field(default_factory=list, description="Trade legs")
    open_date: str | None = Field(None, description="Open date")
    close_date: str | None = Field(None, description="Close date")
    num_executions: int = Field(..., description="Number of executions")


class SuggestGroupingRequest(BaseModel):
    """Schema for suggested grouping request."""

    execution_ids: list[int] | None = Field(None, description="Specific execution IDs to analyze (optional)")


class SuggestGroupingResponse(BaseModel):
    """Schema for suggested grouping response."""

    groups: list[SuggestedGroup] = Field(..., description="Suggested trade groups")
    message: str = Field(..., description="Result message")


class MergeTradesRequest(BaseModel):
    """Schema for merge trades request."""

    trade_ids: list[int] = Field(..., description="List of trade IDs to merge (minimum 2)", min_length=2)
