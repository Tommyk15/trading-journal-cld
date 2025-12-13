"""Position Ledger Service - Manages persistent position tracking."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.models.execution import Execution
from trading_journal.models.position_ledger import PositionLedger, PositionStatus


class PositionLedgerService:
    """Service for managing the position ledger.

    The position ledger tracks:
    1. Current position state per underlying/leg
    2. Position lifecycle (open/close times)
    3. Cost basis and realized P&L
    """

    def __init__(self, session: AsyncSession):
        """Initialize position ledger service.

        Args:
            session: Database session
        """
        self.session = session

    def get_leg_key(self, exec: Execution) -> str:
        """Generate unique key for a position leg.

        Args:
            exec: Execution object

        Returns:
            Unique leg key string
        """
        if exec.security_type == "OPT":
            expiry = exec.expiration.strftime("%Y%m%d") if exec.expiration else ""
            strike = f"{exec.strike}" if exec.strike else ""
            return f"{expiry}_{strike}_{exec.option_type}"
        return "STK"

    async def get_position(self, underlying: str, leg_key: str) -> Optional[PositionLedger]:
        """Get position for a specific leg.

        Args:
            underlying: Underlying symbol
            leg_key: Leg key

        Returns:
            PositionLedger or None
        """
        stmt = select(PositionLedger).where(
            and_(
                PositionLedger.underlying == underlying,
                PositionLedger.leg_key == leg_key,
                PositionLedger.status == PositionStatus.OPEN.value
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_positions(self, underlying: Optional[str] = None) -> list[PositionLedger]:
        """Get all open positions.

        Args:
            underlying: Optional filter by underlying

        Returns:
            List of open PositionLedger records
        """
        stmt = select(PositionLedger).where(
            PositionLedger.status == PositionStatus.OPEN.value
        )
        if underlying:
            stmt = stmt.where(PositionLedger.underlying == underlying)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_position_state(self, underlying: str) -> dict[str, int]:
        """Get current position state as a dictionary.

        Args:
            underlying: Underlying symbol

        Returns:
            Dict of leg_key -> quantity
        """
        positions = await self.get_all_positions(underlying)
        return {p.leg_key: p.quantity for p in positions}

    async def apply_execution(self, exec: Execution) -> PositionLedger:
        """Apply an execution to the position ledger.

        Args:
            exec: Execution to apply

        Returns:
            Updated PositionLedger record
        """
        leg_key = self.get_leg_key(exec)
        position = await self.get_position(exec.underlying, leg_key)

        # Calculate delta
        delta = exec.quantity if exec.side == "BOT" else -exec.quantity

        # Calculate cost
        multiplier = exec.multiplier or 1
        cost = exec.price * abs(exec.quantity) * multiplier
        if exec.side == "SLD":
            cost = -cost

        now = datetime.utcnow()

        if position is None:
            # Create new position
            position = PositionLedger(
                underlying=exec.underlying,
                leg_key=leg_key,
                quantity=delta,
                total_cost=cost,
                avg_cost=abs(cost / abs(delta)) if delta != 0 else Decimal("0.00"),
                status=PositionStatus.OPEN.value,
                opened_at=exec.execution_time,
                last_updated=now,
                created_at=now,
            )
            self.session.add(position)
        else:
            # Update existing position
            old_qty = position.quantity
            new_qty = old_qty + delta

            if new_qty == 0:
                # Position closed
                position.quantity = 0
                position.realized_pnl = -position.total_cost - cost
                position.total_cost += cost
                position.status = PositionStatus.CLOSED.value
                position.closed_at = exec.execution_time
            else:
                # Position adjusted
                position.quantity = new_qty
                position.total_cost += cost

                # Update avg cost only if adding to position
                if (old_qty > 0 and delta > 0) or (old_qty < 0 and delta < 0):
                    # Adding to position
                    total_cost = abs(position.total_cost)
                    position.avg_cost = total_cost / abs(new_qty) if new_qty != 0 else Decimal("0.00")

            position.last_updated = now

        await self.session.flush()
        return position

    async def rebuild_from_executions(self, executions: list[Execution]) -> list[PositionLedger]:
        """Rebuild position ledger from a list of executions.

        This clears and rebuilds positions for the affected underlyings.

        Args:
            executions: List of executions to process

        Returns:
            List of resulting PositionLedger records
        """
        if not executions:
            return []

        # Get affected underlyings
        underlyings = set(e.underlying for e in executions)

        # Clear existing positions for these underlyings
        for underlying in underlyings:
            await self._clear_positions(underlying)

        # Sort executions chronologically
        sorted_execs = sorted(executions, key=lambda e: e.execution_time)

        # Apply each execution
        for exec in sorted_execs:
            await self.apply_execution(exec)

        # Return final positions
        result = []
        for underlying in underlyings:
            positions = await self.get_all_positions(underlying)
            result.extend(positions)

        return result

    async def _clear_positions(self, underlying: str) -> None:
        """Clear all positions for an underlying.

        Args:
            underlying: Underlying symbol
        """
        stmt = select(PositionLedger).where(
            PositionLedger.underlying == underlying
        )
        result = await self.session.execute(stmt)
        positions = list(result.scalars().all())

        for pos in positions:
            await self.session.delete(pos)

        await self.session.flush()

    async def sync_with_ibkr_positions(self, ibkr_positions: list[dict]) -> dict:
        """Sync ledger with IBKR positions.

        Compares ledger with actual IBKR positions and returns discrepancies.

        Args:
            ibkr_positions: List of position dicts from IBKR

        Returns:
            Dict with sync results and any discrepancies
        """
        results = {
            "matched": 0,
            "discrepancies": [],
            "missing_in_ledger": [],
            "missing_in_ibkr": [],
        }

        # Get all open positions from ledger
        ledger_positions = await self.get_all_positions()
        ledger_by_key = {
            (p.underlying, p.leg_key): p for p in ledger_positions
        }

        # Check each IBKR position
        ibkr_keys = set()
        for ibkr_pos in ibkr_positions:
            underlying = ibkr_pos.get("underlying")
            leg_key = ibkr_pos.get("leg_key")
            ibkr_qty = ibkr_pos.get("quantity", 0)

            key = (underlying, leg_key)
            ibkr_keys.add(key)

            ledger_pos = ledger_by_key.get(key)

            if ledger_pos is None:
                results["missing_in_ledger"].append({
                    "underlying": underlying,
                    "leg_key": leg_key,
                    "ibkr_qty": ibkr_qty,
                })
            elif ledger_pos.quantity != ibkr_qty:
                results["discrepancies"].append({
                    "underlying": underlying,
                    "leg_key": leg_key,
                    "ledger_qty": ledger_pos.quantity,
                    "ibkr_qty": ibkr_qty,
                    "diff": ibkr_qty - ledger_pos.quantity,
                })
            else:
                results["matched"] += 1

        # Check for positions in ledger but not in IBKR
        for key, ledger_pos in ledger_by_key.items():
            if key not in ibkr_keys:
                results["missing_in_ibkr"].append({
                    "underlying": ledger_pos.underlying,
                    "leg_key": ledger_pos.leg_key,
                    "ledger_qty": ledger_pos.quantity,
                })

        return results
