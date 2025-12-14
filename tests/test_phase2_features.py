"""Tests for Phase 2 features - Greeks, rolls, analytics, performance, calendar."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.models.greeks import Greeks
from trading_journal.models.position import Position
from trading_journal.models.trade import Trade
from trading_journal.services.analytics_service import AnalyticsService
from trading_journal.services.calendar_service import CalendarService
from trading_journal.services.greeks_service import GreeksService
from trading_journal.services.performance_metrics_service import PerformanceMetricsService
from trading_journal.services.roll_detection_service import RollDetectionService


@pytest.mark.asyncio
async def test_greeks_service_create_record(db_session: AsyncSession):
    """Test creating a Greeks record."""
    # Create a position first
    position = Position(
        trade_id=1,
        underlying="SPY",
        option_type="C",
        strike=Decimal("450.00"),
        expiration=datetime(2024, 12, 20),
        quantity=10,
        avg_cost=Decimal("5.00"),
    )
    db_session.add(position)
    await db_session.commit()

    # Create Greeks record
    service = GreeksService(db_session)
    greeks_data = {
        "delta": Decimal("0.50"),
        "gamma": Decimal("0.02"),
        "theta": Decimal("-0.05"),
        "vega": Decimal("0.15"),
        "implied_volatility": Decimal("0.25"),
        "underlying_price": Decimal("455.00"),
        "option_price": Decimal("7.50"),
    }

    greeks = await service.create_greeks_record(position.id, greeks_data)
    await db_session.commit()

    assert greeks.position_id == position.id
    assert greeks.delta == Decimal("0.50")
    assert greeks.gamma == Decimal("0.02")
    assert greeks.model_type == "IBKR"


@pytest.mark.asyncio
async def test_greeks_service_get_latest(db_session: AsyncSession):
    """Test getting latest Greeks for a position."""
    # Create position
    position = Position(
        trade_id=1,
        underlying="SPY",
        option_type="P",
        strike=Decimal("440.00"),
        expiration=datetime(2024, 12, 20),
        quantity=-5,
        avg_cost=Decimal("3.00"),
    )
    db_session.add(position)
    await db_session.flush()

    # Create multiple Greeks records
    service = GreeksService(db_session)

    greeks1 = Greeks(
        position_id=position.id,
        timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
        delta=Decimal("-0.30"),
    )
    greeks2 = Greeks(
        position_id=position.id,
        timestamp=datetime.now(timezone.utc),
        delta=Decimal("-0.35"),
    )

    db_session.add_all([greeks1, greeks2])
    await db_session.commit()

    # Get latest
    latest = await service.get_latest_greeks(position.id)

    assert latest is not None
    assert latest.delta == Decimal("-0.35")


@pytest.mark.asyncio
async def test_roll_detection_service(db_session: AsyncSession):
    """Test roll detection between trades."""
    # Create two trades that look like a roll
    now = datetime.now(timezone.utc)

    trade1 = Trade(
        underlying="SPY",
        strategy_type="Vertical Call Spread",
        status="CLOSED",
        opened_at=now - timedelta(days=10),
        closed_at=now,
        realized_pnl=Decimal("100.00"),
        unrealized_pnl=Decimal("0.00"),
        total_pnl=Decimal("100.00"),
        opening_cost=Decimal("500.00"),
        closing_proceeds=Decimal("600.00"),
        total_commission=Decimal("2.00"),
        num_legs=2,
        num_executions=4,
    )

    trade2 = Trade(
        underlying="SPY",
        strategy_type="Vertical Call Spread",
        status="CLOSED",
        opened_at=now + timedelta(minutes=5),
        closed_at=now + timedelta(days=5),
        realized_pnl=Decimal("50.00"),
        unrealized_pnl=Decimal("0.00"),
        total_pnl=Decimal("50.00"),
        opening_cost=Decimal("450.00"),
        closing_proceeds=Decimal("500.00"),
        total_commission=Decimal("2.00"),
        num_legs=2,
        num_executions=4,
    )

    db_session.add_all([trade1, trade2])
    await db_session.commit()

    # Detect rolls
    service = RollDetectionService(db_session)
    stats = await service.detect_and_link_rolls()

    assert stats["trades_analyzed"] == 2


@pytest.mark.asyncio
async def test_analytics_service_win_rate(db_session: AsyncSession):
    """Test win rate calculation."""
    # Create winning and losing trades
    trades = [
        Trade(
            underlying="SPY",
            strategy_type="Single",
            status="CLOSED",
            opened_at=datetime.now(timezone.utc) - timedelta(days=i),
            closed_at=datetime.now(timezone.utc) - timedelta(days=i-1),
            realized_pnl=Decimal("100.00") if i % 2 == 0 else Decimal("-50.00"),
            unrealized_pnl=Decimal("0.00"),
            total_pnl=Decimal("100.00") if i % 2 == 0 else Decimal("-50.00"),
            opening_cost=Decimal("500.00"),
            closing_proceeds=Decimal("600.00") if i % 2 == 0 else Decimal("450.00"),
            total_commission=Decimal("2.00"),
            num_legs=1,
            num_executions=2,
        )
        for i in range(10)
    ]

    db_session.add_all(trades)
    await db_session.commit()

    # Calculate win rate
    service = AnalyticsService(db_session)
    stats = await service.get_win_rate()

    assert stats["total_trades"] == 10
    assert stats["winning_trades"] == 5
    assert stats["losing_trades"] == 5
    assert stats["win_rate"] == 50.0


@pytest.mark.asyncio
async def test_analytics_service_strategy_breakdown(db_session: AsyncSession):
    """Test strategy breakdown calculation."""
    # Create trades with different strategies
    strategies = ["Single", "Vertical Call Spread", "Iron Condor"]
    trades = []

    for i, strategy in enumerate(strategies):
        for j in range(3):
            trade = Trade(
                underlying="SPY",
                strategy_type=strategy,
                status="CLOSED",
                opened_at=datetime.now(timezone.utc) - timedelta(days=i*3+j),
                closed_at=datetime.now(timezone.utc) - timedelta(days=i*3+j-1),
                realized_pnl=Decimal(str((i + 1) * 50)),
                unrealized_pnl=Decimal("0.00"),
                total_pnl=Decimal(str((i + 1) * 50)),
                opening_cost=Decimal("500.00"),
                closing_proceeds=Decimal(str(500 + (i + 1) * 50)),
                total_commission=Decimal("2.00"),
                num_legs=i + 1,
                num_executions=(i + 1) * 2,
            )
            trades.append(trade)

    db_session.add_all(trades)
    await db_session.commit()

    # Get breakdown
    service = AnalyticsService(db_session)
    breakdown = await service.get_strategy_breakdown()

    assert len(breakdown) == 3
    # Iron Condor should be first (highest P&L)
    assert breakdown[0]["strategy_type"] == "Iron Condor"
    assert breakdown[0]["total_trades"] == 3


@pytest.mark.asyncio
async def test_performance_metrics_cumulative_pnl(db_session: AsyncSession):
    """Test cumulative P&L calculation."""
    # Create trades with increasing cumulative P&L
    trades = []
    for i in range(5):
        trade = Trade(
            underlying="SPY",
            strategy_type="Single",
            status="CLOSED",
            opened_at=datetime.now(timezone.utc) - timedelta(days=5-i),
            closed_at=datetime.now(timezone.utc) - timedelta(days=4-i),
            realized_pnl=Decimal(str(100 + i * 50)),
            unrealized_pnl=Decimal("0.00"),
            total_pnl=Decimal(str(100 + i * 50)),
            opening_cost=Decimal("500.00"),
            closing_proceeds=Decimal(str(600 + i * 50)),
            total_commission=Decimal("2.00"),
            num_legs=1,
            num_executions=2,
        )
        trades.append(trade)

    db_session.add_all(trades)
    await db_session.commit()

    # Get cumulative P&L
    service = PerformanceMetricsService(db_session)
    time_series = await service.get_cumulative_pnl()

    assert len(time_series) == 5
    # Check cumulative values
    assert time_series[0]["cumulative_pnl"] == Decimal("100.00")
    assert time_series[4]["cumulative_pnl"] == Decimal("100.00") + Decimal("150.00") + Decimal("200.00") + Decimal("250.00") + Decimal("300.00")


@pytest.mark.asyncio
async def test_performance_metrics_drawdown(db_session: AsyncSession):
    """Test drawdown calculation."""
    # Create trades that create a drawdown
    trades = [
        Trade(
            underlying="SPY",
            strategy_type="Single",
            status="CLOSED",
            opened_at=datetime.now(timezone.utc) - timedelta(days=5),
            closed_at=datetime.now(timezone.utc) - timedelta(days=4),
            realized_pnl=Decimal("100.00"),  # Cumulative: 100
            unrealized_pnl=Decimal("0.00"),
            total_pnl=Decimal("100.00"),
            opening_cost=Decimal("500.00"),
            closing_proceeds=Decimal("600.00"),
            total_commission=Decimal("2.00"),
            num_legs=1,
            num_executions=2,
        ),
        Trade(
            underlying="SPY",
            strategy_type="Single",
            status="CLOSED",
            opened_at=datetime.now(timezone.utc) - timedelta(days=4),
            closed_at=datetime.now(timezone.utc) - timedelta(days=3),
            realized_pnl=Decimal("100.00"),  # Cumulative: 200
            unrealized_pnl=Decimal("0.00"),
            total_pnl=Decimal("100.00"),
            opening_cost=Decimal("500.00"),
            closing_proceeds=Decimal("600.00"),
            total_commission=Decimal("2.00"),
            num_legs=1,
            num_executions=2,
        ),
        Trade(
            underlying="SPY",
            strategy_type="Single",
            status="CLOSED",
            opened_at=datetime.now(timezone.utc) - timedelta(days=3),
            closed_at=datetime.now(timezone.utc) - timedelta(days=2),
            realized_pnl=Decimal("-150.00"),  # Cumulative: 50 (drawdown!)
            unrealized_pnl=Decimal("0.00"),
            total_pnl=Decimal("-150.00"),
            opening_cost=Decimal("500.00"),
            closing_proceeds=Decimal("350.00"),
            total_commission=Decimal("2.00"),
            num_legs=1,
            num_executions=2,
        ),
    ]

    db_session.add_all(trades)
    await db_session.commit()

    # Calculate drawdown
    service = PerformanceMetricsService(db_session)
    drawdown = await service.get_drawdown_analysis()

    assert drawdown["peak_equity"] == Decimal("200.00")
    assert drawdown["max_drawdown"] == Decimal("150.00")
    assert drawdown["max_drawdown_percentage"] == 75.0


@pytest.mark.asyncio
async def test_calendar_service_upcoming_expirations(db_session: AsyncSession):
    """Test upcoming expirations retrieval."""
    # Create positions with different expirations
    now = datetime.now(timezone.utc)
    positions = [
        Position(
            trade_id=1,
            underlying="SPY",
            option_type="C",
            strike=Decimal("450.00"),
            expiration=now + timedelta(days=5),
            quantity=10,
            avg_cost=Decimal("5.00"),
        ),
        Position(
            trade_id=1,
            underlying="SPY",
            option_type="P",
            strike=Decimal("440.00"),
            expiration=now + timedelta(days=15),
            quantity=-5,
            avg_cost=Decimal("3.00"),
        ),
        Position(
            trade_id=2,
            underlying="QQQ",
            option_type="C",
            strike=Decimal("380.00"),
            expiration=now + timedelta(days=45),
            quantity=10,
            avg_cost=Decimal("4.00"),
        ),
    ]

    db_session.add_all(positions)
    await db_session.commit()

    # Get upcoming expirations (30 days)
    service = CalendarService(db_session)
    expirations = await service.get_upcoming_expirations(days_ahead=30)

    assert len(expirations) == 2  # Only first two should be included
    assert expirations[0]["days_until_expiration"] < expirations[1]["days_until_expiration"]


@pytest.mark.asyncio
async def test_calendar_service_monthly_summary(db_session: AsyncSession):
    """Test monthly summary calculation."""
    # Create trades in a specific month
    year = 2024
    month = 11

    trades = []
    for i in range(5):
        trade = Trade(
            underlying="SPY",
            strategy_type="Single",
            status="CLOSED",
            opened_at=datetime(year, month, i+1),
            closed_at=datetime(year, month, i+2),
            realized_pnl=Decimal(str(50 + i * 10)),
            unrealized_pnl=Decimal("0.00"),
            total_pnl=Decimal(str(50 + i * 10)),
            opening_cost=Decimal("500.00"),
            closing_proceeds=Decimal(str(550 + i * 10)),
            total_commission=Decimal("2.00"),
            num_legs=1,
            num_executions=2,
        )
        trades.append(trade)

    db_session.add_all(trades)
    await db_session.commit()

    # Get monthly summary
    service = CalendarService(db_session)
    summary = await service.get_monthly_summary(year=year, month=month)

    assert summary["total_trades"] == 5
    assert summary["total_pnl"] == Decimal("50") + Decimal("60") + Decimal("70") + Decimal("80") + Decimal("90")


@pytest.mark.asyncio
async def test_calendar_service_day_of_week_analysis(db_session: AsyncSession):
    """Test day of week analysis."""
    # Create trades on specific days
    base_date = datetime(2024, 11, 4)  # A Monday

    trades = []
    for i in range(7):
        trade = Trade(
            underlying="SPY",
            strategy_type="Single",
            status="CLOSED",
            opened_at=base_date + timedelta(days=i),
            closed_at=base_date + timedelta(days=i, hours=2),
            realized_pnl=Decimal(str((i + 1) * 10)),
            unrealized_pnl=Decimal("0.00"),
            total_pnl=Decimal(str((i + 1) * 10)),
            opening_cost=Decimal("500.00"),
            closing_proceeds=Decimal(str(500 + (i + 1) * 10)),
            total_commission=Decimal("2.00"),
            num_legs=1,
            num_executions=2,
        )
        trades.append(trade)

    db_session.add_all(trades)
    await db_session.commit()

    # Get day of week analysis
    service = CalendarService(db_session)
    stats = await service.get_day_of_week_analysis()

    # Should have stats for all 7 days
    assert len(stats) == 7
    # Check that Monday (day 0) has correct data
    monday_stats = next(s for s in stats if s["day_number"] == 0)
    assert monday_stats["total_trades"] == 1
    assert monday_stats["total_pnl"] == Decimal("10.00")
