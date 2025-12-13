"""Test the new trade grouping algorithm."""

import asyncio
from sqlalchemy import select, delete
from src.trading_journal.core.database import AsyncSessionLocal
from src.trading_journal.models.trade import Trade
from src.trading_journal.models.execution import Execution
from src.trading_journal.services.trade_grouping_service import TradeGroupingService


async def test_new_grouping():
    """Clear trades and reprocess with new algorithm."""
    async with AsyncSessionLocal() as session:
        print("=" * 80)
        print("TESTING NEW TRADE GROUPING ALGORITHM")
        print("=" * 80)

        # Step 1: Clear existing trades
        print("\n1. Clearing existing trades...")
        await session.execute(delete(Trade))

        # Clear trade_id from executions
        result = await session.execute(select(Execution))
        executions = result.scalars().all()
        for exec in executions:
            exec.trade_id = None

        await session.commit()
        print(f"   ✓ Cleared all trades and execution trade_ids")

        # Step 2: Show execution count
        exec_count_result = await session.execute(select(Execution))
        exec_count = len(list(exec_count_result.scalars().all()))
        print(f"\n2. Total executions in database: {exec_count}")

        # Show breakdown by underlying
        stmt = select(Execution.underlying).distinct()
        result = await session.execute(stmt)
        underlyings = result.scalars().all()
        print(f"   Underlyings: {', '.join(underlyings)}")

        for underlying in underlyings:
            stmt = select(Execution).where(Execution.underlying == underlying)
            result = await session.execute(stmt)
            count = len(list(result.scalars().all()))
            print(f"   - {underlying}: {count} executions")

        # Step 3: Process with new algorithm
        print("\n3. Processing trades with NEW algorithm...")
        service = TradeGroupingService(session)
        stats = await service.process_executions_to_trades()

        print(f"   ✓ Processed {stats['executions_processed']} executions")
        print(f"   ✓ Created {stats['trades_created']} trades")

        # Step 4: Show results
        print("\n4. Trades created:")
        print("-" * 80)

        stmt = select(Trade).order_by(Trade.opened_at)
        result = await session.execute(stmt)
        trades = result.scalars().all()

        print(f"\n{'ID':<5} {'Symbol':<6} {'Strategy':<20} {'Status':<7} {'Legs':<5} {'Execs':<6} {'P&L':<12} {'Opened':<20}")
        print("-" * 100)

        for trade in trades:
            pnl = f"${trade.total_pnl:,.2f}" if trade.total_pnl else "$0.00"
            opened = trade.opened_at.strftime("%Y-%m-%d %H:%M:%S") if trade.opened_at else "N/A"
            print(f"{trade.id:<5} {trade.underlying:<6} {trade.strategy_type:<20} {trade.status:<7} "
                  f"{trade.num_legs:<5} {trade.num_executions:<6} {pnl:<12} {opened:<20}")

        # Step 5: Detailed view for first few trades
        print("\n5. Detailed view of first 3 trades:")
        print("=" * 80)

        for i, trade in enumerate(trades[:3], 1):
            print(f"\nTrade {i}: {trade.underlying} {trade.strategy_type} ({trade.status})")
            print(f"  Opened: {trade.opened_at}")
            if trade.closed_at:
                print(f"  Closed: {trade.closed_at}")
            print(f"  Legs: {trade.num_legs}, Executions: {trade.num_executions}")
            print(f"  P&L: ${trade.total_pnl:,.2f}")

            # Show executions for this trade
            stmt = select(Execution).where(Execution.trade_id == trade.id).order_by(Execution.execution_time)
            result = await session.execute(stmt)
            execs = result.scalars().all()

            print(f"\n  Executions:")
            for exec in execs:
                side_symbol = "🟢 BUY " if exec.side == "BOT" else "🔴 SELL"
                if exec.security_type == "OPT":
                    expiry = exec.expiration.strftime("%m/%d/%y") if exec.expiration else "N/A"
                    print(f"    {side_symbol} {exec.quantity:>3} {exec.underlying} ${exec.strike} {exec.option_type} {expiry} @ ${exec.price:.2f}")
                else:
                    print(f"    {side_symbol} {exec.quantity:>3} {exec.underlying} @ ${exec.price:.2f}")

        print("\n" + "=" * 80)
        print("TESTING COMPLETE")
        print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_new_grouping())
