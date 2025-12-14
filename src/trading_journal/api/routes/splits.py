"""API routes for stock split detection and handling."""

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.core.database import get_db
from trading_journal.schemas.splits import (
    PositionAnalysis,
    SplitReport,
    TradeFixResult,
)
from trading_journal.services.split_detection_service import SplitDetectionService

router = APIRouter(prefix="/splits", tags=["splits"])


@router.get("/scan", response_model=SplitReport)
async def scan_for_splits(
    session: AsyncSession = Depends(get_db),
):
    """Scan all stock positions for potential split-related issues.

    Analyzes price patterns and quantity mismatches to detect
    stock splits that may have affected position tracking.

    Returns:
        Report of detected split issues
    """
    service = SplitDetectionService(session)
    report = await service.check_and_report_splits()

    return SplitReport(**report)


@router.get("/analyze/{underlying}", response_model=PositionAnalysis)
async def analyze_position(
    underlying: str = Path(..., description="Stock symbol to analyze"),
    session: AsyncSession = Depends(get_db),
):
    """Analyze a specific stock position for split-related issues.

    Provides detailed breakdown of share counts before and after
    adjusting for detected splits.

    Args:
        underlying: Stock symbol to analyze

    Returns:
        Detailed position analysis
    """
    service = SplitDetectionService(session)
    analysis = await service.analyze_position_for_splits(underlying)

    # Convert StockSplit objects to strings for the response
    analysis["detected_splits"] = [str(s) for s in analysis["detected_splits"]]

    return PositionAnalysis(**analysis)


@router.post("/fix-trade/{trade_id}", response_model=TradeFixResult)
async def fix_trade_with_split(
    trade_id: int = Path(..., description="Trade ID to fix"),
    session: AsyncSession = Depends(get_db),
):
    """Fix a trade that has split-related issues.

    Updates the trade status and P&L based on actual dollar amounts,
    accounting for stock splits that affected share counts.

    Args:
        trade_id: Trade ID to fix

    Returns:
        Result of the fix operation
    """
    service = SplitDetectionService(session)
    result = await service.fix_trade_with_split(trade_id)

    return TradeFixResult(**result)
