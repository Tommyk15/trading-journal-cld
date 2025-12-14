"""Roll detection service - identifies and links rolled positions."""

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.models.execution import Execution
from trading_journal.models.trade import Trade


class RollDetectionService:
    """Service for detecting and tracking rolled positions."""

    def __init__(self, session: AsyncSession):
        """Initialize roll detection service.

        Args:
            session: Database session
        """
        self.session = session
        # Time window for considering trades as potentially rolled
        self.roll_time_window = timedelta(hours=24)

    async def detect_and_link_rolls(
        self,
        underlying: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict:
        """Detect rolls and link trades together.

        Args:
            underlying: Optional filter by underlying
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Dictionary with detection statistics
        """
        stats = {
            "trades_analyzed": 0,
            "rolls_detected": 0,
            "roll_chains_found": 0,
        }

        # Fetch trades ordered by time
        stmt = (
            select(Trade)
            .where(Trade.status == "CLOSED")
            .order_by(Trade.underlying, Trade.closed_at)
        )

        if underlying:
            stmt = stmt.where(Trade.underlying == underlying)
        if start_date:
            stmt = stmt.where(Trade.closed_at >= start_date)
        if end_date:
            stmt = stmt.where(Trade.closed_at <= end_date)

        result = await self.session.execute(stmt)
        trades = list(result.scalars().all())
        stats["trades_analyzed"] = len(trades)

        # Group by underlying for analysis
        from collections import defaultdict

        by_underlying = defaultdict(list)
        for trade in trades:
            by_underlying[trade.underlying].append(trade)

        # Detect rolls for each underlying
        for underlying, underlying_trades in by_underlying.items():
            roll_chains = await self._detect_rolls_for_underlying(underlying_trades)
            stats["rolls_detected"] += sum(len(chain) - 1 for chain in roll_chains)
            stats["roll_chains_found"] += len(roll_chains)

        await self.session.commit()
        return stats

    async def _detect_rolls_for_underlying(
        self, trades: list[Trade]
    ) -> list[list[Trade]]:
        """Detect rolls within a list of trades for the same underlying.

        Args:
            trades: List of trades for the same underlying

        Returns:
            List of roll chains (each chain is a list of connected trades)
        """
        roll_chains = []
        processed = set()

        for i, trade in enumerate(trades):
            if trade.id in processed:
                continue

            # Start a new chain
            chain = [trade]
            processed.add(trade.id)

            # Look for subsequent rolls
            current_trade = trade
            while True:
                next_trade = await self._find_roll_candidate(
                    current_trade, trades[i + 1 :], processed
                )

                if next_trade:
                    chain.append(next_trade)
                    processed.add(next_trade.id)

                    # Link the trades
                    await self._link_roll(current_trade, next_trade)

                    current_trade = next_trade
                else:
                    break

            # Only add chains with actual rolls (length > 1)
            if len(chain) > 1:
                roll_chains.append(chain)

        return roll_chains

    async def _find_roll_candidate(
        self,
        closed_trade: Trade,
        subsequent_trades: list[Trade],
        processed: set,
    ) -> Trade | None:
        """Find a trade that is likely a roll from the closed trade.

        Args:
            closed_trade: The closed trade
            subsequent_trades: Trades that opened after this one closed
            processed: Set of already processed trade IDs

        Returns:
            Trade that is likely a roll, or None
        """
        if not closed_trade.closed_at:
            return None

        for candidate in subsequent_trades:
            if candidate.id in processed:
                continue

            # Check time proximity
            time_diff = candidate.opened_at - closed_trade.closed_at
            if time_diff > self.roll_time_window:
                # Too far apart in time
                continue

            # Check if it's a similar strategy
            if not self._is_similar_strategy(closed_trade, candidate):
                continue

            # Check execution overlap using detailed analysis
            if await self._has_execution_overlap(closed_trade, candidate):
                return candidate

        return None

    def _is_similar_strategy(self, trade1: Trade, trade2: Trade) -> bool:
        """Check if two trades are similar strategies (likely a roll).

        Args:
            trade1: First trade
            trade2: Second trade

        Returns:
            True if strategies are similar
        """
        # Same underlying required
        if trade1.underlying != trade2.underlying:
            return False

        # Similar number of legs (allow some flexibility)
        if abs(trade1.num_legs - trade2.num_legs) > 1:
            return False

        # For single leg trades, always consider similar
        if trade1.num_legs == 1 and trade2.num_legs == 1:
            return True

        # For multi-leg strategies, check strategy type
        # Allow exact match or similar (e.g., both vertical spreads)
        if trade1.strategy_type == trade2.strategy_type:
            return True

        # Check for similar strategy families
        strategy1_base = trade1.strategy_type.replace("Call", "").replace("Put", "").strip()
        strategy2_base = trade2.strategy_type.replace("Call", "").replace("Put", "").strip()

        return strategy1_base == strategy2_base

    async def _has_execution_overlap(
        self, trade1: Trade, trade2: Trade
    ) -> bool:
        """Check if trades have overlapping execution times (sign of a roll).

        Args:
            trade1: First trade (closing)
            trade2: Second trade (opening)

        Returns:
            True if executions overlap temporally
        """
        # Fetch executions for both trades
        trade1_execs = await self._get_trade_executions(trade1)
        trade2_execs = await self._get_trade_executions(trade2)

        if not trade1_execs or not trade2_execs:
            return False

        # Get closing executions from trade1
        trade1_closing = [e for e in trade1_execs if e.execution_time >= (trade1.closed_at - timedelta(hours=1))]

        # Get opening executions from trade2
        trade2_opening = [e for e in trade2_execs if e.execution_time <= (trade2.opened_at + timedelta(hours=1))]

        if not trade1_closing or not trade2_opening:
            return False

        # Check if any closing execution is within 5 minutes of any opening execution
        for close_exec in trade1_closing:
            for open_exec in trade2_opening:
                time_diff = abs((open_exec.execution_time - close_exec.execution_time).total_seconds())
                if time_diff < 300:  # 5 minutes
                    return True

        return False

    async def _get_trade_executions(self, trade: Trade) -> list[Execution]:
        """Get executions for a trade.

        Args:
            trade: Trade to get executions for

        Returns:
            List of executions
        """
        stmt = (
            select(Execution)
            .where(
                Execution.underlying == trade.underlying,
                Execution.execution_time >= trade.opened_at,
            )
            .order_by(Execution.execution_time)
        )

        if trade.closed_at:
            stmt = stmt.where(Execution.execution_time <= trade.closed_at)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _link_roll(self, from_trade: Trade, to_trade: Trade) -> None:
        """Link two trades as a roll.

        Args:
            from_trade: Trade that was rolled from
            to_trade: Trade that was rolled to
        """
        # Mark both trades as rolls
        from_trade.is_roll = True
        from_trade.rolled_to_trade_id = to_trade.id
        from_trade.status = "ROLLED"

        to_trade.is_roll = True
        to_trade.rolled_from_trade_id = from_trade.id

        # Update notes
        if from_trade.notes:
            from_trade.notes += f"\n\nRolled to trade #{to_trade.id}"
        else:
            from_trade.notes = f"Rolled to trade #{to_trade.id}"

        if to_trade.notes:
            to_trade.notes += f"\n\nRolled from trade #{from_trade.id}"
        else:
            to_trade.notes = f"Rolled from trade #{from_trade.id}"

        await self.session.flush()

    async def get_roll_chain(self, trade_id: int) -> list[Trade]:
        """Get the complete roll chain for a trade.

        Args:
            trade_id: Starting trade ID

        Returns:
            List of trades in the roll chain
        """
        # Get the starting trade
        stmt = select(Trade).where(Trade.id == trade_id)
        result = await self.session.execute(stmt)
        trade = result.scalar_one_or_none()

        if not trade:
            return []

        chain = []

        # Walk backwards to find the start of the chain
        current = trade
        while current.rolled_from_trade_id:
            stmt = select(Trade).where(Trade.id == current.rolled_from_trade_id)
            result = await self.session.execute(stmt)
            prev_trade = result.scalar_one_or_none()
            if not prev_trade:
                break
            current = prev_trade

        # Now walk forward building the chain
        chain.append(current)
        while current.rolled_to_trade_id:
            stmt = select(Trade).where(Trade.id == current.rolled_to_trade_id)
            result = await self.session.execute(stmt)
            next_trade = result.scalar_one_or_none()
            if not next_trade:
                break
            chain.append(next_trade)
            current = next_trade

        return chain

    async def get_roll_statistics(
        self,
        underlying: str | None = None,
    ) -> dict:
        """Get statistics about rolled positions.

        Args:
            underlying: Optional filter by underlying

        Returns:
            Dictionary with roll statistics
        """
        stmt = select(Trade).where(Trade.is_roll.is_(True))

        if underlying:
            stmt = stmt.where(Trade.underlying == underlying)

        result = await self.session.execute(stmt)
        rolled_trades = list(result.scalars().all())

        # Count unique roll chains
        processed_chains = set()
        total_chains = 0
        max_chain_length = 0
        total_roll_pnl = Decimal("0.00")

        for trade in rolled_trades:
            # Skip if we've already counted this chain
            if trade.id in processed_chains:
                continue

            # Get the full chain
            chain = await self.get_roll_chain(trade.id)
            chain_length = len(chain)

            if chain_length > 1:
                total_chains += 1
                max_chain_length = max(max_chain_length, chain_length)

                # Calculate total P&L for the chain
                chain_pnl = sum(t.total_pnl for t in chain)
                total_roll_pnl += chain_pnl

                # Mark all trades in chain as processed
                for t in chain:
                    processed_chains.add(t.id)

        return {
            "total_rolled_trades": len(rolled_trades),
            "unique_roll_chains": total_chains,
            "max_chain_length": max_chain_length,
            "average_chain_length": (
                len(rolled_trades) / total_chains if total_chains > 0 else 0
            ),
            "total_roll_pnl": total_roll_pnl,
            "average_roll_pnl": (
                total_roll_pnl / total_chains if total_chains > 0 else Decimal("0.00")
            ),
        }
