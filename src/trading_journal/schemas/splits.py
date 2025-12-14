"""Schemas for stock split detection and reporting."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class DetectedSplit(BaseModel):
    """Information about a detected stock split."""

    ratio: str
    date: str
    pre_split_qty: int
    adjusted_qty: int

    model_config = ConfigDict(from_attributes=True)


class SplitIssue(BaseModel):
    """Details about a stock position with split-related issues."""

    underlying: str
    raw_net_position: int
    adjusted_net_position: int
    net_pnl: float
    detected_splits: list[DetectedSplit]
    recommendation: str

    model_config = ConfigDict(from_attributes=True)


class SplitReport(BaseModel):
    """Full report of split detection scan."""

    total_stocks_scanned: int
    issues_found: int
    details: list[SplitIssue]

    model_config = ConfigDict(from_attributes=True)


class PositionAnalysis(BaseModel):
    """Detailed analysis of a stock position for splits."""

    underlying: str
    raw_shares_bought: int
    raw_shares_sold: int
    raw_net_position: int
    adjusted_shares_bought: int
    adjusted_net_position: int
    total_cost: Decimal
    total_proceeds: Decimal
    net_pnl: Decimal
    detected_splits: list[str]
    position_should_be_flat: bool
    has_split_issue: bool

    model_config = ConfigDict(from_attributes=True)


class TradeFixResult(BaseModel):
    """Result of fixing a trade with split issues."""

    trade_id: int
    underlying: str
    status: str
    realized_pnl: float | None = None
    detected_splits: list[str] | None = None
    message: str

    model_config = ConfigDict(from_attributes=True)
