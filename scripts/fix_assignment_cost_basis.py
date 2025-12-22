#!/usr/bin/env python3
"""Fix cost basis for stock positions acquired via option assignment.

When a short put is assigned, the effective cost basis is:
  strike price - premium received

When a short call is assigned, the effective proceeds is:
  strike price + premium received

IBKR reflects this in their cost basis, but our journal treats the stock
acquisition as a standalone transaction. This script adjusts the stock
trade's opening_cost to include the option premium.
"""

import asyncio
import sys
from decimal import Decimal

sys.path.insert(0, "src")

from sqlalchemy import select, text
from trading_journal.core.database import AsyncSessionLocal, init_db
from trading_journal.models.execution import Execution
from trading_journal.models.trade import Trade


async def find_assignments():
    """Find all assignments with their corresponding stock transactions."""
    async with AsyncSessionLocal() as session:
        # Query to find assignments with matching stock transactions
        query = text("""
            SELECT
                opt.id as opt_exec_id,
                opt.underlying,
                opt.execution_time::date as assignment_date,
                opt.option_type,
                opt.strike,
                opt.quantity as opt_qty,
                stk.id as stk_exec_id,
                stk.side as stk_side,
                stk.quantity as stk_qty,
                stk.price as stk_price,
                stk.net_amount as stk_net_amount,
                opt.trade_id as opt_trade_id,
                stk.trade_id as stk_trade_id
            FROM executions opt
            JOIN executions stk ON stk.underlying = opt.underlying
                AND stk.security_type = 'STK'
                AND stk.execution_time::date = opt.execution_time::date
                AND (
                    (opt.option_type = 'P' AND stk.side = 'BOT')
                    OR (opt.option_type = 'C' AND stk.side = 'SLD')
                )
            WHERE opt.security_type = 'OPT'
                AND opt.price = 0
                AND opt.side = 'BOT'
                AND opt.open_close_indicator = 'C'
            ORDER BY opt.execution_time DESC
        """)

        result = await session.execute(query)
        return result.fetchall()


async def get_option_premium_per_contract(session, trade_id: int) -> Decimal:
    """Get the average premium per contract for a short option trade.

    For short options:
    - SLD executions = premium received (positive)
    - BOT executions = premium paid to close (negative, except 0 for assignment)

    Returns the net premium per contract.
    """
    result = await session.execute(
        select(Execution).where(Execution.trade_id == trade_id)
    )
    executions = result.scalars().all()

    total_premium = Decimal("0")
    total_sold_qty = Decimal("0")

    for exec in executions:
        if exec.side == "SLD":
            # Premium received from selling option
            total_premium += abs(exec.net_amount)
            total_sold_qty += exec.quantity
        elif exec.side == "BOT" and exec.price > 0:
            # Premium paid to close (excluding assignment at price 0)
            total_premium -= abs(exec.net_amount)

    if total_sold_qty == 0:
        return Decimal("0")

    # Return premium per contract
    return total_premium / total_sold_qty


async def fix_assignment_cost_basis(dry_run: bool = True):
    """Fix cost basis for stock positions from assignments."""
    await init_db()

    print("=" * 80)
    print("ASSIGNMENT COST BASIS FIX")
    print("=" * 80)
    print()

    assignments = await find_assignments()
    print(f"Found {len(assignments)} assignment transactions")
    print()

    if not assignments:
        print("No assignments found.")
        return

    async with AsyncSessionLocal() as session:
        # Group assignments by stock trade to handle multiple assignments to same stock
        stock_trade_adjustments = {}  # stk_trade_id -> total_adjustment

        for assignment in assignments:
            opt_trade_id = assignment.opt_trade_id
            stk_trade_id = assignment.stk_trade_id
            underlying = assignment.underlying
            option_type = assignment.option_type
            strike = assignment.strike
            opt_qty = Decimal(str(assignment.opt_qty))

            # Get the premium per contract from the short option trade
            premium_per_contract = await get_option_premium_per_contract(session, opt_trade_id)

            if premium_per_contract <= 0:
                # No premium received, skip
                continue

            # Calculate premium for this assignment (qty * premium_per_contract)
            assignment_premium = opt_qty * premium_per_contract

            # Initialize stock trade entry if not exists
            if stk_trade_id not in stock_trade_adjustments:
                # Get the stock trade
                result = await session.execute(
                    select(Trade).where(Trade.id == stk_trade_id)
                )
                stk_trade = result.scalar_one_or_none()

                if not stk_trade:
                    continue

                stock_trade_adjustments[stk_trade_id] = {
                    "underlying": underlying,
                    "stk_trade_id": stk_trade_id,
                    "current_cost": stk_trade.opening_cost,
                    "total_adjustment": Decimal("0"),
                    "assignments": [],
                }

            # For put assignment: reduce cost by premium received
            # For call assignment: increase proceeds by premium received
            if option_type == "P":
                adjustment = -assignment_premium  # Reduce cost
            else:
                adjustment = assignment_premium  # Increase credit

            stock_trade_adjustments[stk_trade_id]["total_adjustment"] += adjustment
            stock_trade_adjustments[stk_trade_id]["assignments"].append({
                "option_type": option_type,
                "strike": strike,
                "opt_qty": opt_qty,
                "premium": assignment_premium,
            })

        # Build fixes list
        fixes = []
        for stk_trade_id, data in stock_trade_adjustments.items():
            adjusted_cost = data["current_cost"] + data["total_adjustment"]
            fixes.append({
                "underlying": data["underlying"],
                "stk_trade_id": stk_trade_id,
                "current_cost": data["current_cost"],
                "total_adjustment": data["total_adjustment"],
                "adjusted_cost": adjusted_cost,
                "assignments": data["assignments"],
            })

        # Print summary
        print(f"{'Underlying':<10} | {'Assignments':<30} | {'Adjustment':<15} | {'Current Cost':<15} | {'Adjusted Cost':<15}")
        print("-" * 100)

        for fix in fixes:
            # Format assignments
            assignment_strs = []
            for a in fix["assignments"]:
                assignment_strs.append(f"{a['opt_qty']:.0f} {a['option_type']} ${a['strike']:.2f}")
            assignments_text = ", ".join(assignment_strs)[:30]

            print(f"{fix['underlying']:<10} | {assignments_text:<30} | ${fix['total_adjustment']:<14,.2f} | ${fix['current_cost']:<14,.2f} | ${fix['adjusted_cost']:<14,.2f}")

        print()
        print(f"Total stock trades to adjust: {len(fixes)}")
        print()

        if dry_run:
            print("DRY RUN - No changes made.")
            print("Run with --apply to apply changes.")
            return

        # Apply fixes
        print("Applying fixes...")
        for fix in fixes:
            result = await session.execute(
                select(Trade).where(Trade.id == fix["stk_trade_id"])
            )
            trade = result.scalar_one()
            trade.opening_cost = fix["adjusted_cost"]

        await session.commit()
        print(f"Applied {len(fixes)} cost basis adjustments.")

    print()
    print("Done!")


if __name__ == "__main__":
    dry_run = "--apply" not in sys.argv
    asyncio.run(fix_assignment_cost_basis(dry_run=dry_run))
