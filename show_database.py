"""Show database contents."""

import asyncio
from sqlalchemy import text
from src.trading_journal.core.database import AsyncSessionLocal


async def show_database():
    """Show all database contents."""
    async with AsyncSessionLocal() as session:
        # Count executions
        result = await session.execute(text("SELECT COUNT(*) FROM executions"))
        exec_count = result.scalar()
        print(f"\n{'='*80}")
        print(f"EXECUTIONS: {exec_count} total")
        print(f"{'='*80}")

        if exec_count > 0:
            result = await session.execute(text("""
                SELECT
                    id,
                    execution_time,
                    underlying,
                    side,
                    quantity,
                    strike,
                    option_type,
                    expiration,
                    open_close_indicator,
                    price,
                    trade_id
                FROM executions
                ORDER BY execution_time, underlying, strike
                LIMIT 50
            """))

            rows = result.fetchall()
            print(f"\n{'ID':<5} {'Time':<20} {'Symbol':<6} {'Side':<5} {'Qty':<5} {'Strike':<8} {'Type':<5} {'Exp':<12} {'O/C':<4} {'Price':<10} {'Trade':<6}")
            print('-' * 110)
            for row in rows:
                exp_str = row[7].strftime('%Y-%m-%d') if row[7] else 'N/A'
                print(f"{row[0]:<5} {row[1].strftime('%Y-%m-%d %H:%M:%S'):<20} {row[2]:<6} {row[3]:<5} {row[4]:<5} ${row[5] or 'N/A':<7} {row[6] or 'N/A':<5} {exp_str:<12} {row[8] or 'N/A':<4} ${float(row[9]):<9.2f} {row[10] or 'N/A':<6}")

        # Count trades
        result = await session.execute(text("SELECT COUNT(*) FROM trades"))
        trade_count = result.scalar()
        print(f"\n{'='*80}")
        print(f"TRADES: {trade_count} total")
        print(f"{'='*80}")

        if trade_count > 0:
            result = await session.execute(text("""
                SELECT
                    id,
                    underlying,
                    strategy_type,
                    status,
                    opened_at,
                    closed_at,
                    realized_pnl,
                    num_legs,
                    num_executions
                FROM trades
                ORDER BY opened_at DESC
            """))

            rows = result.fetchall()
            print(f"\n{'ID':<5} {'Symbol':<8} {'Strategy':<20} {'Status':<8} {'Opened':<20} {'Closed':<20} {'P&L':<12} {'Legs':<5} {'Execs':<6}")
            print('-' * 120)
            for row in rows:
                closed_str = row[5].strftime('%Y-%m-%d %H:%M:%S') if row[5] else 'N/A'
                pnl_str = f"${float(row[6]):.2f}" if row[6] else '$0.00'
                print(f"{row[0]:<5} {row[1]:<8} {row[2]:<20} {row[3]:<8} {row[4].strftime('%Y-%m-%d %H:%M:%S'):<20} {closed_str:<20} {pnl_str:<12} {row[7]:<5} {row[8]:<6}")

        # Count positions
        result = await session.execute(text("SELECT COUNT(*) FROM positions"))
        pos_count = result.scalar()
        print(f"\n{'='*80}")
        print(f"POSITIONS: {pos_count} total")
        print(f"{'='*80}\n")


if __name__ == "__main__":
    asyncio.run(show_database())
