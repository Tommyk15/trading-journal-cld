"""Check if trades exist in database."""
import asyncio
from sqlalchemy import select, func
from src.trading_journal.core.database import AsyncSessionLocal
from src.trading_journal.models.trade import Trade


async def check_trades():
    """Query trades from database."""
    async with AsyncSessionLocal() as session:
        # Count total trades
        count_result = await session.execute(select(func.count(Trade.id)))
        count = count_result.scalar()
        print(f"Total trades in database: {count}")

        # Get first 5 trades
        result = await session.execute(
            select(Trade).limit(5)
        )
        trades = result.scalars().all()

        print(f"\nFirst {len(trades)} trades:")
        for trade in trades:
            print(f"  ID: {trade.id}, Symbol: {trade.underlying_symbol}, "
                  f"Strategy: {trade.strategy}, Status: {trade.status}, "
                  f"Qty: {trade.quantity}, PnL: {trade.realized_pnl}")


if __name__ == "__main__":
    asyncio.run(check_trades())
