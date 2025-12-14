"""Trade grouping service - converts executions into trades with strategy classification.

This module uses a position state machine approach to correctly identify trade boundaries:
1. Tracks cumulative position state across all executions
2. Detects when positions open, close, roll, or adjust
3. Groups executions into logical trades with proper strategy classification
"""

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.models.execution import Execution
from trading_journal.models.trade import Trade
from trading_journal.services.position_state_machine import (
    PositionStateMachine,
    TradeGroup,
    classify_strategy_from_opening,
)


class TradeLedger:
    """Ledger for tracking positions and executions."""

    def __init__(self, underlying: str):
        """Initialize ledger for an underlying.

        Args:
            underlying: Underlying symbol
        """
        self.underlying = underlying
        self.position_ledger: dict[str, dict] = {}
        self.executions: list[Execution] = []

    def get_leg_key(self, execution: Execution) -> str:
        """Generate unique key for a position leg.

        Args:
            execution: Execution object

        Returns:
            Unique leg key
        """
        if execution.security_type == "OPT":
            expiry = execution.expiration.strftime("%Y%m%d") if execution.expiration else ""
            return f"{expiry}_{execution.strike}_{execution.option_type}"
        return "STK"

    def add_execution(self, execution: Execution) -> None:
        """Add execution and update position ledger.

        Args:
            execution: Execution to add
        """
        self.executions.append(execution)
        leg_key = self.get_leg_key(execution)

        # Calculate signed quantity (positive for buy, negative for sell)
        signed_qty = execution.quantity
        if execution.side == "SLD":
            signed_qty = -signed_qty

        # Initialize leg if needed
        if leg_key not in self.position_ledger:
            self.position_ledger[leg_key] = {
                "quantity": 0,
                "total_cost": Decimal("0.00"),
                "executions": [],
            }

        leg = self.position_ledger[leg_key]

        # Calculate cost (positive for buy, negative for sell)
        multiplier = execution.multiplier or 1
        cost = execution.price * abs(execution.quantity) * multiplier

        if execution.side == "SLD":
            cost = -cost

        # Update ledger
        leg["quantity"] += signed_qty
        leg["total_cost"] += cost
        leg["executions"].append(execution)

    def is_flat(self) -> bool:
        """Check if all positions are flat (zero quantity).

        Returns:
            True if all legs have zero quantity
        """
        return all(leg["quantity"] == 0 for leg in self.position_ledger.values())

    def get_open_legs(self) -> dict:
        """Get legs with non-zero quantity.

        Returns:
            Dictionary of open legs
        """
        return {k: v for k, v in self.position_ledger.items() if v["quantity"] != 0}

    def get_pnl(self) -> Decimal:
        """Calculate total P&L (negative of total cost).

        Returns:
            Total P&L
        """
        return -sum(leg["total_cost"] for leg in self.position_ledger.values())


