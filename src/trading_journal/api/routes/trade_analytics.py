"""API routes for trade analytics."""

import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query

logger = logging.getLogger(__name__)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.core.database import get_db
from trading_journal.models.margin_settings import MarginSettings
from trading_journal.models.trade import Trade
from trading_journal.models.trade_leg_greeks import TradeLegGreeks
from trading_journal.schemas.trade_analytics import (
    BatchFetchResponse,
    FetchGreeksRequest,
    FetchGreeksResponse,
    LegGreeksResponse,
    MarginSettingsCreate,
    MarginSettingsList,
    MarginSettingsResponse,
    MarginSettingsUpdate,
    TradeAnalyticsResponse,
    TradeLegsResponse,
)
from trading_journal.services.fred_service import FredService
from trading_journal.services.polygon_service import PolygonService, PolygonServiceError
from trading_journal.services.trade_analytics_service import LegData, TradeAnalyticsService

router = APIRouter(prefix="/trade-analytics", tags=["trade-analytics"])


# ============================================================================
# Margin Settings CRUD (static paths - must come before /{trade_id})
# ============================================================================


@router.get("/margin", response_model=MarginSettingsList)
async def list_margin_settings(
    session: AsyncSession = Depends(get_db),
):
    """List all margin settings.

    Args:
        session: Database session

    Returns:
        List of margin settings
    """
    stmt = select(MarginSettings).order_by(MarginSettings.underlying)
    result = await session.execute(stmt)
    settings = list(result.scalars().all())

    return MarginSettingsList(
        settings=[MarginSettingsResponse.model_validate(s) for s in settings],
        total=len(settings),
    )


@router.post("/margin", response_model=MarginSettingsResponse)
async def create_margin_settings(
    request: MarginSettingsCreate,
    session: AsyncSession = Depends(get_db),
):
    """Create margin settings for an underlying.

    Args:
        request: Margin settings data
        session: Database session

    Returns:
        Created margin settings

    Raises:
        HTTPException: If settings already exist
    """
    # Check if already exists
    stmt = select(MarginSettings).where(
        MarginSettings.underlying == request.underlying.upper()
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Margin settings for {request.underlying} already exist",
        )

    settings = MarginSettings(
        underlying=request.underlying.upper(),
        naked_put_margin_pct=request.naked_put_margin_pct,
        naked_call_margin_pct=request.naked_call_margin_pct,
        spread_margin_pct=request.spread_margin_pct,
        iron_condor_margin_pct=request.iron_condor_margin_pct,
        notes=request.notes,
    )
    session.add(settings)
    await session.commit()
    await session.refresh(settings)

    return MarginSettingsResponse.model_validate(settings)


@router.get("/margin/{underlying}", response_model=MarginSettingsResponse)
async def get_margin_settings(
    underlying: str,
    session: AsyncSession = Depends(get_db),
):
    """Get margin settings for an underlying.

    Args:
        underlying: Underlying symbol
        session: Database session

    Returns:
        Margin settings

    Raises:
        HTTPException: If settings not found
    """
    stmt = select(MarginSettings).where(MarginSettings.underlying == underlying.upper())
    result = await session.execute(stmt)
    settings = result.scalar_one_or_none()

    if not settings:
        raise HTTPException(
            status_code=404,
            detail=f"No margin settings for {underlying}. Using defaults.",
        )

    return MarginSettingsResponse.model_validate(settings)


@router.put("/margin/{underlying}", response_model=MarginSettingsResponse)
async def update_margin_settings(
    underlying: str,
    request: MarginSettingsUpdate,
    session: AsyncSession = Depends(get_db),
):
    """Update margin settings for an underlying.

    Args:
        underlying: Underlying symbol
        request: Updated settings
        session: Database session

    Returns:
        Updated margin settings

    Raises:
        HTTPException: If settings not found
    """
    stmt = select(MarginSettings).where(MarginSettings.underlying == underlying.upper())
    result = await session.execute(stmt)
    settings = result.scalar_one_or_none()

    if not settings:
        raise HTTPException(
            status_code=404, detail=f"No margin settings for {underlying}"
        )

    if request.naked_put_margin_pct is not None:
        settings.naked_put_margin_pct = request.naked_put_margin_pct
    if request.naked_call_margin_pct is not None:
        settings.naked_call_margin_pct = request.naked_call_margin_pct
    if request.spread_margin_pct is not None:
        settings.spread_margin_pct = request.spread_margin_pct
    if request.iron_condor_margin_pct is not None:
        settings.iron_condor_margin_pct = request.iron_condor_margin_pct
    if request.notes is not None:
        settings.notes = request.notes

    await session.commit()
    await session.refresh(settings)

    return MarginSettingsResponse.model_validate(settings)


