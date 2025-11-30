"""Tests for service layer."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from trading_journal.models.execution import Execution
from trading_journal.services.execution_service import ExecutionService
from trading_journal.services.trade_grouping_service import TradeGroupingService


@pytest.mark.asyncio
async def test_create_execution(db_session):
    """Test creating an execution."""
    service = ExecutionService(db_session)

    exec_data = {
        "exec_id": "TEST123",
        "order_id": 1,
        "perm_id": 1,
        "execution_time": datetime.utcnow(),
        "underlying": "SPY",
        "security_type": "STK",
        "exchange": "SMART",
        "currency": "USD",
        "side": "BOT",
        "quantity": 100,
        "price": Decimal("450.00"),
        "commission": Decimal("1.00"),
        "net_amount": Decimal("-45000.00"),
        "account_id": "TEST",
    }

    execution = await service.create_execution(exec_data)

    assert execution.id is not None
    assert execution.exec_id == "TEST123"
    assert execution.underlying == "SPY"
    assert execution.quantity == 100


@pytest.mark.asyncio
async def test_get_by_exec_id(db_session):
    """Test getting execution by exec_id."""
    service = ExecutionService(db_session)

    # Create execution
    exec_data = {
        "exec_id": "TEST456",
        "order_id": 2,
        "perm_id": 2,
        "execution_time": datetime.utcnow(),
        "underlying": "AAPL",
        "security_type": "STK",
        "exchange": "SMART",
        "currency": "USD",
        "side": "SLD",
        "quantity": 50,
        "price": Decimal("180.00"),
        "commission": Decimal("0.50"),
        "net_amount": Decimal("9000.00"),
        "account_id": "TEST",
    }

    await service.create_execution(exec_data)

    # Retrieve it
    execution = await service.get_by_exec_id("TEST456")

    assert execution is not None
    assert execution.exec_id == "TEST456"
    assert execution.underlying == "AAPL"


@pytest.mark.asyncio
async def test_list_executions(db_session):
    """Test listing executions with filters."""
    service = ExecutionService(db_session)

    # Create multiple executions
    for i in range(5):
        exec_data = {
            "exec_id": f"TEST{i}",
            "order_id": i,
            "perm_id": i,
            "execution_time": datetime.utcnow() - timedelta(days=i),
            "underlying": "SPY" if i % 2 == 0 else "AAPL",
            "security_type": "STK",
            "exchange": "SMART",
            "currency": "USD",
            "side": "BOT",
            "quantity": 100,
            "price": Decimal("450.00"),
            "commission": Decimal("1.00"),
            "net_amount": Decimal("-45000.00"),
            "account_id": "TEST",
        }
        await service.create_execution(exec_data)

    # List all
    executions = await service.list_executions(limit=10)
    assert len(executions) == 5

    # Filter by underlying
    spy_execs = await service.list_executions(underlying="SPY", limit=10)
    assert len(spy_execs) == 3


@pytest.mark.asyncio
async def test_trade_grouping_simple(db_session):
    """Test simple trade grouping."""
    exec_service = ExecutionService(db_session)
    trade_service = TradeGroupingService(db_session)

    # Create buy and sell executions for same stock
    buy_data = {
        "exec_id": "BUY1",
        "order_id": 1,
        "perm_id": 1,
        "execution_time": datetime.utcnow(),
        "underlying": "TSLA",
        "security_type": "STK",
        "exchange": "SMART",
        "currency": "USD",
        "side": "BOT",
        "quantity": 100,
        "price": Decimal("250.00"),
        "commission": Decimal("1.00"),
        "net_amount": Decimal("-25000.00"),
        "account_id": "TEST",
    }

    sell_data = {
        "exec_id": "SELL1",
        "order_id": 2,
        "perm_id": 2,
        "execution_time": datetime.utcnow() + timedelta(hours=1),
        "underlying": "TSLA",
        "security_type": "STK",
        "exchange": "SMART",
        "currency": "USD",
        "side": "SLD",
        "quantity": 100,
        "price": Decimal("260.00"),
        "commission": Decimal("1.00"),
        "net_amount": Decimal("26000.00"),
        "account_id": "TEST",
    }

    await exec_service.create_execution(buy_data)
    await exec_service.create_execution(sell_data)

    # Process into trades
    stats = await trade_service.process_executions_to_trades()

    assert stats["executions_processed"] == 2
    assert stats["trades_created"] > 0
