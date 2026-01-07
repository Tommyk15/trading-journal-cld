#!/usr/bin/env python3
"""Fix executions where net_amount incorrectly includes commission.

IBKR's Flex Query NetCash field includes commission:
  - BOT: net_cash = -(cost + commission)
  - SLD: net_cash = +(proceeds - commission)

This script adds commission back to net_amount to make it consistent
with the real-time API import which uses: net_amount = price * qty * multiplier

After fixing net_amount, trades need to be re-grouped to recalculate opening_cost.
"""

import asyncio
import sys
from decimal import Decimal

sys.path.insert(0, "src")

from sqlalchemy import select, update
from trading_journal.core.database import AsyncSessionLocal, init_db
from trading_journal.models.execution import Execution


async def find_affected_executions():
    """Find executions where net_amount includes commission."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Execution).where(Execution.commission > 0)
        )
        executions = result.scalars().all()

        affected = []
        for exec in executions:
            # Calculate expected raw net_amount (price * qty * multiplier)
            multiplier = exec.multiplier or (100 if exec.security_type == "OPT" else 1)
            expected_raw = exec.price * abs(exec.quantity) * multiplier
            if exec.side == "BOT":
                expected_raw = -expected_raw

            # Check if net_amount differs from expected by approximately the commission
            diff = abs(abs(exec.net_amount) - abs(expected_raw))
            if abs(diff - exec.commission) < Decimal("0.10"):  # Allow small rounding
                affected.append({
                    "id": exec.id,
                    "underlying": exec.underlying,
                    "side": exec.side,
                    "net_amount": exec.net_amount,
                    "commission": exec.commission,
                    "expected_raw": expected_raw,
                    "diff": diff,
                })

        return affected


async def fix_net_amounts(dry_run: bool = True):
    """Fix net_amount for executions where it includes commission.

    Args:
        dry_run: If True, only show what would be changed without making changes.
    """
    await init_db()

    print("=" * 80)
    print("COMMISSION FIX FOR NET_AMOUNT")
    print("=" * 80)
    print()

    affected = await find_affected_executions()

    print(f"Found {len(affected)} executions where net_amount includes commission:")
    print()

    if not affected:
        print("No affected executions found.")
        return

    # Group by underlying for summary
    by_underlying = {}
    for exec in affected:
        if exec["underlying"] not in by_underlying:
            by_underlying[exec["underlying"]] = []
        by_underlying[exec["underlying"]].append(exec)

    print(f"{'Underlying':<10} | {'Count':<6} | {'Total Commission':<15}")
    print("-" * 40)
    for underlying, execs in sorted(by_underlying.items()):
        total_comm = sum(e["commission"] for e in execs)
        print(f"{underlying:<10} | {len(execs):<6} | ${total_comm:>12,.2f}")

    print()
    print(f"Total affected executions: {len(affected)}")
    print()

    if dry_run:
        print("DRY RUN - No changes made.")
        print("Run with --apply to apply changes.")
        return

    # Apply fixes
    print("Applying fixes...")
    async with AsyncSessionLocal() as session:
        fixed_count = 0
        for exec_data in affected:
            # Add commission back to net_amount
            # For both BOT and SLD: raw = net_cash + commission
            result = await session.execute(
                select(Execution).where(Execution.id == exec_data["id"])
            )
            exec = result.scalar_one()

            old_net_amount = exec.net_amount
            exec.net_amount = old_net_amount + exec.commission

            fixed_count += 1

        await session.commit()
        print(f"Fixed {fixed_count} executions.")

    print()
    print("=" * 80)
    print("NEXT STEPS:")
    print("1. Re-run trade grouping to recalculate opening_cost:")
    print("   curl -X POST http://localhost:8000/api/v1/trades/regroup-all")
    print()
    print("2. Verify the fix:")
    print("   python scripts/compare_costs_with_ibkr.py")
    print("=" * 80)


if __name__ == "__main__":
    dry_run = "--apply" not in sys.argv
    asyncio.run(fix_net_amounts(dry_run=dry_run))
