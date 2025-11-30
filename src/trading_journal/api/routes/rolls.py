"""API routes for roll detection and tracking."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.core.database import get_db
from trading_journal.schemas.roll import (
    RollChainResponse,
    RollChainTrade,
    RollDetectionRequest,
    RollDetectionResponse,
    RollStatistics,
)
from trading_journal.services.roll_detection_service import RollDetectionService

router = APIRouter(prefix="/rolls", tags=["rolls"])


@router.post("/detect", response_model=RollDetectionResponse)
async def detect_rolls(
    request: RollDetectionRequest,
    session: AsyncSession = Depends(get_db),
):
    """Detect and link rolled positions.

    Analyzes closed trades to identify roll relationships where a trader
    closed one position and opened a similar position shortly after.

    Args:
        request: Detection request parameters
        session: Database session

    Returns:
        Detection statistics
    """
    service = RollDetectionService(session)

    try:
        stats = await service.detect_and_link_rolls(
            underlying=request.underlying,
            start_date=request.start_date,
            end_date=request.end_date,
        )

        message = f"Analyzed {stats['trades_analyzed']} trades"
        if stats['rolls_detected'] > 0:
            message += f", detected {stats['rolls_detected']} rolls in {stats['roll_chains_found']} chains"
        else:
            message += ", no rolls detected"

        return RollDetectionResponse(
            **stats,
            message=message,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Roll detection failed: {e}")


@router.get("/chain/{trade_id}", response_model=RollChainResponse)
async def get_roll_chain(
    trade_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Get the complete roll chain for a trade.

    Returns all trades connected by roll relationships, starting from
    the earliest trade and continuing through all subsequent rolls.

    Args:
        trade_id: Any trade ID in the chain
        session: Database session

    Returns:
        Complete roll chain

    Raises:
        HTTPException: If trade not found or not part of a roll
    """
    service = RollDetectionService(session)
    chain = await service.get_roll_chain(trade_id)

    if not chain:
        raise HTTPException(
            status_code=404,
            detail=f"Trade {trade_id} not found or not part of a roll chain"
        )

    if len(chain) == 1 and not chain[0].is_roll:
        raise HTTPException(
            status_code=404,
            detail=f"Trade {trade_id} is not part of a roll chain"
        )

    total_pnl = sum(t.total_pnl for t in chain)

    return RollChainResponse(
        chain_length=len(chain),
        total_pnl=total_pnl,
        trades=[RollChainTrade.model_validate(t) for t in chain],
    )


@router.get("/statistics", response_model=RollStatistics)
async def get_roll_statistics(
    underlying: Optional[str] = Query(None, description="Filter by underlying symbol"),
    session: AsyncSession = Depends(get_db),
):
    """Get statistics about rolled positions.

    Provides metrics on how frequently positions are rolled, average
    chain lengths, and P&L from rolled positions.

    Args:
        underlying: Optional filter by underlying
        session: Database session

    Returns:
        Roll statistics
    """
    service = RollDetectionService(session)
    stats = await service.get_roll_statistics(underlying=underlying)

    return RollStatistics(**stats)
