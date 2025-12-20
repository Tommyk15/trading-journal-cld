"""Stock splits API routes."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.core.database import get_db
from trading_journal.models.stock_split import StockSplit
from trading_journal.schemas.stock_split import (
    StockSplitCreate,
    StockSplitList,
    StockSplitResponse,
)
from trading_journal.services.split_normalization_service import SplitNormalizationService

router = APIRouter(prefix="/stock-splits", tags=["stock-splits"])


@router.get("", response_model=StockSplitList)
async def list_stock_splits(
    symbol: str | None = None,
    session: AsyncSession = Depends(get_db),
):
    """List all stock splits, optionally filtered by symbol.

    Args:
        symbol: Optional symbol to filter by
        session: Database session

    Returns:
        List of stock splits
    """
    stmt = select(StockSplit).order_by(StockSplit.split_date.desc())

    if symbol:
        stmt = stmt.where(StockSplit.symbol == symbol.upper())

    result = await session.execute(stmt)
    splits = list(result.scalars().all())

    return StockSplitList(
        splits=[StockSplitResponse.model_validate(s) for s in splits],
        total=len(splits),
    )


@router.post("", response_model=StockSplitResponse, status_code=201)
async def create_stock_split(
    split_data: StockSplitCreate,
    session: AsyncSession = Depends(get_db),
):
    """Create a new stock split record.

    Args:
        split_data: Stock split details
        session: Database session

    Returns:
        Created stock split record
    """
    # Check for duplicate
    stmt = select(StockSplit).where(
        StockSplit.symbol == split_data.symbol.upper(),
        StockSplit.split_date == split_data.split_date,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Stock split already exists for {split_data.symbol} on {split_data.split_date.date()}",
        )

    split = StockSplit(
        symbol=split_data.symbol.upper(),
        split_date=split_data.split_date,
        ratio_from=split_data.ratio_from,
        ratio_to=split_data.ratio_to,
        description=split_data.description,
    )

    session.add(split)
    await session.commit()
    await session.refresh(split)

    return StockSplitResponse.model_validate(split)


# NOTE: Specific path routes must be defined BEFORE parameterized routes like /{split_id}

@router.get("/symbol/{symbol}", response_model=StockSplitList)
async def get_splits_for_symbol(
    symbol: str,
    session: AsyncSession = Depends(get_db),
):
    """Get all stock splits for a specific symbol.

    Args:
        symbol: Stock symbol
        session: Database session

    Returns:
        List of stock splits for the symbol
    """
    stmt = (
        select(StockSplit)
        .where(StockSplit.symbol == symbol.upper())
        .order_by(StockSplit.split_date.desc())
    )

    result = await session.execute(stmt)
    splits = list(result.scalars().all())

    return StockSplitList(
        splits=[StockSplitResponse.model_validate(s) for s in splits],
        total=len(splits),
    )


@router.get("/by-symbol", response_model=dict)
async def get_all_splits_by_symbol(
    session: AsyncSession = Depends(get_db),
):
    """Get all stock splits grouped by symbol.

    Returns a dictionary where keys are symbols and values are lists of splits.
    This is useful for the frontend to efficiently look up splits.

    Returns:
        Dictionary of symbol -> list of splits
    """
    stmt = select(StockSplit).order_by(StockSplit.symbol, StockSplit.split_date.desc())
    result = await session.execute(stmt)
    splits = list(result.scalars().all())

    splits_by_symbol: dict[str, list[dict]] = {}
    for split in splits:
        if split.symbol not in splits_by_symbol:
            splits_by_symbol[split.symbol] = []
        splits_by_symbol[split.symbol].append({
            "id": split.id,
            "symbol": split.symbol,
            "split_date": split.split_date.isoformat(),
            "ratio_from": split.ratio_from,
            "ratio_to": split.ratio_to,
            "description": split.description,
            "adjustment_factor": float(split.adjustment_factor),
            "price_factor": float(split.price_factor),
            "is_reverse_split": split.is_reverse_split,
        })

    return splits_by_symbol


@router.get("/normalize/check")
async def check_unnormalized_splits(
    session: AsyncSession = Depends(get_db),
):
    """Check for executions that may need split normalization.

    This endpoint scans for pre-split executions that haven't been normalized.
    It checks both options (by strike price) and stocks (by date).

    Returns:
        Report of potentially unnormalized executions
    """
    service = SplitNormalizationService(session)
    report = await service.check_for_unnormalized_splits()

    return {
        **report,
        "message": f"Found {report['total_suspicious']} executions that may need normalization",
    }


@router.get("/{split_id}", response_model=StockSplitResponse)
async def get_stock_split(
    split_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Get a specific stock split by ID.

    Args:
        split_id: Stock split database ID
        session: Database session

    Returns:
        Stock split record
    """
    stmt = select(StockSplit).where(StockSplit.id == split_id)
    result = await session.execute(stmt)
    split = result.scalar_one_or_none()

    if not split:
        raise HTTPException(status_code=404, detail="Stock split not found")

    return StockSplitResponse.model_validate(split)


@router.delete("/{split_id}", status_code=204)
async def delete_stock_split(
    split_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Delete a stock split record.

    Args:
        split_id: Stock split database ID
        session: Database session
    """
    stmt = select(StockSplit).where(StockSplit.id == split_id)
    result = await session.execute(stmt)
    split = result.scalar_one_or_none()

    if not split:
        raise HTTPException(status_code=404, detail="Stock split not found")

    await session.delete(split)
    await session.commit()


@router.post("/normalize/all")
async def normalize_all_splits(
    session: AsyncSession = Depends(get_db),
):
    """Normalize all executions affected by stock splits.

    This endpoint processes all known stock splits and normalizes:
    - Option strikes, quantities, and prices for forward splits
    - Stock quantities and prices for both forward and reverse splits

    For forward splits (e.g., 10:1): quantity increases, price decreases
    For reverse splits (e.g., 5:1 reverse): quantity decreases, price increases

    Note: Net amounts for stocks are preserved (dollar value doesn't change).

    Returns:
        Statistics about the normalization process
    """
    service = SplitNormalizationService(session)

    try:
        stats = await service.normalize_all_splits()
        await session.commit()

        return {
            **stats,
            "message": f"Normalized {stats['executions_normalized']} executions "
                      f"({stats['options_normalized']} options, {stats['stocks_normalized']} stocks)",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Normalization failed: {e}")


@router.post("/normalize/{symbol}")
async def normalize_symbol(
    symbol: str,
    session: AsyncSession = Depends(get_db),
):
    """Normalize all executions for a specific symbol.

    This endpoint normalizes all pre-split executions for the given symbol,
    handling both options and stocks.

    Args:
        symbol: Stock symbol to normalize

    Returns:
        Statistics about the normalization
    """
    service = SplitNormalizationService(session)

    try:
        stats = await service.normalize_symbol(symbol.upper())

        if stats["total"] == 0:
            return {
                **stats,
                "message": f"No executions needed normalization for {symbol.upper()}",
            }

        return {
            **stats,
            "message": f"Normalized {stats['total']} executions for {symbol.upper()} "
                      f"({stats['options']} options, {stats['stocks']} stocks)",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Normalization failed: {e}")