@router.delete("/margin/{underlying}")
async def delete_margin_settings(
    underlying: str,
    session: AsyncSession = Depends(get_db),
):
    """Delete margin settings for an underlying.

    Args:
        underlying: Underlying symbol
        session: Database session

    Returns:
        Success message

    Raises:
        HTTPException: If settings not found
    """
    stmt = select(MarginSettings).where(MarginSettings.underlying == underlying.upper())
    result = await session.execute(stmt)
    settings = result.scalar_one_or_none()

    if not settings:
        raise HTTPException(
            status_code=404, detail=f"No margin settings for {underlying}"
        )

    await session.delete(settings)
    await session.commit()

    return {"message": f"Margin settings for {underlying} deleted"}


# ============================================================================
# Batch Operations (static paths - must come before /{trade_id})
# ============================================================================


@router.post("/fetch-pending", response_model=BatchFetchResponse)
async def fetch_pending_greeks(
    limit: int = Query(10, ge=1, le=50, description="Max trades to process"),
    session: AsyncSession = Depends(get_db),
):
    """Batch fetch Greeks for trades with pending status.

    Args:
        limit: Maximum number of trades to process
        session: Database session

    Returns:
        Batch fetch statistics
    """
    # Get trades with pending Greeks
    stmt = (
        select(Trade)
        .where(Trade.greeks_pending == True)  # noqa: E712
        .order_by(Trade.opened_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    trades = list(result.scalars().all())

    if not trades:
        return BatchFetchResponse(
            trades_processed=0,
            trades_succeeded=0,
            trades_failed=0,
            message="No trades with pending Greeks",
        )

    succeeded = 0
    failed = 0

    for trade in trades:
        try:
            # Use the fetch endpoint logic
            response = await fetch_trade_greeks(trade.id, FetchGreeksRequest(), session)
            if response.success:
                succeeded += 1
            else:
                failed += 1
        except Exception:
            failed += 1
            trade.greeks_pending = False  # Mark as processed even if failed

    await session.commit()

    return BatchFetchResponse(
        trades_processed=len(trades),
        trades_succeeded=succeeded,
        trades_failed=failed,
        message=f"Processed {len(trades)} trades: {succeeded} succeeded, {failed} failed",
    )


@router.post("/backfill-greeks", response_model=BatchFetchResponse)
async def backfill_missing_greeks(
    limit: int = Query(50, ge=1, le=500, description="Max trades to process"),
    status: str = Query("OPEN", description="Trade status filter (OPEN, CLOSED, or ALL)"),
    session: AsyncSession = Depends(get_db),
):
    """Backfill Greeks for trades that are missing them.

    Unlike fetch-pending, this finds trades where delta_open is NULL
    regardless of the greeks_pending flag.

    Args:
        limit: Maximum number of trades to process
        status: Filter by trade status (OPEN, CLOSED, or ALL)
        session: Database session

    Returns:
        Batch fetch statistics
    """
    # Get trades missing Greeks (exclude stock-only trades)
    stock_strategies = ["Stock", "Long Stock", "Short Stock"]
    conditions = [
        Trade.delta_open.is_(None),
        ~Trade.strategy_type.in_(stock_strategies),  # Only options have Greeks
    ]

    if status != "ALL":
        conditions.append(Trade.status == status)

    stmt = (
        select(Trade)
        .where(*conditions)
        .order_by(Trade.opened_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    trades = list(result.scalars().all())

    if not trades:
        return BatchFetchResponse(
            trades_processed=0,
            trades_succeeded=0,
            trades_failed=0,
            message="No trades found missing Greeks",
        )

    succeeded = 0
    failed = 0

    for trade in trades:
        try:
            # Use the fetch endpoint logic
            response = await fetch_trade_greeks(trade.id, FetchGreeksRequest(), session)
            if response.success:
                succeeded += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            logger.warning(f"Failed to fetch Greeks for trade {trade.id}: {e}")

    await session.commit()

    return BatchFetchResponse(
        trades_processed=len(trades),
        trades_succeeded=succeeded,
        trades_failed=failed,
        message=f"Backfilled {len(trades)} trades: {succeeded} succeeded, {failed} failed",
    )


@router.post("/backfill-analytics", response_model=BatchFetchResponse)
async def backfill_missing_analytics(
    limit: int = Query(100, ge=1, le=1000, description="Max trades to process"),
    status: str = Query("OPEN", description="Trade status filter (OPEN, CLOSED, or ALL)"),
    force: bool = Query(False, description="Force recalculation even if analytics exist"),
    session: AsyncSession = Depends(get_db),
):
    """Backfill analytics (max_profit, max_risk, pop_open) for trades that have Greeks but missing analytics.

    This is faster than backfill-greeks as it doesn't need to call external APIs.
    It only processes trades that already have delta_open populated.

    Args:
        limit: Maximum number of trades to process
        status: Filter by trade status (OPEN, CLOSED, or ALL)
        force: Force recalculation even if analytics exist
        session: Database session

    Returns:
        Batch update statistics
    """
    from trading_journal.services.fred_service import FredService

    # Get trades with Greeks (exclude stock-only trades)
    from sqlalchemy import or_
    stock_strategies = ["Stock", "Long Stock", "Short Stock"]
    conditions = [
        Trade.delta_open.isnot(None),  # Has Greeks
        ~Trade.strategy_type.in_(stock_strategies),  # Only options have analytics
    ]

    # Only filter for missing analytics if not forcing recalculation
    if not force:
        conditions.append(or_(Trade.max_profit.is_(None), Trade.pop_open.is_(None)))

    if status != "ALL":
        conditions.append(Trade.status == status)

    stmt = (
        select(Trade)
        .where(*conditions)
        .order_by(Trade.opened_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    trades = list(result.scalars().all())

    if not trades:
        return BatchFetchResponse(
            trades_processed=0,
            trades_succeeded=0,
            trades_failed=0,
            message="No trades found missing analytics",
        )

    # Get risk-free rate once
    try:
        async with FredService() as fred:
            rate_data = await fred.get_risk_free_rate()
            risk_free_rate = rate_data.rate
    except Exception:
        risk_free_rate = Decimal("0.05")

    analytics_service = TradeAnalyticsService(risk_free_rate=risk_free_rate)

    succeeded = 0
    failed = 0

    for trade in trades:
        try:
            result = await analytics_service.populate_analytics_only(trade, session)
            if result:
                succeeded += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            logger.warning(f"Failed to populate analytics for trade {trade.id}: {e}")

    await session.commit()

    return BatchFetchResponse(
        trades_processed=len(trades),
        trades_succeeded=succeeded,
        trades_failed=failed,
        message=f"Backfilled analytics for {len(trades)} trades: {succeeded} succeeded, {failed} failed",
    )


# ============================================================================
# Trade-specific Analytics (parameterized routes)
# ============================================================================


@router.get("/{trade_id}", response_model=TradeAnalyticsResponse)
async def get_trade_analytics(
    trade_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Get complete analytics for a trade.

    Returns Greeks, IV metrics, PoP, max profit/risk, and collateral.

    Args:
        trade_id: Trade database ID
        session: Database session

    Returns:
        Trade analytics data

    Raises:
        HTTPException: If trade not found
    """
    # Get the trade
    stmt = select(Trade).where(Trade.id == trade_id)
    result = await session.execute(stmt)
    trade = result.scalar_one_or_none()

    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    # Build response from trade data
    return TradeAnalyticsResponse(
        trade_id=trade.id,
        underlying=trade.underlying,
        strategy_type=trade.strategy_type,
        status=trade.status,
        # Net Greeks from trade
        net_delta=trade.delta_open,
        net_gamma=trade.gamma_open,
        net_theta=trade.theta_open,
        net_vega=trade.vega_open,
        # IV metrics
        trade_iv=trade.iv_open,
        iv_percentile_52w=trade.iv_percentile_52w_open,
        iv_rank_52w=trade.iv_rank_52w_open,
        iv_percentile_custom=trade.iv_percentile_custom_open,
        iv_rank_custom=trade.iv_rank_custom_open,
        # Risk analytics
        pop=trade.pop_open,
        breakevens=[],  # Would need to calculate from legs
        max_profit=trade.max_profit,
        max_risk=trade.max_risk,
        risk_reward_ratio=(
            trade.max_profit / trade.max_risk
            if trade.max_profit and trade.max_risk and trade.max_risk > 0
            else None
        ),
        pnl_percent=trade.pnl_percent,
        # Collateral
        collateral_calculated=trade.collateral_calculated,
        collateral_ibkr=trade.collateral_ibkr,
        # Time
        dte=None,  # Would need to calculate from executions
        days_held=trade.days_held,
        # Metadata
        greeks_source=trade.greeks_source,
        greeks_pending=trade.greeks_pending,
        underlying_price=trade.underlying_price_open,
    )


@router.get("/{trade_id}/legs", response_model=TradeLegsResponse)
async def get_trade_leg_greeks(
    trade_id: int,
    snapshot_type: str = Query("OPEN", description="OPEN or CLOSE"),
    session: AsyncSession = Depends(get_db),
):
    """Get per-leg Greeks for a trade.

    Args:
        trade_id: Trade database ID
        snapshot_type: OPEN or CLOSE snapshot
        session: Database session

    Returns:
        Leg-level Greeks data

    Raises:
        HTTPException: If trade not found
    """
    # Verify trade exists
    stmt = select(Trade).where(Trade.id == trade_id)
    result = await session.execute(stmt)
    trade = result.scalar_one_or_none()

    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    # Get leg Greeks
    stmt = (
        select(TradeLegGreeks)
        .where(
            TradeLegGreeks.trade_id == trade_id,
            TradeLegGreeks.snapshot_type == snapshot_type.upper(),
        )
        .order_by(TradeLegGreeks.leg_index)
    )
    result = await session.execute(stmt)
    legs = list(result.scalars().all())

    captured_at = legs[0].captured_at if legs else None

    return TradeLegsResponse(
        trade_id=trade_id,
        snapshot_type=snapshot_type.upper(),
        legs=[LegGreeksResponse.model_validate(leg) for leg in legs],
        captured_at=captured_at,
    )


@router.post("/{trade_id}/fetch-greeks", response_model=FetchGreeksResponse)
async def fetch_trade_greeks(
    trade_id: int,
    request: FetchGreeksRequest = FetchGreeksRequest(),
    session: AsyncSession = Depends(get_db),
):
    """Fetch Greeks for a trade from external data source.

    Fetches Greeks for each leg of the trade and stores them.

    Args:
        trade_id: Trade database ID
        request: Fetch options
        session: Database session

    Returns:
        Fetch status

    Raises:
        HTTPException: If trade not found or fetch fails
    """
    from trading_journal.models.execution import Execution

    # Get the trade
    stmt = select(Trade).where(Trade.id == trade_id)
    result = await session.execute(stmt)
    trade = result.scalar_one_or_none()

    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    # Check if we already have Greeks and not forcing refresh
    if not request.force_refresh and trade.greeks_source:
        return FetchGreeksResponse(
            trade_id=trade_id,
            success=True,
            legs_fetched=0,
            source=trade.greeks_source,
            message="Greeks already exist. Use force_refresh=true to update.",
        )

    # Get executions for this trade to build leg data
    exec_stmt = (
        select(Execution)
        .where(Execution.trade_id == trade_id)
        .order_by(Execution.execution_time)
    )
    result = await session.execute(exec_stmt)
    executions = list(result.scalars().all())

    if not executions:
        return FetchGreeksResponse(
            trade_id=trade_id,
            success=False,
            legs_fetched=0,
            source=None,
            message="No executions found for trade",
        )

    # Build unique legs from executions (by strike/expiration/type)
    # For CLOSED trades: use opening legs (open_close_indicator = 'O')
    # For OPEN trades: use current net position
    legs_map: dict[tuple, dict] = {}

    if trade.status == "CLOSED":
        # For closed trades, look at the opening transactions
        for exec in executions:
            if exec.option_type and exec.strike and exec.expiration:
                # Only include opening transactions
                if exec.open_close_indicator == "O":
                    key = (exec.option_type, exec.strike, exec.expiration)
                    if key not in legs_map:
                        legs_map[key] = {
                            "option_type": exec.option_type,
                            "strike": exec.strike,
                            "expiration": exec.expiration,
                            "quantity": 0,
                        }
                    # BOT = long, SLD = short (for opens)
                    if exec.side == "BOT":
                        legs_map[key]["quantity"] += exec.quantity
                    else:
                        legs_map[key]["quantity"] -= exec.quantity
        active_legs = list(legs_map.values())
    else:
        # For open trades, use net position (existing logic)
        for exec in executions:
            if exec.option_type and exec.strike and exec.expiration:
                key = (exec.option_type, exec.strike, exec.expiration)
                if key not in legs_map:
                    legs_map[key] = {
                        "option_type": exec.option_type,
                        "strike": exec.strike,
                        "expiration": exec.expiration,
                        "quantity": 0,
                    }
                # Accumulate quantity (BOT adds, SLD subtracts for closing)
                if exec.side == "BOT":
                    legs_map[key]["quantity"] += exec.quantity
                else:
                    legs_map[key]["quantity"] -= exec.quantity
        # Filter to legs with non-zero quantity (still open)
        active_legs = [v for v in legs_map.values() if v["quantity"] != 0]

    if not active_legs:
        return FetchGreeksResponse(
            trade_id=trade_id,
            success=True,
            legs_fetched=0,
            source=None,
            message="No active option legs to fetch Greeks for",
        )

    # Fetch Greeks from Polygon
    legs_fetched = 0
    leg_data_list: list[LegData] = []

    try:
        async with PolygonService() as polygon:
            # First get underlying price
            quote = await polygon.get_underlying_price(trade.underlying)
            underlying_price = quote.price if quote else None

            for idx, leg in enumerate(active_legs):
                greeks = await polygon.get_option_greeks(
                    underlying=trade.underlying,
                    expiration=leg["expiration"],
                    option_type=leg["option_type"],
                    strike=leg["strike"],
                    fetch_underlying_price=False,  # Already fetched
                )

                if greeks:
                    legs_fetched += 1
                    leg_data_list.append(
                        LegData(
                            option_type=leg["option_type"],
                            strike=leg["strike"],
                            expiration=leg["expiration"],
                            quantity=leg["quantity"],
                            delta=greeks.delta,
                            gamma=greeks.gamma,
                            theta=greeks.theta,
                            vega=greeks.vega,
                            iv=greeks.iv,
                        )
                    )

                    # Store leg Greeks
                    # Strip timezone from expiration (column is timezone-naive)
                    exp_dt = leg["expiration"]
                    if exp_dt and hasattr(exp_dt, 'tzinfo') and exp_dt.tzinfo is not None:
                        exp_dt = exp_dt.replace(tzinfo=None)

                    leg_greeks = TradeLegGreeks(
                        trade_id=trade_id,
                        snapshot_type="OPEN",
                        leg_index=idx,
                        underlying=trade.underlying,
                        option_type=leg["option_type"],
                        strike=leg["strike"],
                        expiration=exp_dt,
                        quantity=leg["quantity"],
                        delta=greeks.delta,
                        gamma=greeks.gamma,
                        theta=greeks.theta,
                        vega=greeks.vega,
                        iv=greeks.iv,
                        underlying_price=underlying_price,
                        option_price=greeks.option_price,
                        bid=greeks.bid,
                        ask=greeks.ask,
                        bid_ask_spread=greeks.bid_ask_spread,
                        open_interest=greeks.open_interest,
                        volume=greeks.volume,
                        data_source="POLYGON",
                        captured_at=greeks.timestamp,
                    )
                    session.add(leg_greeks)

    except PolygonServiceError as e:
        raise HTTPException(status_code=503, detail=f"Polygon API error: {e}")

    # Calculate trade-level analytics
    if leg_data_list:
        # Get risk-free rate
        try:
            async with FredService() as fred:
                rate_data = await fred.get_risk_free_rate()
                risk_free_rate = rate_data.rate
        except Exception:
            risk_free_rate = Decimal("0.05")

        analytics_service = TradeAnalyticsService(risk_free_rate=risk_free_rate)
        # Use multiplier=1 to store per-contract Greeks (not position-level)
        net_greeks = analytics_service.calculate_net_greeks(leg_data_list, multiplier=1)
        trade_iv = analytics_service.get_trade_iv(leg_data_list, trade.strategy_type)

        # Update trade with analytics
        trade.underlying_price_open = underlying_price
        trade.delta_open = net_greeks["net_delta"]
        trade.gamma_open = net_greeks["net_gamma"]
        trade.theta_open = net_greeks["net_theta"]
        trade.vega_open = net_greeks["net_vega"]
        trade.iv_open = trade_iv
        trade.greeks_source = "POLYGON"
        trade.greeks_pending = False

        # Calculate net premium from executions
        # Include executions with open_close_indicator = "O" or None (infer as opening)
        # For CLOSED trades, also include None since it might be an opening without tag
        net_premium = Decimal("0")
        total_contracts = Decimal("0")
        unique_strikes = set()
        for exec in executions:
            is_opening = exec.open_close_indicator == "O" or (
                exec.open_close_indicator is None and exec.open_close_indicator != "C"
            )
            if exec.security_type == "OPT" and is_opening:
                qty = abs(Decimal(str(exec.quantity)))
                premium_per_share = Decimal(str(exec.price))
                if exec.side == "SLD":
                    net_premium += premium_per_share * qty
                else:
                    net_premium -= premium_per_share * qty
                total_contracts += qty
                unique_strikes.add(exec.strike)

        # Normalize to per-spread premium
        if total_contracts > 0 and unique_strikes:
            num_legs = len(unique_strikes)
            contracts_per_leg = total_contracts / num_legs if num_legs > 0 else total_contracts
            if contracts_per_leg > 0:
                net_premium = net_premium / contracts_per_leg

        # Calculate max profit/risk
        max_profit, max_risk = analytics_service.calculate_max_profit_risk(
            leg_data_list,
            trade.strategy_type or "",
            net_premium,
            multiplier=100,  # Standard option contract multiplier
        )

        # Multiply by number of contracts for total position value
        num_contracts = max(abs(leg.quantity) for leg in leg_data_list) if leg_data_list else 1
        if max_profit is not None:
            trade.max_profit = max_profit * num_contracts
        if max_risk is not None:
            trade.max_risk = max_risk * num_contracts

        # Calculate DTE
        dte = analytics_service.calculate_dte(leg_data_list)

        # Calculate PoP if we have IV and underlying price
        if trade_iv and underlying_price and dte and dte > 0:
            breakevens = analytics_service.calculate_breakevens(
                leg_data_list, trade.strategy_type or "", net_premium
            )
            if breakevens:
                is_credit = net_premium > 0
                pop = analytics_service.calculate_pop_black_scholes(
                    underlying_price,
                    breakevens[0],
                    trade_iv,
                    dte,
                    is_credit,
                )
                trade.pop_open = pop

        # Calculate collateral (multiply by num_contracts for total position)
        collateral = analytics_service._calculate_collateral(
            trade.strategy_type or "",
            leg_data_list,
        )
        if collateral is not None:
            trade.collateral_calculated = collateral * num_contracts
        else:
            trade.collateral_calculated = None

    await session.commit()

    return FetchGreeksResponse(
        trade_id=trade_id,
        success=True,
        legs_fetched=legs_fetched,
        source="POLYGON",
        message=f"Fetched Greeks for {legs_fetched} legs",
    )
