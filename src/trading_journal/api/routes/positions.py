"""API routes for positions."""


from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.core.database import get_db
from trading_journal.schemas.position import (
    PositionList,
    PositionResponse,
    PositionSyncRequest,
    PositionSyncResponse,
)
from trading_journal.services.position_service import PositionService

router = APIRouter(prefix="/positions", tags=["positions"])


@router.post("/sync", response_model=PositionSyncResponse)
async def sync_positions(
    request: PositionSyncRequest,
    session: AsyncSession = Depends(get_db),
):
    """Sync positions from IBKR.

    Args:
        request: Sync request parameters
        session: Database session

    Returns:
        Sync statistics
    """
    service = PositionService(session)

    try:
        stats = await service.sync_positions_from_ibkr(
            host=request.host,
            port=request.port,
        )

        message = f"Synced {stats['fetched']} positions from IBKR"
        if stats['created'] > 0:
            message += f" ({stats['created']} new, {stats['updated']} updated)"
        if stats['errors'] > 0:
            message += f" ({stats['errors']} errors)"

        return PositionSyncResponse(
            **stats,
            message=message,
        )

    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=f"IBKR connection failed: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {e}")


@router.get("", response_model=PositionList)
async def list_positions(
    underlying: str | None = Query(None, description="Filter by underlying symbol"),
    options_only: bool = Query(False, description="Only show option positions"),
    session: AsyncSession = Depends(get_db),
):
    """List positions.

    Args:
        underlying: Filter by underlying
        options_only: Only show options
        session: Database session

    Returns:
        List of positions
    """
    service = PositionService(session)

    if options_only:
        positions = await service.get_option_positions()
    else:
        positions = await service.get_open_positions(underlying=underlying)

    return PositionList(
        positions=[PositionResponse.model_validate(p) for p in positions],
        total=len(positions),
    )


@router.get("/{position_id}", response_model=PositionResponse)
async def get_position(
    position_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Get position by ID.

    Args:
        position_id: Position database ID
        session: Database session

    Returns:
        Position details

    Raises:
        HTTPException: If position not found
    """
    service = PositionService(session)
    position = await service.get_by_id(position_id)

    if not position:
        raise HTTPException(status_code=404, detail="Position not found")

    return PositionResponse.model_validate(position)
