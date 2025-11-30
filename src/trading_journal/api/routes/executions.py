"""API routes for executions."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.core.database import get_db
from trading_journal.schemas.execution import (
    ExecutionList,
    ExecutionResponse,
    ExecutionSyncRequest,
    ExecutionSyncResponse,
)
from trading_journal.services.execution_service import ExecutionService

router = APIRouter(prefix="/executions", tags=["executions"])


@router.post("/sync", response_model=ExecutionSyncResponse)
async def sync_executions(
    request: ExecutionSyncRequest,
    session: AsyncSession = Depends(get_db),
):
    """Sync executions from IBKR.

    Args:
        request: Sync request parameters
        session: Database session

    Returns:
        Sync statistics
    """
    service = ExecutionService(session)

    try:
        stats = await service.sync_from_ibkr(
            days_back=request.days_back,
            host=request.host,
            port=request.port,
        )

        message = f"Synced {stats['new']} new executions from IBKR"
        if stats['existing'] > 0:
            message += f" ({stats['existing']} already existed)"
        if stats['errors'] > 0:
            message += f" ({stats['errors']} errors)"

        return ExecutionSyncResponse(
            **stats,
            message=message,
        )

    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=f"IBKR connection failed: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {e}")


@router.get("", response_model=ExecutionList)
async def list_executions(
    underlying: Optional[str] = Query(None, description="Filter by underlying symbol"),
    start_date: Optional[datetime] = Query(None, description="Start date filter"),
    end_date: Optional[datetime] = Query(None, description="End date filter"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Results offset"),
    session: AsyncSession = Depends(get_db),
):
    """List executions with optional filters.

    Args:
        underlying: Filter by underlying
        start_date: Start date
        end_date: End date
        limit: Max results
        offset: Results offset
        session: Database session

    Returns:
        List of executions
    """
    service = ExecutionService(session)

    executions = await service.list_executions(
        underlying=underlying,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )

    # Get total count (simplified - in production would use COUNT query)
    total = len(executions)

    return ExecutionList(
        executions=[ExecutionResponse.model_validate(e) for e in executions],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{execution_id}", response_model=ExecutionResponse)
async def get_execution(
    execution_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Get execution by ID.

    Args:
        execution_id: Execution database ID
        session: Database session

    Returns:
        Execution details

    Raises:
        HTTPException: If execution not found
    """
    service = ExecutionService(session)
    execution = await service.get_by_id(execution_id)

    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    return ExecutionResponse.model_validate(execution)
