"""Clear all data from the database."""

import asyncio
from sqlalchemy import text
from src.trading_journal.core.database import AsyncSessionLocal


async def clear_database():
    """Delete all trades and executions from the database."""
    async with AsyncSessionLocal() as session:
        # Delete positions first (due to foreign key constraints)
        result = await session.execute(text("DELETE FROM positions"))
        print(f"Deleted {result.rowcount} positions")

        # Delete all trades
        result = await session.execute(text("DELETE FROM trades"))
        print(f"Deleted {result.rowcount} trades")

        # Delete all executions
        result = await session.execute(text("DELETE FROM executions"))
        print(f"Deleted {result.rowcount} executions")

        await session.commit()
        print("Database cleared successfully!")


if __name__ == "__main__":
    asyncio.run(clear_database())
