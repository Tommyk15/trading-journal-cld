"""Load sample execution data for testing the trade grouping algorithm."""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import delete
from src.trading_journal.core.database import AsyncSessionLocal
from src.trading_journal.models.execution import Execution
from src.trading_journal.models.trade import Trade


async def load_sample_data():
    """Load sample executions to test the grouping algorithm."""
    async with AsyncSessionLocal() as session:
        print("Clearing existing data...")
        await session.execute(delete(Trade))
        await session.execute(delete(Execution))
        await session.commit()

        base_time = datetime(2024, 11, 1, 10, 0, 0)

        executions = []

        # ==================================================================
        # Test Case 1: Simple long call - open and close (should be 1 CLOSED trade)
        # ==================================================================
        executions.append(Execution(
            order_id=1001,
            exec_id="exec_1001_1",
            perm_id=10010001,
            execution_time=base_time,
            underlying="AAPL",
            security_type="OPT",
            side="BOT",
            quantity=1,
            price=Decimal("5.50"),
            strike=Decimal("150"),
            option_type="C",
            expiration=datetime(2024, 12, 20),
            multiplier=100,
            exchange="SMART",
            account_id="U1234567",
            commission=Decimal("0.65"),
            net_amount=Decimal("550.65"),
        ))

        # Close it 2 days later
        executions.append(Execution(
            order_id=1002,
            perm_id=1002,
            exec_id="exec_1002_1",
            execution_time=base_time + timedelta(days=2),
            underlying="AAPL",
            security_type="OPT",
            side="SLD",
            quantity=1,
            price=Decimal("7.20"),
            strike=Decimal("150"),
            option_type="C",
            expiration=datetime(2024, 12, 20),
            multiplier=100,
            exchange="SMART",
            account_id="U1234567",
            commission=Decimal("0.65"),
            net_amount=Decimal("719.35"),
        ))

        # ==================================================================
        # Test Case 2: Vertical spread - open and close (should be 1 CLOSED trade)
        # ==================================================================
        # Open vertical spread (same order_id for both legs)
        executions.append(Execution(
            order_id=2001,
            exec_id="exec_2001_1",
            execution_time=base_time + timedelta(hours=1),
            underlying="TSLA",
            security_type="OPT",
            side="BOT",
            quantity=1,
            price=Decimal("12.00"),
            strike=Decimal("250"),
            option_type="C",
            expiration=datetime(2024, 12, 15),
            multiplier=100,
            exchange="SMART",
            account_id="U1234567",
            commission=Decimal("0.65"),
            net_amount=Decimal("1200.65"),
        ))

        executions.append(Execution(
            order_id=2001,  # Same order
            exec_id="exec_2001_2",
            execution_time=base_time + timedelta(hours=1, seconds=1),
            underlying="TSLA",
            security_type="OPT",
            side="SLD",
            quantity=1,
            price=Decimal("5.00"),
            strike=Decimal("260"),
            option_type="C",
            expiration=datetime(2024, 12, 15),
            multiplier=100,
            exchange="SMART",
            account_id="U1234567",
            commission=Decimal("0.65"),
            net_amount=Decimal("499.35"),
        ))

        # Close vertical spread 3 days later
        executions.append(Execution(
            order_id=2002,
            exec_id="exec_2002_1",
            execution_time=base_time + timedelta(days=3),
            underlying="TSLA",
            security_type="OPT",
            side="SLD",
            quantity=1,
            price=Decimal("15.00"),
            strike=Decimal("250"),
            option_type="C",
            expiration=datetime(2024, 12, 15),
            multiplier=100,
            exchange="SMART",
            account_id="U1234567",
            commission=Decimal("0.65"),
            net_amount=Decimal("1499.35"),
        ))

        executions.append(Execution(
            order_id=2002,  # Same order
            exec_id="exec_2002_2",
            execution_time=base_time + timedelta(days=3, seconds=1),
            underlying="TSLA",
            security_type="OPT",
            side="BOT",
            quantity=1,
            price=Decimal("8.00"),
            strike=Decimal("260"),
            option_type="C",
            expiration=datetime(2024, 12, 15),
            multiplier=100,
            exchange="SMART",
            account_id="U1234567",
            commission=Decimal("0.65"),
            net_amount=Decimal("800.65"),
        ))

        # ==================================================================
        # Test Case 3: ROLL - close Dec spread, open Jan spread (should be 2 trades, potentially linked)
        # ==================================================================
        # Open Dec spread
        executions.append(Execution(
            order_id=3001,
            exec_id="exec_3001_1",
            execution_time=base_time + timedelta(days=5),
            underlying="NVDA",
            security_type="OPT",
            side="BOT",
            quantity=1,
            price=Decimal("20.00"),
            strike=Decimal("140"),
            option_type="C",
            expiration=datetime(2024, 12, 20),
            multiplier=100,
            exchange="SMART",
            account_id="U1234567",
            commission=Decimal("0.65"),
            net_amount=Decimal("2000.65"),
        ))

        executions.append(Execution(
            order_id=3001,
            exec_id="exec_3001_2",
            execution_time=base_time + timedelta(days=5, seconds=1),
            underlying="NVDA",
            security_type="OPT",
            side="SLD",
            quantity=1,
            price=Decimal("10.00"),
            strike=Decimal("145"),
            option_type="C",
            expiration=datetime(2024, 12, 20),
            multiplier=100,
            exchange="SMART",
            account_id="U1234567",
            commission=Decimal("0.65"),
            net_amount=Decimal("999.35"),
        ))

        # ROLL: Close Dec spread and open Jan spread (10 days later)
        # Close Dec spread
        executions.append(Execution(
            order_id=3002,
            exec_id="exec_3002_1",
            execution_time=base_time + timedelta(days=15),
            underlying="NVDA",
            security_type="OPT",
            side="SLD",
            quantity=1,
            price=Decimal("25.00"),
            strike=Decimal("140"),
            option_type="C",
            expiration=datetime(2024, 12, 20),
            multiplier=100,
            exchange="SMART",
            account_id="U1234567",
            commission=Decimal("0.65"),
            net_amount=Decimal("2499.35"),
        ))

        executions.append(Execution(
            order_id=3002,
            exec_id="exec_3002_2",
            execution_time=base_time + timedelta(days=15, seconds=1),
            underlying="NVDA",
            security_type="OPT",
            side="BOT",
            quantity=1,
            price=Decimal("15.00"),
            strike=Decimal("145"),
            option_type="C",
            expiration=datetime(2024, 12, 20),
            multiplier=100,
            exchange="SMART",
            account_id="U1234567",
            commission=Decimal("0.65"),
            net_amount=Decimal("1500.65"),
        ))

        # Open Jan spread (same execution time, different order)
        executions.append(Execution(
            order_id=3003,
            exec_id="exec_3003_1",
            execution_time=base_time + timedelta(days=15, seconds=2),
            underlying="NVDA",
            security_type="OPT",
            side="BOT",
            quantity=1,
            price=Decimal("22.00"),
            strike=Decimal("145"),
            option_type="C",
            expiration=datetime(2025, 1, 17),  # Different expiration
            multiplier=100,
            exchange="SMART",
            account_id="U1234567",
            commission=Decimal("0.65"),
            net_amount=Decimal("2200.65"),
        ))

        executions.append(Execution(
            order_id=3003,
            exec_id="exec_3003_2",
            execution_time=base_time + timedelta(days=15, seconds=3),
            underlying="NVDA",
            security_type="OPT",
            side="SLD",
            quantity=1,
            price=Decimal("12.00"),
            strike=Decimal("150"),
            option_type="C",
            expiration=datetime(2025, 1, 17),
            multiplier=100,
            exchange="SMART",
            account_id="U1234567",
            commission=Decimal("0.65"),
            net_amount=Decimal("1199.35"),
        ))

        # ==================================================================
        # Test Case 4: Open position (still OPEN) (should be 1 OPEN trade)
        # ==================================================================
        executions.append(Execution(
            order_id=4001,
            exec_id="exec_4001_1",
            execution_time=base_time + timedelta(days=20),
            underlying="SPY",
            security_type="OPT",
            side="BOT",
            quantity=2,
            price=Decimal("8.50"),
            strike=Decimal("450"),
            option_type="P",
            expiration=datetime(2024, 12, 29),
            multiplier=100,
            exchange="SMART",
            account_id="U1234567",
            commission=Decimal("1.30"),
            net_amount=Decimal("1701.30"),
        ))

        # Add all executions
        for execution in executions:
            session.add(execution)

        await session.commit()

        print(f"\n✓ Loaded {len(executions)} sample executions")
        print("\nExpected results:")
        print("  1. AAPL 150C Dec 20 - Single Call (CLOSED)")
        print("  2. TSLA 250/260 Call Spread Dec 15 (CLOSED)")
        print("  3. NVDA 140/145 Call Spread Dec 20 (CLOSED)")
        print("  4. NVDA 145/150 Call Spread Jan 17 (OPEN) - rolled from #3")
        print("  5. SPY 450P Dec 29 - Single Put (OPEN)")
        print("\nTotal expected trades: 5")
        print("  - 3 CLOSED trades")
        print("  - 2 OPEN trades")
        print("  - 1 roll link (NVDA Dec → Jan)")


if __name__ == "__main__":
    asyncio.run(load_sample_data())
