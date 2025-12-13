"""Check NVDA butterfly execution details."""

import asyncio
from sqlalchemy import select, and_
from src.trading_journal.core.database import AsyncSessionLocal
from src.trading_journal.models.execution import Execution
from datetime import datetime


async def check_executions():
    """Check NVDA executions."""
    async with AsyncSessionLocal() as session:
        # Get NVDA executions around Nov 24, 2025
        stmt = (
            select(Execution)
            .where(
                and_(
                    Execution.underlying == 'NVDA',
                    Execution.expiration == datetime(2025, 11, 28)
                )
            )
            .order_by(Execution.execution_time, Execution.strike)
        )
        result = await session.execute(stmt)
        execs = result.scalars().all()

        print(f'Found {len(execs)} NVDA executions with Nov 28 expiration:')
        print()
        print(f'{"Time":<20} {"OrderID":<15} {"Side":<5} {"Qty":<5} {"Strike":<8} {"Type":<5} {"O/C":<5} {"Price":<10} {"Trade ID":<10}')
        print('-' * 110)
        for e in execs:
            time_str = e.execution_time.strftime('%Y-%m-%d %H:%M:%S')
            print(f'{time_str:<20} {e.order_id:<15} {e.side:<5} {e.quantity:<5} ${e.strike:<7} {e.option_type:<5} {e.open_close_indicator or "N/A":<5} ${e.price:<9.2f} {e.trade_id or "None":<10}')


if __name__ == "__main__":
    asyncio.run(check_executions())
