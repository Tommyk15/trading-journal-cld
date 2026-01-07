#!/usr/bin/env python3
"""Compare journal costs with IBKR to identify differences."""

import asyncio
import sys
sys.path.insert(0, "src")

from decimal import Decimal
from sqlalchemy import select
from trading_journal.core.database import AsyncSessionLocal, init_db
from trading_journal.models.trade import Trade
from trading_journal.models.execution import Execution


async def analyze_cost_differences():
    """Analyze cost calculation differences between journal and IBKR."""
    await init_db()

    async with AsyncSessionLocal() as session:
        # Get open trades with their executions
        result = await session.execute(
            select(Trade).where(Trade.status == "OPEN").order_by(Trade.underlying)
        )
        trades = result.scalars().all()

        print("=" * 100)
        print("JOURNAL COST BREAKDOWN ANALYSIS")
        print("=" * 100)
        print()

        total_opening_cost = Decimal("0")
        total_commission = Decimal("0")
        total_cost_with_commission = Decimal("0")

        for trade in trades:
            # Get executions for this trade
            exec_result = await session.execute(
                select(Execution).where(Execution.trade_id == trade.id)
            )
            executions = exec_result.scalars().all()

            # Calculate components
            bot_amount = sum(abs(e.net_amount) for e in executions if e.side == "BOT")
            sld_amount = sum(abs(e.net_amount) for e in executions if e.side == "SLD")
            commission = sum(e.commission for e in executions)

            # Net cost (what journal stores as opening_cost)
            net_cost = bot_amount - sld_amount

            # Cost with commission (what IBKR might show)
            cost_with_commission = net_cost + commission

            total_opening_cost += trade.opening_cost
            total_commission += commission
            total_cost_with_commission += cost_with_commission

            print(f"{trade.underlying:8} | {trade.strategy_type:25} | "
                  f"opening_cost: ${trade.opening_cost:>12,.2f} | "
                  f"commission: ${commission:>8,.2f} | "
                  f"cost+comm: ${cost_with_commission:>12,.2f}")

        print()
        print("=" * 100)
        print("TOTALS:")
        print(f"  Total Opening Cost (stored):     ${total_opening_cost:>15,.2f}")
        print(f"  Total Commission:                ${total_commission:>15,.2f}")
        print(f"  Total Cost + Commission:         ${total_cost_with_commission:>15,.2f}")
        print("=" * 100)
        print()
        print("KEY INSIGHT:")
        print("  Journal opening_cost = net_amount (price * qty * multiplier)")
        print("  Journal does NOT include commissions in opening_cost")
        print("  Commissions are tracked separately in total_commission field")
        print()
        print("IF IBKR's 'CST BSS' INCLUDES COMMISSIONS:")
        print(f"  The difference would be the commission total: ${total_commission:,.2f}")


if __name__ == "__main__":
    asyncio.run(analyze_cost_differences())
