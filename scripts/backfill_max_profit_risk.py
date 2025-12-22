#!/usr/bin/env python3
"""Backfill max_profit and max_risk for all trades.

This script populates max_profit and max_risk values for trades
that are missing them. These calculations don't require Greeks
and only use execution data.

Usage:
    PYTHONPATH=src python scripts/backfill_max_profit_risk.py
"""

import asyncio
import logging
from sqlalchemy import select

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def backfill_max_profit_risk():
    """Backfill max_profit and max_risk for all trades."""
    from trading_journal.core.database import AsyncSessionLocal
    from trading_journal.models.trade import Trade
    from trading_journal.services.trade_analytics_service import TradeAnalyticsService

    analytics_service = TradeAnalyticsService()

    stats = {
        "total": 0,
        "populated": 0,
        "skipped": 0,
        "errors": 0,
    }

    async with AsyncSessionLocal() as session:
        # Find all trades missing max_profit
        stmt = select(Trade).where(Trade.max_profit.is_(None))
        result = await session.execute(stmt)
        trades = list(result.scalars().all())

        stats["total"] = len(trades)
        logger.info(f"Found {stats['total']} trades missing max_profit/max_risk")

        for i, trade in enumerate(trades):
            try:
                success = await analytics_service.populate_max_profit_risk_only(
                    trade, session
                )
                if success:
                    stats["populated"] += 1
                    if (i + 1) % 100 == 0:
                        logger.info(f"Progress: {i + 1}/{stats['total']} trades processed")
                else:
                    stats["skipped"] += 1
            except Exception as e:
                stats["errors"] += 1
                logger.error(f"Error processing trade {trade.id}: {e}")

        await session.commit()

    logger.info(
        f"Backfill complete: {stats['populated']} populated, "
        f"{stats['skipped']} skipped, {stats['errors']} errors "
        f"out of {stats['total']} total"
    )

    return stats


if __name__ == "__main__":
    asyncio.run(backfill_max_profit_risk())
