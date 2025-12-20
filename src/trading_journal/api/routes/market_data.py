"""API routes for market data (OHLC candles)."""

from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from trading_journal.services.polygon_service import PolygonService, PolygonServiceError

router = APIRouter(prefix="/market-data", tags=["market-data"])


class CandleData(BaseModel):
    """Single OHLC candle."""

    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int | None = None


class CandlesResponse(BaseModel):
    """Response containing candle data."""

    underlying: str
    timeframe: str
    candles: list[CandleData]
    count: int


@router.get("/{underlying}/candles", response_model=CandlesResponse)
async def get_candles(
    underlying: str,
    days: int = Query(90, ge=1, le=365, description="Number of days of data"),
    timespan: str = Query("day", description="Candle timespan: minute, hour, day, week, month"),
    multiplier: int = Query(1, ge=1, le=60, description="Timespan multiplier (e.g., 5 for 5-minute candles)"),
):
    """Get OHLC candle data for an underlying.

    Args:
        underlying: Stock/ETF symbol
        days: Number of days of historical data (1-365)
        timespan: Candle timespan (minute, hour, day, week, month)
        multiplier: Timespan multiplier (e.g., 5 for 5-minute candles)

    Returns:
        OHLC candle data

    Raises:
        HTTPException: If data fetch fails
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    try:
        async with PolygonService() as polygon:
            candles = await polygon.get_stock_candles(
                symbol=underlying.upper(),
                start_date=start_date,
                end_date=end_date,
                timespan=timespan,
                multiplier=multiplier,
            )

            if not candles:
                raise HTTPException(
                    status_code=404,
                    detail=f"No candle data found for {underlying}",
                )

            return CandlesResponse(
                underlying=underlying.upper(),
                timeframe=f"{days}D",
                candles=[
                    CandleData(
                        timestamp=c["timestamp"],
                        open=c["open"],
                        high=c["high"],
                        low=c["low"],
                        close=c["close"],
                        volume=c.get("volume"),
                    )
                    for c in candles
                ],
                count=len(candles),
            )

    except HTTPException:
        raise
    except PolygonServiceError as e:
        raise HTTPException(status_code=503, detail=f"Polygon API error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching candles: {e}")
