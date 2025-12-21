"""API routes for executions."""

import json
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.core.database import get_db
from trading_journal.schemas.execution import (
    ExecutionList,
    ExecutionResponse,
    ExecutionSyncRequest,
    ExecutionSyncResponse,
)
from trading_journal.services.execution_service import ExecutionService
from trading_journal.services.flex_query_parser import FlexQueryParser
from trading_journal.services.flex_query_service import FlexQueryService

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


@router.post("/upload", response_model=ExecutionSyncResponse)
async def upload_flex_query(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
):
    """Upload and import Flex Query CSV or XML file.

    Args:
        file: Flex Query report file (CSV or XML)
        session: Database session

    Returns:
        Import statistics

    Raises:
        HTTPException: If file parsing or import fails
    """
    try:
        # Read file content
        content = await file.read()
        content_str = content.decode('utf-8')

        # Parse executions from file
        parser = FlexQueryParser()
        parsed_executions = parser.parse_file(content_str)

        if not parsed_executions:
            raise HTTPException(
                status_code=400,
                detail="No executions found in file. Please check the file format and content."
            )

        # Import executions to database
        service = ExecutionService(session)

        stats = {
            "fetched": len(parsed_executions),
            "new": 0,
            "existing": 0,
            "errors": 0,
        }

        for exec_data in parsed_executions:
            try:
                # Check if execution already exists
                existing = await service.get_by_exec_id(exec_data['exec_id'])

                if existing:
                    stats['existing'] += 1
                else:
                    # Create new execution
                    await service.create_execution(exec_data)
                    stats['new'] += 1

            except Exception as e:
                print(f"Error importing execution {exec_data.get('exec_id')}: {e}")
                stats['errors'] += 1

        await session.commit()

        # Build response message
        message = f"Imported {stats['new']} new executions from Flex Query"
        if stats['existing'] > 0:
            message += f" ({stats['existing']} already existed)"
        if stats['errors'] > 0:
            message += f" ({stats['errors']} errors)"

        return ExecutionSyncResponse(
            **stats,
            message=message,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.post("/sync-flex-query")
async def sync_flex_query(
    session: AsyncSession = Depends(get_db),
):
    """Sync executions from IBKR Flex Query API with streaming progress.

    Fetches executions from IBKR using the configured Flex Query (ID: 1348073).
    This requires IBKR_FLEX_TOKEN to be set in environment variables.

    Returns:
        Server-Sent Events stream with progress updates
    """

    async def generate_progress():
        stats = {
            "fetched": 0,
            "new": 0,
            "existing": 0,
            "errors": 0,
        }

        try:
            # Send initial status
            yield f"data: {json.dumps({'status': 'connecting', 'message': 'Connecting to IBKR...'})}\n\n"

            # Initialize Flex Query service
            flex_service = FlexQueryService()

            yield f"data: {json.dumps({'status': 'fetching', 'message': 'Fetching executions from IBKR...'})}\n\n"

            # Fetch executions from IBKR
            parsed_executions = await flex_service.fetch_executions()

            if not parsed_executions:
                yield f"data: {json.dumps({'status': 'complete', 'message': 'No executions found in Flex Query.', 'stats': stats})}\n\n"
                return

            stats["fetched"] = len(parsed_executions)
            total = stats["fetched"]
            msg = f"Found {total} executions. Importing..."
            yield f"data: {json.dumps({'status': 'importing', 'message': msg, 'total': total, 'current': 0})}\n\n"

            # Import executions to database
            service = ExecutionService(session)

            for i, exec_data in enumerate(parsed_executions):
                try:
                    # Check if execution already exists
                    existing = await service.get_by_exec_id(exec_data["exec_id"])

                    if existing:
                        stats["existing"] += 1
                    else:
                        # Create new execution
                        await service.create_execution(exec_data)
                        stats["new"] += 1

                except Exception as e:
                    print(f"Error importing execution {exec_data.get('exec_id')}: {e}")
                    stats["errors"] += 1

                # Send progress update every 10 executions or on the last one
                if (i + 1) % 10 == 0 or i == len(parsed_executions) - 1:
                    progress_msg = f"Importing {i + 1}/{total}..."
                    progress_data = {
                        'status': 'importing',
                        'message': progress_msg,
                        'total': total,
                        'current': i + 1,
                        'new': stats['new'],
                        'existing': stats['existing']
                    }
                    yield f"data: {json.dumps(progress_data)}\n\n"

            await session.commit()

            # Build final message
            message = f"Synced {stats['new']} new executions from Flex Query"
            if stats["existing"] > 0:
                message += f" ({stats['existing']} already existed)"
            if stats["errors"] > 0:
                message += f" ({stats['errors']} errors)"

            yield f"data: {json.dumps({'status': 'complete', 'message': message, 'stats': stats})}\n\n"

        except ValueError as e:
            yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"
        except ConnectionError as e:
            yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'message': f'Flex Query sync failed: {str(e)}'})}\n\n"

    return StreamingResponse(
        generate_progress(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get("", response_model=ExecutionList)
async def list_executions(
    underlying: str | None = Query(None, description="Filter by underlying symbol"),
    start_date: datetime | None = Query(None, description="Start date filter"),
    end_date: datetime | None = Query(None, description="End date filter"),
    unassigned_only: bool = Query(False, description="Filter to unassigned executions only"),
    opens_only: bool = Query(False, description="Filter to only opening transactions (BTO/STO)"),
    orphans_only: bool = Query(False, description="Filter to orphan closes (unassigned closing transactions)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Results offset"),
    session: AsyncSession = Depends(get_db),
):
    """List executions with optional filters.

    Args:
        underlying: Filter by underlying
        start_date: Start date
        end_date: End date
        unassigned_only: Only show executions not assigned to a trade
        opens_only: Only show opening transactions (BTO/STO)
        orphans_only: Only show orphan closes (unassigned closing transactions)
        limit: Max results
        offset: Results offset
        session: Database session

    Returns:
        List of executions
    """
    service = ExecutionService(session)

    executions, total = await service.list_executions_with_filter(
        unassigned_only=unassigned_only,
        opens_only=opens_only,
        orphans_only=orphans_only,
        underlying=underlying,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )

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


# Scheduler monitoring endpoints

@router.get("/sync/status")
async def get_sync_status(request: Request):
    """Get execution sync scheduler status.

    Returns scheduler status including:
    - enabled: Whether scheduler is running
    - interval_minutes: Sync interval
    - next_realtime_sync: Next scheduled real-time sync
    - next_flex_sync: Next scheduled Flex Query sync
    - last_sync: Last sync timestamp
    - total_syncs: Total syncs performed
    - consecutive_errors: Number of consecutive errors
    - history: Recent sync history

    Raises:
        HTTPException: If scheduler is not running
    """
    if not hasattr(request.app.state, 'execution_scheduler'):
        raise HTTPException(
            status_code=503,
            detail="Execution sync scheduler not running. Set ENABLE_EXECUTION_SYNC=true to enable."
        )

    scheduler = request.app.state.execution_scheduler
    status = scheduler.get_status()

    return status


@router.post("/sync/trigger")
async def trigger_manual_sync(
    request: Request,
    sync_type: str = Query(
        default="realtime",
        description="Type of sync: 'realtime' or 'flex_query'"
    ),
):
    """Manually trigger an execution sync.

    Args:
        sync_type: Type of sync - 'realtime' (IBKR API) or 'flex_query' (Flex Query API)

    Returns:
        Sync statistics

    Raises:
        HTTPException: If scheduler is not running
    """
    if not hasattr(request.app.state, 'execution_scheduler'):
        raise HTTPException(
            status_code=503,
            detail="Execution sync scheduler not running. Set ENABLE_EXECUTION_SYNC=true to enable."
        )

    if sync_type not in ["realtime", "flex_query"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid sync_type. Use 'realtime' or 'flex_query'."
        )

    scheduler = request.app.state.execution_scheduler
    stats = await scheduler.trigger_sync(sync_type=sync_type)

    return {
        "message": f"{sync_type.replace('_', ' ').title()} sync triggered",
        "sync_type": stats.sync_type,
        "started_at": stats.started_at.isoformat() if stats.started_at else None,
        "completed_at": stats.completed_at.isoformat() if stats.completed_at else None,
        "executions_fetched": stats.executions_fetched,
        "executions_new": stats.executions_new,
        "executions_existing": stats.executions_existing,
        "trades_created": stats.trades_created,
        "greeks_fetched": stats.greeks_fetched,
        "error": stats.error_message,
    }
