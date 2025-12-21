"""API routes for market data (OHLC candles, quotes, Greeks, positions)."""

from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from trading_journal.core.database import get_db
from trading_journal.models.execution import Execution
from trading_journal.models.trade import Trade
from trading_journal.schemas.market_data import (
    AccountPnLResponse,
    OptionDataResponse,
    OptionGreeksResponse,
    OptionQuoteResponse,
    PortfolioPositionResponse,
    PortfolioResponse,
    PositionMarketDataResponse,
    PositionsMarketDataResponse,
    StockQuoteResponse,
)
from trading_journal.services.market_data_service import MarketDataService
from trading_journal.services.polygon_service import PolygonService, PolygonServiceError

router = APIRouter(prefix="/market-data", tags=["market-data"])

# Global market data service instance
_market_data_service: MarketDataService | None = None


def get_market_data_service() -> MarketDataService:
    """Get or create market data service singleton."""
    global _market_data_service
    if _market_data_service is None:
        _market_data_service = MarketDataService()
    return _market_data_service


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


# =============================================================================
# Stock Quotes
# =============================================================================


@router.get("/quote/{symbol}", response_model=StockQuoteResponse)
async def get_stock_quote(
    symbol: str,
    service: MarketDataService = Depends(get_market_data_service),
):
    """Get stock quote from best available source.

    Priority: IBKR (real-time) -> Polygon (EOD) -> yfinance (delayed)

    Args:
        symbol: Stock ticker symbol

    Returns:
        Stock quote with price data
    """
    try:
        quote = await service.get_stock_quote(symbol.upper())
        return StockQuoteResponse(
            symbol=quote.symbol,
            price=float(quote.price) if quote.price else None,
            bid=float(quote.bid) if quote.bid else None,
            ask=float(quote.ask) if quote.ask else None,
            last=float(quote.last) if quote.last else None,
            close=float(quote.close) if quote.close else None,
            volume=quote.volume,
            source=quote.source.value,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching quote: {e}")


# =============================================================================
# Option Data
# =============================================================================


@router.get("/option/{underlying}/{expiration}/{strike}/{option_type}", response_model=OptionDataResponse)
async def get_option_data(
    underlying: str,
    expiration: str,
    strike: float,
    option_type: str,
    service: MarketDataService = Depends(get_market_data_service),
):
    """Get option quote and Greeks from best available source.

    Priority: IBKR (real-time) -> Polygon (snapshot) -> yfinance (delayed)

    Args:
        underlying: Underlying symbol
        expiration: Expiration date (YYYYMMDD or YYYY-MM-DD)
        strike: Strike price
        option_type: 'C' for call, 'P' for put

    Returns:
        Option quote and Greeks
    """
    try:
        # Parse expiration date
        exp_str = expiration.replace("-", "")
        exp_date = datetime.strptime(exp_str, "%Y%m%d")

        quote, greeks = await service.get_option_data(
            underlying=underlying.upper(),
            expiration=exp_date,
            strike=Decimal(str(strike)),
            option_type=option_type.upper(),
        )

        return OptionDataResponse(
            quote=OptionQuoteResponse(
                symbol=quote.symbol,
                underlying=quote.underlying,
                strike=float(quote.strike),
                expiration=quote.expiration.strftime("%Y-%m-%d"),
                option_type=quote.option_type,
                bid=float(quote.bid) if quote.bid else None,
                ask=float(quote.ask) if quote.ask else None,
                last=float(quote.last) if quote.last else None,
                mid=float(quote.mid) if quote.mid else None,
                volume=quote.volume,
                open_interest=quote.open_interest,
                source=quote.source.value,
            ),
            greeks=OptionGreeksResponse(
                delta=float(greeks.delta) if greeks.delta else None,
                gamma=float(greeks.gamma) if greeks.gamma else None,
                theta=float(greeks.theta) if greeks.theta else None,
                vega=float(greeks.vega) if greeks.vega else None,
                rho=float(greeks.rho) if greeks.rho else None,
                iv=float(greeks.iv) if greeks.iv else None,
                source=greeks.source.value,
            ),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid parameters: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching option data: {e}")


# =============================================================================
# Portfolio (IBKR)
# =============================================================================


@router.get("/portfolio", response_model=PortfolioResponse)
async def get_portfolio(
    service: MarketDataService = Depends(get_market_data_service),
):
    """Get portfolio positions with market data from IBKR.

    Returns real-time positions with market values and P&L.
    Requires IBKR TWS/Gateway to be running.

    Returns:
        Portfolio positions with market data
    """
    try:
        positions = await service.get_portfolio_positions()

        total_market_value = sum(float(p["market_value"]) for p in positions)
        total_unrealized = sum(float(p["unrealized_pnl"]) for p in positions)

        return PortfolioResponse(
            positions=[
                PortfolioPositionResponse(
                    symbol=p["symbol"],
                    underlying=p["underlying"],
                    security_type=p["security_type"],
                    strike=float(p["strike"]) if p["strike"] else None,
                    expiration=p["expiration"],
                    option_type=p["option_type"],
                    position=p["position"],
                    market_price=float(p["market_price"]) if p["market_price"] else None,
                    market_value=float(p["market_value"]),
                    avg_cost=float(p["avg_cost"]),
                    unrealized_pnl=float(p["unrealized_pnl"]),
                    realized_pnl=float(p["realized_pnl"]),
                )
                for p in positions
            ],
            total_market_value=total_market_value,
            total_unrealized_pnl=total_unrealized,
            connected=len(positions) > 0,
            timestamp=datetime.now(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching portfolio: {e}")


@router.get("/account-pnl", response_model=AccountPnLResponse)
async def get_account_pnl(
    service: MarketDataService = Depends(get_market_data_service),
):
    """Get account-level P&L from IBKR.

    Returns daily, unrealized, and realized P&L.
    Requires IBKR TWS/Gateway to be running.

    Returns:
        Account P&L data
    """
    try:
        pnl = await service.get_account_pnl()

        return AccountPnLResponse(
            account=pnl.get("account"),
            daily_pnl=float(pnl["daily_pnl"]) if pnl.get("daily_pnl") else None,
            unrealized_pnl=float(pnl["unrealized_pnl"]) if pnl.get("unrealized_pnl") else None,
            realized_pnl=float(pnl["realized_pnl"]) if pnl.get("realized_pnl") else None,
            connected=bool(pnl),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching account P&L: {e}")


# =============================================================================
# Positions Market Data (for trades)
# =============================================================================


@router.get("/positions", response_model=PositionsMarketDataResponse)
async def get_positions_market_data(
    force_refresh: bool = Query(False, description="Force refresh from live sources"),
    session: AsyncSession = Depends(get_db),
    service: MarketDataService = Depends(get_market_data_service),
):
    """Get market data for all open positions/trades.

    Fetches current prices, Greeks, and calculates unrealized P&L
    for all OPEN trades. Uses IBKR portfolio data when available (fast),
    otherwise falls back to per-option fetching.

    Args:
        force_refresh: If True, bypass cache and fetch fresh data
        session: Database session

    Returns:
        Market data for all open positions
    """
    import logging

    if force_refresh:
        service.clear_cache()

    # Get all OPEN trades
    stmt = (
        select(Trade)
        .where(Trade.status == "OPEN")
        .where(Trade.num_executions > 0)
        .order_by(Trade.opened_at.desc())
    )
    result = await session.execute(stmt)
    trades = list(result.scalars().all())

    # Try to get IBKR portfolio data first (fast - one call returns all positions)
    ibkr_portfolio = await service.get_portfolio_positions()
    ibkr_connected = len(ibkr_portfolio) > 0

    # Build lookup for IBKR positions by symbol
    # Key: "UNDERLYING_EXPIRATION_STRIKE_OPTIONTYPE" or "UNDERLYING" for stocks
    ibkr_by_key: dict[str, dict] = {}
    for pos in ibkr_portfolio:
        underlying = pos.get("underlying", "")
        sec_type = pos.get("security_type", "")
        if sec_type == "OPT":
            exp = pos.get("expiration", "")
            strike = pos.get("strike")
            opt_type = pos.get("option_type", "")
            if exp and strike and opt_type:
                key = f"{underlying}_{exp}_{strike}_{opt_type}"
                ibkr_by_key[key] = pos
        elif sec_type == "STK":
            ibkr_by_key[f"{underlying}_STK"] = pos

    positions_data = []
    total_market_value = Decimal("0")
    total_cost_basis = Decimal("0")
    total_delta = Decimal("0")
    total_theta = Decimal("0")
    primary_source = "IBKR" if ibkr_connected else "UNAVAILABLE"
    all_fresh = True
    any_data = False

    # Fetch stock quotes for all unique underlyings (for underlying_price column)
    import asyncio
    unique_underlyings = set(t.underlying for t in trades)
    underlying_prices: dict[str, float | None] = {}

    if ibkr_connected:
        # First, get prices from existing stock positions
        underlyings_to_fetch = []
        for underlying in unique_underlyings:
            stock_key = f"{underlying}_STK"
            if stock_key in ibkr_by_key:
                underlying_prices[underlying] = ibkr_by_key[stock_key].get("market_price")
            else:
                underlyings_to_fetch.append(underlying)

        # Fetch remaining quotes concurrently from IBKR
        async def fetch_quote(symbol: str) -> tuple[str, float | None]:
            try:
                quote = await asyncio.wait_for(
                    service.get_stock_quote(symbol),
                    timeout=5.0  # 5 second timeout per quote
                )
                if quote and quote.price:
                    return (symbol, float(quote.price))
            except Exception:
                pass
            return (symbol, None)

        if underlyings_to_fetch:
            results = await asyncio.gather(
                *[fetch_quote(sym) for sym in underlyings_to_fetch],
                return_exceptions=True
            )
            for result in results:
                if isinstance(result, tuple):
                    symbol, price = result
                    underlying_prices[symbol] = price

    # Pre-fetch all executions with proper date casting to avoid timezone issues
    from sqlalchemy import func, cast, Date
    all_trade_ids = [t.id for t in trades]
    exec_stmt = (
        select(
            Execution,
            cast(Execution.expiration, Date).label("exp_date")
        )
        .where(Execution.trade_id.in_(all_trade_ids))
        .order_by(Execution.trade_id, Execution.execution_time)
    )
    exec_result = await session.execute(exec_stmt)
    all_exec_rows = list(exec_result.all())

    # Group executions by trade_id
    executions_by_trade: dict[int, list[tuple]] = {}
    for row in all_exec_rows:
        trade_id = row[0].trade_id
        if trade_id not in executions_by_trade:
            executions_by_trade[trade_id] = []
        executions_by_trade[trade_id].append(row)

    for trade in trades:
        # Get executions for this trade
        exec_rows = executions_by_trade.get(trade.id, [])

        # Build legs from executions (group by strike/expiration/type)
        legs_dict: dict[str, dict] = {}
        is_stock_trade = False
        for row in exec_rows:
            ex = row[0]  # Execution object
            exp_date = row[1]  # SQL-casted Date (avoids timezone issues)

            if ex.security_type == "STK":
                is_stock_trade = True
                key = f"{trade.underlying}_STK"
                if key not in legs_dict:
                    legs_dict[key] = {
                        "strike": None,
                        "expiration": None,
                        "option_type": None,
                        "quantity": 0,
                        "multiplier": 1,
                        "security_type": "STK",
                    }
                if ex.side == "BOT":
                    legs_dict[key]["quantity"] += int(ex.quantity)
                else:
                    legs_dict[key]["quantity"] -= int(ex.quantity)
            elif ex.security_type == "OPT" and exp_date and ex.strike:
                # Use SQL-casted date to avoid timezone conversion issues
                exp_str = exp_date.strftime('%Y%m%d')
                key = f"{exp_str}_{ex.strike}_{ex.option_type}"
                if key not in legs_dict:
                    legs_dict[key] = {
                        "strike": float(ex.strike),
                        "expiration": exp_str,
                        "option_type": ex.option_type,
                        "quantity": 0,
                        "multiplier": ex.multiplier or 100,
                        "security_type": "OPT",
                    }
                if ex.side == "BOT":
                    legs_dict[key]["quantity"] += int(ex.quantity)
                else:
                    legs_dict[key]["quantity"] -= int(ex.quantity)

        # Filter out closed legs (quantity = 0)
        legs = [leg for leg in legs_dict.values() if leg["quantity"] != 0]

        if not legs:
            continue

        # Try to match legs with IBKR portfolio data
        trade_market_value = Decimal("0")
        trade_unrealized_pnl = Decimal("0")
        matched_legs = []
        all_legs_matched = True

        for leg in legs:
            if leg.get("security_type") == "STK":
                ibkr_key = f"{trade.underlying}_STK"
            else:
                ibkr_key = f"{trade.underlying}_{leg['expiration']}_{leg['strike']}_{leg['option_type']}"

            ibkr_pos = ibkr_by_key.get(ibkr_key)

            if ibkr_pos:
                market_value = Decimal(str(ibkr_pos.get("market_value", 0)))
                unrealized_pnl = Decimal(str(ibkr_pos.get("unrealized_pnl", 0)))
                market_price = ibkr_pos.get("market_price")

                trade_market_value += market_value
                trade_unrealized_pnl += unrealized_pnl

                matched_legs.append({
                    "strike": leg.get("strike"),
                    "expiration": leg.get("expiration"),
                    "option_type": leg.get("option_type"),
                    "security_type": leg.get("security_type", "OPT"),
                    "quantity": leg["quantity"],
                    "price": market_price,
                    "market_value": float(market_value),
                    "delta": None,  # Not available from portfolio
                    "gamma": None,
                    "theta": None,
                    "vega": None,
                    "iv": None,
                    "source": "IBKR",
                })
                any_data = True
            else:
                all_legs_matched = False
                matched_legs.append({
                    "strike": leg.get("strike"),
                    "expiration": leg.get("expiration"),
                    "option_type": leg.get("option_type"),
                    "security_type": leg.get("security_type", "OPT"),
                    "quantity": leg["quantity"],
                    "price": None,
                    "market_value": None,
                    "delta": None,
                    "gamma": None,
                    "theta": None,
                    "vega": None,
                    "iv": None,
                    "source": "UNAVAILABLE",
                })

        # Calculate unrealized P&L percent
        cost_basis = trade.opening_cost or Decimal("0")
        unrealized_pnl_percent = None
        if all_legs_matched and cost_basis != 0:
            unrealized_pnl_percent = float((trade_unrealized_pnl) / abs(cost_basis) * 100)

        # Get underlying price from pre-fetched quotes
        underlying_price = underlying_prices.get(trade.underlying)

        positions_data.append(PositionMarketDataResponse(
            trade_id=trade.id,
            underlying=trade.underlying,
            underlying_price=underlying_price,
            legs=matched_legs,
            total_market_value=float(trade_market_value) if all_legs_matched else None,
            total_cost_basis=float(cost_basis),
            unrealized_pnl=float(trade_unrealized_pnl) if all_legs_matched else None,
            unrealized_pnl_percent=unrealized_pnl_percent,
            net_delta=None,
            net_gamma=None,
            net_theta=None,
            net_vega=None,
            source="IBKR" if all_legs_matched else "UNAVAILABLE",
            timestamp=datetime.now(),
            is_stale=not all_legs_matched,
        ))

        # Aggregate totals
        if all_legs_matched:
            total_market_value += trade_market_value
        total_cost_basis += cost_basis

    # Calculate net unrealized P&L
    net_unrealized_pnl = None
    net_unrealized_pnl_percent = None
    if any_data and total_cost_basis != 0:
        net_unrealized_pnl = float(total_market_value - total_cost_basis)
        net_unrealized_pnl_percent = float((total_market_value - total_cost_basis) / abs(total_cost_basis) * 100)

    # Determine cache status
    if not positions_data:
        cache_status = "empty"
    elif all_fresh:
        cache_status = "fresh"
    elif any_data:
        cache_status = "partial"
    else:
        cache_status = "stale"

    return PositionsMarketDataResponse(
        positions=positions_data,
        net_unrealized_pnl=net_unrealized_pnl,
        net_unrealized_pnl_percent=net_unrealized_pnl_percent,
        total_market_value=float(total_market_value) if any_data else None,
        total_cost_basis=float(total_cost_basis),
        total_delta=float(total_delta) if total_delta else None,
        total_theta=float(total_theta) if total_theta else None,
        ibkr_connected=ibkr_connected,
        source=primary_source,
        timestamp=datetime.now(),
        cache_status=cache_status,
    )


@router.post("/cache/clear")
async def clear_cache(
    service: MarketDataService = Depends(get_market_data_service),
):
    """Clear the market data cache.

    Returns:
        Confirmation message
    """
    service.clear_cache()
    return {"message": "Cache cleared", "timestamp": datetime.now()}
