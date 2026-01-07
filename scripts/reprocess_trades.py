#!/usr/bin/env python3
"""Reprocess all trades to recalculate opening_cost after net_amount fix."""

import asyncio
import sys

sys.path.insert(0, "src")

from trading_journal.core.database import AsyncSessionLocal, init_db
from trading_journal.services.trade_grouping_service import TradeGroupingService


async def reprocess_all():
    """Reprocess all executions into trades."""
    await init_db()

    print("=" * 80)
    print("REPROCESSING ALL TRADES")
    print("=" * 80)
    print()

    async with AsyncSessionLocal() as session:
        service = TradeGroupingService(session)
        stats = await service.reprocess_all_executions()

        print(f"Executions processed: {stats['executions_processed']}")
        print(f"Trades created: {stats['trades_created']}")
        print(f"Trades updated: {stats.get('trades_updated', 0)}")

        await session.commit()

    print()
    print("Done!")


if __name__ == "__main__":
    asyncio.run(reprocess_all())