class TradeGroupingService:
    """Service for grouping executions into trades using position state machine."""

    def __init__(self, session: AsyncSession):
        """Initialize trade grouping service.

        Args:
            session: Database session
        """
        self.session = session

    async def process_executions_to_trades(
        self,
        underlying: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict:
        """Process executions into trades with strategy classification.

        Uses a position state machine to correctly identify trade boundaries:
        - Tracks cumulative position state across all executions
        - Detects when positions open, close, or change structure
        - Handles rolls, adjustments, and multi-leg strategies

        Args:
            underlying: Optional filter by underlying
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Dictionary with processing statistics
        """
        stats = {
            "executions_processed": 0,
            "trades_created": 0,
            "trades_updated": 0,
        }

        # Fetch executions
        stmt = select(Execution).order_by(
            Execution.execution_time,
            Execution.underlying,
            Execution.security_type,
        )

        if underlying:
            stmt = stmt.where(Execution.underlying == underlying)
        if start_date:
            stmt = stmt.where(Execution.execution_time >= start_date)
        if end_date:
            stmt = stmt.where(Execution.execution_time <= end_date)

        result = await self.session.execute(stmt)
        executions = list(result.scalars().all())
        stats["executions_processed"] = len(executions)

        # Group by underlying first
        by_underlying = defaultdict(list)
        for exec in executions:
            by_underlying[exec.underlying].append(exec)

        # Process each underlying with position state machine
        for underlying_symbol, execs in by_underlying.items():
            trades_created = await self._process_underlying_with_state_machine(
                underlying_symbol, execs
            )
            stats["trades_created"] += trades_created

        await self.session.commit()
        return stats

    async def _process_underlying_with_state_machine(
        self, underlying: str, executions: list[Execution]
    ) -> int:
        """Process executions for one underlying using position state machine.

        This algorithm:
        1. Groups near-simultaneous executions (multi-leg orders)
        2. Separates closing vs opening executions using open_close_indicator
        3. Tracks cumulative position state across all executions
        4. Detects trade boundaries when position structure changes
        5. Handles rolls by properly assigning closing executions to existing trades

        Args:
            underlying: Underlying symbol
            executions: List of executions for this underlying

        Returns:
            Number of trades created
        """
        if not executions:
            return 0

        trades_created = 0

        # Sort executions chronologically
        sorted_execs = sorted(executions, key=lambda e: e.execution_time)

        # Step 1: Group near-simultaneous executions (multi-leg orders)
        execution_groups = self._group_simultaneous_executions(sorted_execs)

        # Step 2: Process groups with position state machine
        # Track multiple open trades by their leg keys
        open_trades: dict[frozenset, TradeLedger] = {}  # leg_keys -> TradeLedger
        cumulative_position: dict[str, int] = {}  # leg_key -> net quantity

        for group in execution_groups:
            # Separate closing vs opening executions
            closing_execs = []
            opening_execs = []

            for exec in group:
                leg_key = self._get_leg_key_from_exec(exec)
                current_qty = cumulative_position.get(leg_key, 0)

                if exec.open_close_indicator == 'C':
                    closing_execs.append(exec)
                elif exec.open_close_indicator == 'O':
                    opening_execs.append(exec)
                elif current_qty != 0:
                    # Has existing position - check if this reduces it
                    delta = exec.quantity if exec.side == "BOT" else -exec.quantity
                    if (current_qty > 0 and delta < 0) or (current_qty < 0 and delta > 0):
                        closing_execs.append(exec)
                    else:
                        opening_execs.append(exec)
                else:
                    # No position, must be opening
                    opening_execs.append(exec)

            # Process closing executions - add to existing trades
            for exec in closing_execs:
                leg_key = self._get_leg_key_from_exec(exec)

                # Find existing trade that has this leg
                matching_trade_key = None
                for trade_key in open_trades:
                    if leg_key in trade_key:
                        matching_trade_key = trade_key
                        break

                if matching_trade_key is not None:
                    # Add to existing trade
                    open_trades[matching_trade_key].add_execution(exec)
                    self._update_cumulative_position(cumulative_position, exec)

                    # Check if trade is now closed
                    if self._trade_legs_are_flat(set(matching_trade_key), cumulative_position):
                        trade = await self._save_trade_from_ledger(
                            open_trades[matching_trade_key], is_closed=True
                        )
                        if trade:
                            trades_created += 1
                        del open_trades[matching_trade_key]
                else:
                    # No matching trade - treat as opening (orphaned close)
                    opening_execs.append(exec)

            # Process opening executions - create new trade or add to existing
            if opening_execs:
                opening_legs = frozenset(
                    self._get_leg_key_from_exec(e) for e in opening_execs
                )

                # Check if there's an existing trade with overlapping legs
                matching_trade_key = None
                for trade_key in open_trades:
                    if opening_legs & trade_key:  # Any overlap
                        matching_trade_key = trade_key
                        break

                if matching_trade_key is not None:
                    # Add to existing trade and update its leg key
                    for exec in opening_execs:
                        open_trades[matching_trade_key].add_execution(exec)
                        self._update_cumulative_position(cumulative_position, exec)

                    # Update trade key to include new legs
                    new_key = matching_trade_key | opening_legs
                    if new_key != matching_trade_key:
                        open_trades[new_key] = open_trades.pop(matching_trade_key)
                else:
                    # Create new trade
                    new_trade = TradeLedger(underlying)
                    for exec in opening_execs:
                        new_trade.add_execution(exec)
                        self._update_cumulative_position(cumulative_position, exec)
                    open_trades[opening_legs] = new_trade

        # Handle any remaining open trades
        for trade_key, ledger in open_trades.items():
            is_closed = self._trade_legs_are_flat(set(trade_key), cumulative_position)
            trade = await self._save_trade_from_ledger(ledger, is_closed=is_closed)
            if trade:
                trades_created += 1

        return trades_created

    def _group_simultaneous_executions(self, executions: list[Execution]) -> list[list[Execution]]:
        """Group near-simultaneous executions (multi-leg orders).

        Groups executions that occur within a short time window, regardless of order_id.
        This handles:
        - Combo orders (same order_id)
        - Multi-leg strategies placed as separate orders
        - Spreads executed simultaneously but with different order IDs

        Args:
            executions: Sorted list of executions

        Returns:
            List of execution groups
        """
        if not executions:
            return []

        groups = []
        current_group = []
        group_start_time = None

        # Very tight window - executions within 2 seconds are likely part of same strategy
        TIME_WINDOW = timedelta(seconds=2)

        for exec in executions:
            if not current_group:
                # Start new group
                current_group = [exec]
                group_start_time = exec.execution_time
            else:
                # Check if this execution is close enough to the group start
                time_diff = exec.execution_time - group_start_time

                if time_diff <= TIME_WINDOW:
                    # Within time window - add to current group
                    current_group.append(exec)
                else:
                    # Too far apart - finalize current group and start new one
                    groups.append(current_group)
                    current_group = [exec]
                    group_start_time = exec.execution_time

        # Add final group
        if current_group:
            groups.append(current_group)

        return groups

    def _get_leg_key_from_exec(self, execution: Execution) -> str:
        """Get leg key from execution (same as TradeLedger.get_leg_key)."""
        if execution.security_type == "OPT":
            expiry = execution.expiration.strftime("%Y%m%d") if execution.expiration else ""
            return f"{expiry}_{execution.strike}_{execution.option_type}"
        return "STK"

    def _update_cumulative_position(self, position: dict[str, int], execution: Execution) -> None:
        """Update cumulative position with an execution.

        Args:
            position: Cumulative position dict (leg_key -> quantity)
            execution: Execution to apply
        """
        leg_key = self._get_leg_key_from_exec(execution)
        delta = execution.quantity if execution.side == "BOT" else -execution.quantity
        position[leg_key] = position.get(leg_key, 0) + delta

    def _trade_legs_are_flat(self, trade_legs: set[str], cumulative_position: dict[str, int]) -> bool:
        """Check if all legs of a trade are flat (zero quantity).

        Args:
            trade_legs: Set of leg keys in the trade
            cumulative_position: Current cumulative position

        Returns:
            True if all trade legs are at zero quantity
        """
        return all(cumulative_position.get(leg, 0) == 0 for leg in trade_legs)

    async def _save_trade_from_ledger(self, ledger: TradeLedger, is_closed: bool) -> Optional[Trade]:
        """Save a trade from a ledger.

        Args:
            ledger: Trade ledger with executions
            is_closed: Whether the trade is closed

        Returns:
            Created Trade object or None
        """
        trade_data = self._create_trade_data(ledger, is_closed=is_closed)
        trade_executions = trade_data.pop("executions", [])
        trade = await self._create_or_update_trade(trade_data)
        if trade:
            # Assign trade_id to all executions
            for execution in trade_executions:
                execution.trade_id = trade.id
        return trade

    def _create_trade_data(self, ledger: TradeLedger, is_closed: bool) -> dict:
        """Create trade data dictionary from ledger.

        Args:
            ledger: Trade ledger
            is_closed: Whether trade is closed

        Returns:
            Trade data dictionary
        """
        legs = ledger.get_open_legs() if not is_closed else ledger.position_ledger
        strategy = self._classify_strategy(legs)

        # Calculate timestamps
        opened_at = min(e.execution_time for e in ledger.executions)
        closed_at = max(e.execution_time for e in ledger.executions) if is_closed else None

        # Calculate costs
        # For multi-leg strategies, we need to distinguish between:
        # - Opening executions (initial position entry)
        # - Closing executions (position exit)

        if is_closed:
            # Trade is closed - all executions contributed to opening or closing
            opening_cost = sum(
                abs(e.net_amount) for e in ledger.executions
                if e.side == "BOT"
            )
            closing_proceeds = sum(
                abs(e.net_amount) for e in ledger.executions
                if e.side == "SLD"
            )
        else:
            # Trade is still open - calculate net opening cost
            # For spreads: BOT (long leg) - SLD (short leg credit)
            # For single legs: just the BOT cost
            bot_cost = sum(
                abs(e.net_amount) for e in ledger.executions
                if e.side == "BOT"
            )
            sld_credit = sum(
                abs(e.net_amount) for e in ledger.executions
                if e.side == "SLD"
            )

            # Net opening cost = cost paid - credit received
            opening_cost = bot_cost - sld_credit
            closing_proceeds = Decimal("0.00")

        total_commission = sum(e.commission for e in ledger.executions)

        return {
            "underlying": ledger.underlying,
            "strategy_type": strategy,
            "status": "CLOSED" if is_closed else "OPEN",
            "opened_at": opened_at,
            "closed_at": closed_at,
            "realized_pnl": ledger.get_pnl() if is_closed else Decimal("0.00"),
            "unrealized_pnl": Decimal("0.00"),  # Requires live market data to calculate
            "total_pnl": ledger.get_pnl() if is_closed else Decimal("0.00"),
            "opening_cost": opening_cost,
            "closing_proceeds": closing_proceeds,
            "total_commission": total_commission,
            "num_legs": len(legs),
            "num_executions": len(ledger.executions),
            "executions": ledger.executions,  # Include executions for trade_id assignment
        }

    def _classify_strategy(self, legs: dict) -> str:
        """Classify option strategy based on leg structure.

        Args:
            legs: Dictionary of position legs

        Returns:
            Strategy classification string
        """
        if not legs:
            return "UNKNOWN"

        num_legs = len(legs)
        open_legs = {k: v for k, v in legs.items() if v["quantity"] != 0}

        if num_legs == 1:
            leg_key = list(legs.keys())[0]
            leg_data = list(legs.values())[0]
            qty = leg_data["quantity"]

            # Check if it's stock or option
            if leg_key == "STK":
                return "Long Stock" if qty > 0 else "Short Stock"

            # Parse option leg key: "YYYYMMDD_strike_type"
            parts = leg_key.split("_")
            if len(parts) == 3:
                option_type = parts[2]  # "C" or "P"
                is_long = qty > 0

                if option_type == "C":
                    return "Long Call" if is_long else "Short Call"
                elif option_type == "P":
                    return "Long Put" if is_long else "Short Put"

            return "Single"

        if num_legs == 2:
            # Check for vertical spread
            leg_list = list(open_legs.items())
            if len(leg_list) == 2:
                leg1_key, leg1_data = leg_list[0]
                leg2_key, leg2_data = leg_list[1]

                parts1 = leg1_key.split("_")
                parts2 = leg2_key.split("_")

                if len(parts1) == 3 and len(parts2) == 3:
                    exp1, strike1_str, right1 = parts1
                    exp2, strike2_str, right2 = parts2

                    # Same expiry and type = vertical spread
                    if exp1 == exp2 and right1 == right2:
                        try:
                            strike1 = float(strike1_str)
                            strike2 = float(strike2_str)
                            qty1 = leg1_data["quantity"]
                            qty2 = leg2_data["quantity"]

                            # Sort by strike
                            if strike1 > strike2:
                                strike1, strike2 = strike2, strike1
                                qty1, qty2 = qty2, qty1

                            # Now strike1 is lower, strike2 is higher
                            # qty > 0 = long, qty < 0 = short
                            lower_is_long = qty1 > 0
                            upper_is_long = qty2 > 0

                            if right1 == "C":
                                # Call spreads
                                if lower_is_long and not upper_is_long:
                                    return "Bull Call Spread"
                                elif not lower_is_long and upper_is_long:
                                    return "Bear Call Spread"
                            else:
                                # Put spreads
                                # Bull Put Spread: Long lower put + Short higher put (credit)
                                # Bear Put Spread: Short lower put + Long higher put (debit)
                                if lower_is_long and not upper_is_long:
                                    return "Bull Put Spread"
                                elif not lower_is_long and upper_is_long:
                                    return "Bear Put Spread"
                        except (ValueError, KeyError):
                            pass

                        # Fallback if can't determine direction
                        if right1 == "C":
                            return "Vertical Call Spread"
                        else:
                            return "Vertical Put Spread"

            return "Two-Leg"

        if num_legs == 3:
            # Check for butterfly
            leg_list = sorted(
                open_legs.items(),
                key=lambda x: float(x[0].split("_")[1]) if len(x[0].split("_")) > 1 else 0
            )
            quantities = [abs(v["quantity"]) for k, v in leg_list]

            if len(quantities) == 3 and quantities[1] == 2 * quantities[0] == 2 * quantities[2]:
                return "Butterfly"

            return "Three-Leg"

        if num_legs == 4:
            # Check for iron condor
            calls = [k for k in open_legs.keys() if k.endswith("_C")]
            puts = [k for k in open_legs.keys() if k.endswith("_P")]

            if len(calls) == 2 and len(puts) == 2:
                return "Iron Condor"

            return "Four-Leg"

        return f"{num_legs}-Leg Complex"

    async def _create_or_update_trade(self, trade_data: dict) -> Optional[Trade]:
        """Create or update a trade record.

        Args:
            trade_data: Trade data dictionary

        Returns:
            Trade model or None
        """
        # For now, always create new trades
        # In Phase 2, we can add logic to update existing trades
        trade = Trade(**trade_data)
        self.session.add(trade)
        await self.session.flush()
        return trade

    async def reprocess_all_executions(self) -> dict:
        """Reprocess all executions using the improved state machine algorithm.

        This method:
        1. Deletes all existing trades
        2. Clears trade_id from all executions
        3. Reprocesses all executions using the position state machine
        4. Links rolls within the same day

        Returns:
            Dict with processing statistics
        """
        stats = {
            "trades_deleted": 0,
            "executions_processed": 0,
            "trades_created": 0,
            "rolls_detected": 0,
        }

        # Step 1: Delete all existing trades
        delete_stmt = delete(Trade)
        await self.session.execute(delete_stmt)

        # Step 2: Clear trade_id from all executions
        stmt = select(Execution)
        result = await self.session.execute(stmt)
        executions = list(result.scalars().all())

        for exec in executions:
            exec.trade_id = None

        await self.session.flush()
        stats["executions_processed"] = len(executions)

        # Step 3: Group by underlying
        by_underlying = defaultdict(list)
        for exec in executions:
            by_underlying[exec.underlying].append(exec)

        # Step 4: Process each underlying with state machine
        all_trades: list[Trade] = []
        roll_chain_counter = 1

        for underlying, execs in by_underlying.items():
            # Use the new position state machine
            state_machine = PositionStateMachine(underlying)
            trade_groups = state_machine.process_executions(execs)

            # Convert trade groups to Trade models
            prev_trade: Optional[Trade] = None
            current_chain_id: Optional[int] = None

            for group in trade_groups:
                trade = await self._create_trade_from_group(group)
                if trade:
                    all_trades.append(trade)
                    stats["trades_created"] += 1

                    # Handle assignment linking (option -> stock)
                    if group.is_assignment and prev_trade:
                        trade.is_assignment = True
                        trade.assigned_from_trade_id = prev_trade.id
                        # Don't mark as roll - assignments are distinct from rolls
                        current_chain_id = None

                    # Handle roll linking (option -> option)
                    elif group.roll_type == "ROLL" and prev_trade:
                        trade.is_roll = True
                        trade.rolled_from_trade_id = prev_trade.id
                        prev_trade.rolled_to_trade_id = trade.id

                        # Use same chain ID or create new one
                        if current_chain_id is None:
                            current_chain_id = roll_chain_counter
                            roll_chain_counter += 1
                            prev_trade.roll_chain_id = current_chain_id

                        trade.roll_chain_id = current_chain_id
                        stats["rolls_detected"] += 1
                    else:
                        # Reset chain for non-rolls
                        current_chain_id = None

                    prev_trade = trade

        await self.session.commit()
        return stats

    async def _create_trade_from_group(self, group: TradeGroup) -> Optional[Trade]:
        """Create a Trade model from a TradeGroup.

        Args:
            group: TradeGroup from state machine

        Returns:
            Created Trade model
        """
        if not group.executions:
            return None

        # Calculate metrics
        executions = group.executions

        # Timestamps
        opened_at = min(e.execution_time for e in executions)
        closed_at = max(e.execution_time for e in executions) if group.status == "CLOSED" else None

        # Classify strategy based on opening position
        strategy_type = classify_strategy_from_opening(group.opening_position)

        # Calculate costs and P&L
        total_commission = sum(e.commission for e in executions)

        if group.status == "CLOSED":
            opening_cost = sum(abs(e.net_amount) for e in executions if e.side == "BOT")
            closing_proceeds = sum(abs(e.net_amount) for e in executions if e.side == "SLD")
            realized_pnl = closing_proceeds - opening_cost - total_commission
        else:
            bot_cost = sum(abs(e.net_amount) for e in executions if e.side == "BOT")
            sld_credit = sum(abs(e.net_amount) for e in executions if e.side == "SLD")
            opening_cost = bot_cost - sld_credit
            closing_proceeds = Decimal("0.00")
            realized_pnl = Decimal("0.00")

        # Count unique legs
        leg_keys = set()
        for exec in executions:
            if exec.security_type == "OPT":
                expiry = exec.expiration.strftime("%Y%m%d") if exec.expiration else ""
                leg_key = f"{expiry}_{exec.strike}_{exec.option_type}"
            else:
                leg_key = "STK"
            leg_keys.add(leg_key)

        # Create trade
        # Note: is_roll should not be set for assignments
        trade = Trade(
            underlying=group.underlying,
            strategy_type=strategy_type,
            status=group.status,
            opened_at=opened_at,
            closed_at=closed_at,
            realized_pnl=realized_pnl,
            unrealized_pnl=Decimal("0.00"),
            total_pnl=realized_pnl,
            opening_cost=opening_cost,
            closing_proceeds=closing_proceeds,
            total_commission=total_commission,
            num_legs=len(leg_keys),
            num_executions=len(executions),
            is_roll=group.roll_type == "ROLL" and not group.is_assignment,
            is_assignment=group.is_assignment,
        )

        self.session.add(trade)
        await self.session.flush()

        # Link executions to trade
        for exec in executions:
            exec.trade_id = trade.id

        return trade
