"""API routes for trades."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.core.database import get_db
from trading_journal.models.trade import Trade
from trading_journal.models.execution import Execution
from trading_journal.schemas.trade import (
    ManualTradeCreateRequest,
    MergeTradesRequest,
    SuggestGroupingRequest,
    SuggestGroupingResponse,
    SuggestedGroup,
    TradeExecutionsUpdateRequest,
    TradeList,
    TradeProcessRequest,
    TradeProcessResponse,
    TradeResponse,
    TradeUpdate,
)
from trading_journal.services.trade_grouping_service import TradeGroupingService
from trading_journal.services.trade_service import TradeService

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
    # Build query - show all trades, no deduplication
    stmt = (
        select(Trade)
        .where(Trade.num_executions > 0)  # Only execution-based trades
        .order_by(Trade.opened_at.desc())
    )

    # Apply filters
    if underlying:
        stmt = stmt.where(Trade.underlying == underlying)
    if status:
        stmt = stmt.where(Trade.status == status)
    if strategy_type:
        stmt = stmt.where(Trade.strategy_type == strategy_type)

    # Get total count before pagination
    count_stmt = select(func.count()).select_from(
        select(Trade.id)
        .where(Trade.num_executions > 0)
        .subquery()
    )

    # Apply same filters to count
    if underlying or status or strategy_type:
        count_stmt = select(func.count(Trade.id)).where(Trade.num_executions > 0)
        if underlying:
            count_stmt = count_stmt.where(Trade.underlying == underlying)
        if status:
            count_stmt = count_stmt.where(Trade.status == status)
        if strategy_type:
            count_stmt = count_stmt.where(Trade.strategy_type == strategy_type)

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


@router.get("/{trade_id}/executions")
async def get_trade_executions(
    trade_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Get executions for a specific trade.

    Args:
        trade_id: Trade database ID
        session: Database session

    Returns:
        List of executions that make up this trade

    Raises:
        HTTPException: If trade not found
    """
    # Get the trade
    stmt = select(Trade).where(Trade.id == trade_id)
    result = await session.execute(stmt)
    trade = result.scalar_one_or_none()

    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    # Get executions for this trade using the trade_id foreign key
    exec_stmt = (
        select(Execution)
        .where(Execution.trade_id == trade_id)
        .order_by(Execution.execution_time)
    )

    result = await session.execute(exec_stmt)
    executions = result.scalars().all()

    return {"executions": executions}


@router.post("/create-manual", response_model=TradeResponse)
async def create_manual_trade(
    request: ManualTradeCreateRequest,
    session: AsyncSession = Depends(get_db),
):
    """Create a trade from manually selected executions.

    Args:
        request: Manual trade creation request with execution IDs
        session: Database session

    Returns:
        Created trade

    Raises:
        HTTPException: If creation fails
    """
    service = TradeService(session)

    # Use custom strategy name if provided, otherwise use strategy_type
    strategy = (
        request.custom_strategy
        if request.strategy_type == "Custom" and request.custom_strategy
        else request.strategy_type
    )

    try:
        trade = await service.create_manual_trade(
            execution_ids=request.execution_ids,
            strategy_type=strategy,
            notes=request.notes,
            tags=request.tags,
            auto_match_closes=request.auto_match_closes,
        )
        return TradeResponse.model_validate(trade)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{trade_id}/executions", response_model=TradeResponse)
async def update_trade_executions(
    trade_id: int,
    request: TradeExecutionsUpdateRequest,
    session: AsyncSession = Depends(get_db),
):
    """Add or remove executions from an existing trade.

    Args:
        trade_id: Trade database ID
        request: Execution IDs to add or remove
        session: Database session

    Returns:
        Updated trade

    Raises:
        HTTPException: If trade not found or update fails
    """
    service = TradeService(session)

    try:
        trade = await service.update_trade_executions(
            trade_id=trade_id,
            add_ids=request.add_execution_ids,
            remove_ids=request.remove_execution_ids,
        )
        if trade is None:
            raise HTTPException(
                status_code=404,
                detail="Trade deleted (no executions remaining)",
            )
        return TradeResponse.model_validate(trade)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{trade_id}")
async def delete_trade(
    trade_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Ungroup and delete a trade.

    This removes all execution assignments and deletes the trade record.

    Args:
        trade_id: Trade database ID
        session: Database session

    Returns:
        Success message

    Raises:
        HTTPException: If trade not found
    """
    service = TradeService(session)

    success = await service.ungroup_trade(trade_id)
    if not success:
        raise HTTPException(status_code=404, detail="Trade not found")

    return {"message": "Trade ungrouped and deleted"}


@router.post("/merge", response_model=TradeResponse)
async def merge_trades(
    request: MergeTradesRequest,
    session: AsyncSession = Depends(get_db),
):
    """Merge multiple trades into a single trade.

    All executions from the source trades are combined into the first trade (by ID).
    The other trades are deleted. Preserves notes and tags from the first trade.

    Args:
        request: List of trade IDs to merge (minimum 2)
        session: Database session

    Returns:
        The merged trade

    Raises:
        HTTPException: If trades not found, different underlyings, or merge fails
    """
    service = TradeService(session)

    try:
        merged_trade = await service.merge_trades(request.trade_ids)
        return TradeResponse.model_validate(merged_trade)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/suggest-grouping", response_model=SuggestGroupingResponse)
async def suggest_grouping(
    request: SuggestGroupingRequest = SuggestGroupingRequest(),
    session: AsyncSession = Depends(get_db),
):
    """Run auto-grouping algorithm and return suggestions without saving.

    This uses the existing trade grouping algorithm to suggest how
    unassigned executions could be grouped into trades.

    Args:
        request: Optional request with specific execution IDs to group
        session: Database session

    Returns:
        Suggested trade groupings
    """
    service = TradeService(session)

    groups = await service.suggest_grouping(request.execution_ids)

    return SuggestGroupingResponse(
        groups=[SuggestedGroup(**g) for g in groups],
        message=f"Suggested {len(groups)} trade groups",
    )


@router.post("/reprocess-all", response_model=TradeProcessResponse)
async def reprocess_all_trades(
    session: AsyncSession = Depends(get_db),
):
    """Reprocess all executions using the improved state machine algorithm.

    This endpoint:
    1. Deletes ALL existing trades
    2. Clears trade assignments from all executions
    3. Reprocesses all executions using the new position state machine
    4. Detects and links roll chains

    WARNING: This is a destructive operation that deletes all existing trades.

    Args:
        session: Database session

    Returns:
        Processing statistics including trades created and rolls detected
    """
    service = TradeGroupingService(session)

    try:
        stats = await service.reprocess_all_executions()

        message = (
            f"Reprocessed {stats['executions_processed']} executions "
            f"into {stats['trades_created']} trades. "
            f"Detected {stats['rolls_detected']} rolls."
        )

        return TradeProcessResponse(
            executions_processed=stats["executions_processed"],
            trades_created=stats["trades_created"],
            trades_updated=0,
            message=message,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reprocessing failed: {e}")
