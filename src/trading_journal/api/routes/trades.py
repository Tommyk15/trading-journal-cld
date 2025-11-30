"""API routes for trades."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.core.database import get_db
from trading_journal.models.trade import Trade
from trading_journal.schemas.trade import (
    TradeList,
    TradeProcessRequest,
    TradeProcessResponse,
    TradeResponse,
    TradeUpdate,
)
from trading_journal.services.trade_grouping_service import TradeGroupingService

router = APIRouter(prefix="/trades", tags=["trades"])


@router.post("/process", response_model=TradeProcessResponse)
async def process_trades(
    request: TradeProcessRequest,
    session: AsyncSession = Depends(get_db),
):
    """Process executions into trades with strategy classification.

    Args:
        request: Processing request parameters
        session: Database session

    Returns:
        Processing statistics
    """
    service = TradeGroupingService(session)

    try:
        stats = await service.process_executions_to_trades(
            underlying=request.underlying,
            start_date=request.start_date,
            end_date=request.end_date,
        )

        message = (
            f"Processed {stats['executions_processed']} executions "
            f"into {stats['trades_created']} trades"
        )

        return TradeProcessResponse(
            **stats,
            message=message,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {e}")


@router.get("", response_model=TradeList)
async def list_trades(
    underlying: Optional[str] = Query(None, description="Filter by underlying symbol"),
    status: Optional[str] = Query(None, description="Filter by status (OPEN, CLOSED)"),
    strategy_type: Optional[str] = Query(None, description="Filter by strategy type"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Results offset"),
    session: AsyncSession = Depends(get_db),
):
    """List trades with optional filters.

    Args:
        underlying: Filter by underlying
        status: Filter by status
        strategy_type: Filter by strategy type
        limit: Max results
        offset: Results offset
        session: Database session

    Returns:
        List of trades
    """
    stmt = select(Trade).order_by(Trade.opened_at.desc())

    # Apply filters
    if underlying:
        stmt = stmt.where(Trade.underlying == underlying)
    if status:
        stmt = stmt.where(Trade.status == status)
    if strategy_type:
        stmt = stmt.where(Trade.strategy_type == strategy_type)

    # Get total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0

    # Apply pagination
    stmt = stmt.limit(limit).offset(offset)

    result = await session.execute(stmt)
    trades = list(result.scalars().all())

    return TradeList(
        trades=[TradeResponse.model_validate(t) for t in trades],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{trade_id}", response_model=TradeResponse)
async def get_trade(
    trade_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Get trade by ID.

    Args:
        trade_id: Trade database ID
        session: Database session

    Returns:
        Trade details

    Raises:
        HTTPException: If trade not found
    """
    stmt = select(Trade).where(Trade.id == trade_id)
    result = await session.execute(stmt)
    trade = result.scalar_one_or_none()

    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    return TradeResponse.model_validate(trade)


@router.patch("/{trade_id}", response_model=TradeResponse)
async def update_trade(
    trade_id: int,
    update_data: TradeUpdate,
    session: AsyncSession = Depends(get_db),
):
    """Update trade details (notes, tags, status).

    Args:
        trade_id: Trade database ID
        update_data: Update data
        session: Database session

    Returns:
        Updated trade

    Raises:
        HTTPException: If trade not found
    """
    stmt = select(Trade).where(Trade.id == trade_id)
    result = await session.execute(stmt)
    trade = result.scalar_one_or_none()

    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    # Update fields
    if update_data.notes is not None:
        trade.notes = update_data.notes
    if update_data.tags is not None:
        trade.tags = update_data.tags
    if update_data.status is not None:
        trade.status = update_data.status

    await session.commit()
    await session.refresh(trade)

    return TradeResponse.model_validate(trade)
