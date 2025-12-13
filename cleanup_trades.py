"""Clean up duplicate and position-sync trades."""
import asyncio
from sqlalchemy import select, delete
from src.trading_journal.core.database import AsyncSessionLocal
from src.trading_journal.models.trade import Trade


async def cleanup_trades():
    """Remove position-sync trades and duplicates."""
    async with AsyncSessionLocal() as session:
        # 1. Delete all position-sync trades (those with 0 executions)
        print("Deleting position-sync trades (0 executions)...")
        result = await session.execute(
            delete(Trade).where(Trade.num_executions == 0)
        )
        await session.commit()
        print(f"  Deleted {result.rowcount} position-sync trades")

        # 2. Find and delete duplicate execution-based trades
        # Keep the most recent trade for each underlying
        print("\nFinding duplicate execution-based trades...")

        # Get all trades grouped by underlying
        stmt = select(Trade).order_by(Trade.underlying, Trade.created_at.desc())
        result = await session.execute(stmt)
        all_trades = result.scalars().all()

        # Group by underlying and keep only the most recent
        seen_underlyings = set()
        trades_to_delete = []

        for trade in all_trades:
            if trade.underlying in seen_underlyings:
                # Duplicate - mark for deletion
                trades_to_delete.append(trade.id)
            else:
                # First occurrence (most recent) - keep it
                seen_underlyings.add(trade.underlying)

        if trades_to_delete:
            print(f"  Found {len(trades_to_delete)} duplicate trades")
            result = await session.execute(
                delete(Trade).where(Trade.id.in_(trades_to_delete))
            )
            await session.commit()
            print(f"  Deleted {result.rowcount} duplicate trades")

        # 3. Show final count
        count_result = await session.execute(select(Trade))
        remaining = len(count_result.scalars().all())
        print(f"\nFinal trade count: {remaining}")


if __name__ == "__main__":
    asyncio.run(cleanup_trades())
