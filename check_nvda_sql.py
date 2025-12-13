"""Check NVDA butterfly execution details using raw SQL."""

import asyncio
from sqlalchemy import text
from src.trading_journal.core.database import AsyncSessionLocal


async def check_executions():
    """Check NVDA executions."""
    async with AsyncSessionLocal() as session:
        # Get NVDA executions with Nov 28 expiration
        result = await session.execute(text("""
            SELECT
                execution_time,
                order_id,
                side,
                quantity,
                strike,
                option_type,
                open_close_indicator,
                price,
                trade_id
            FROM executions
            WHERE underlying = 'NVDA'
              AND expiration = '2025-11-28'
            ORDER BY execution_time, strike
        """))

        rows = result.fetchall()

        print(f'Found {len(rows)} NVDA executions with Nov 28 expiration:')
        print()
        print(f'{"Time":<20} {"OrderID":<15} {"Side":<5} {"Qty":<5} {"Strike":<8} {"Type":<5} {"O/C":<5} {"Price":<10} {"Trade ID":<10}')
        print('-' * 110)
        for row in rows:
            time_str = row[0].strftime('%Y-%m-%d %H:%M:%S')
            print(f'{time_str:<20} {row[1]:<15} {row[2]:<5} {row[3]:<5} ${row[4]:<7} {row[5]:<5} {row[6] or "N/A":<5} ${float(row[7]):<9.2f} {row[8] or "None":<10}')


if __name__ == "__main__":
    asyncio.run(check_executions())
