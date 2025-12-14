"""API routes for Greeks data."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.core.database import get_db
from trading_journal.schemas.greeks import (
    GreeksFetchRequest,
    GreeksFetchResponse,
    GreeksHistoryResponse,
    GreeksResponse,
)
from trading_journal.services.greeks_service import GreeksService

router = APIRouter(prefix="/greeks", tags=["greeks"])


@router.post("/fetch", response_model=GreeksFetchResponse)
async def fetch_greeks(
    request: GreeksFetchRequest,
    session: AsyncSession = Depends(get_db),
):
    """Fetch Greeks for all open positions from IBKR.

    Args:
        request: Fetch request parameters
        session: Database session

    Returns:
        Fetch statistics
    """
    service = GreeksService(session)

    try:
        stats = await service.fetch_all_positions_greeks(
            host=request.host,
            port=request.port,
        )

        message = f"Fetched Greeks for {stats['greeks_fetched']} positions"
        if stats['errors'] > 0:
            message += f" ({stats['errors']} errors)"

        return GreeksFetchResponse(
            **stats,
            message=message,
        )

    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=f"IBKR connection failed: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fetch failed: {e}")


@router.get("/position/{position_id}/latest", response_model=GreeksResponse)
async def get_latest_greeks(
    position_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Get latest Greeks for a position.

    Args:
        position_id: Position database ID
        session: Database session

    Returns:
        Latest Greeks data

    Raises:
        HTTPException: If no Greeks data found
    """
    service = GreeksService(session)
    greeks = await service.get_latest_greeks(position_id)

    if not greeks:
        raise HTTPException(
            status_code=404,
            detail=f"No Greeks data found for position {position_id}"
        )

    return GreeksResponse.model_validate(greeks)


@router.get("/position/{position_id}/history", response_model=GreeksHistoryResponse)
async def get_greeks_history(
    position_id: int,
    start_date: datetime | None = Query(None, description="Start date"),
    end_date: datetime | None = Query(None, description="End date"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    session: AsyncSession = Depends(get_db),
):
    """Get historical Greeks for a position.

    Args:
        position_id: Position database ID
        start_date: Start date filter
        end_date: End date filter
        limit: Maximum results
        session: Database session

    Returns:
        Historical Greeks data
    """
    service = GreeksService(session)
    greeks_list = await service.get_greeks_history(
        position_id=position_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )

    return GreeksHistoryResponse(
        greeks=[GreeksResponse.model_validate(g) for g in greeks_list],
        total=len(greeks_list),
        position_id=position_id,
    )
