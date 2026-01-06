"""Trade grouping service - converts executions into trades with strategy classification.

This module uses a position state machine approach to correctly identify trade boundaries:
1. Tracks cumulative position state across all executions
2. Detects when positions open, close, roll, or adjust
3. Groups executions into logical trades with proper strategy classification
4. Detects stock splits that may affect position tracking
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import Date, case, cast, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.models.execution import Execution
from trading_journal.models.trade import Trade
from trading_journal.services.position_state_machine import (
    LegPosition,
    PositionStateMachine,
    TradeGroup,
    classify_strategy_from_opening,
)
from trading_journal.services.split_detection_service import SplitDetectionService

logger = logging.getLogger(__name__)


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
            expiry = self._normalize_expiration_date(execution.expiration)
            return f"{expiry}_{execution.strike}_{execution.option_type}"
        return "STK"

    def _normalize_expiration_date(self, expiration: datetime | None) -> str:
        """Normalize expiration datetime to YYYYMMDD string.

        See TradeGroupingService._normalize_expiration_date for details.
        """
        if not expiration:
            return ""

        utc_hour = expiration.hour
        if utc_hour >= 20:
            expiration = expiration + timedelta(days=1)

        return expiration.strftime("%Y%m%d")

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
        underlying: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
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

        # Fetch executions (excluding forex/cash/combo bags)
        # BAG = IBKR combo order net debit/credit (individual legs are separate executions)
        stmt = select(Execution).where(
            Execution.security_type.notin_(["CASH", "FOREX", "FX", "BAG"]),
            ~Execution.underlying.contains("."),  # Exclude currency pairs like USD.ILS
        ).order_by(
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

        IMPORTANT: Executions with different expirations are NEVER grouped together,
        even if they occur within the time window. Different expirations indicate
        different strategies (e.g., a Long Call LEAP vs a short-term put spread).

        Args:
            executions: Sorted list of executions

        Returns:
            List of execution groups
        """
        if not executions:
            return []

        time_groups = []
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
                    time_groups.append(current_group)
                    current_group = [exec]
                    group_start_time = exec.execution_time

        # Add final group
        if current_group:
            time_groups.append(current_group)

        # Now split each time group by expiration to separate different strategies
        # Executions with different expirations should NOT be grouped together
        final_groups = []
        for time_group in time_groups:
            expiry_subgroups = self._split_group_by_expiration(time_group)
            final_groups.extend(expiry_subgroups)

        return final_groups

    def _split_group_by_expiration(self, executions: list[Execution]) -> list[list[Execution]]:
        """Split a group of executions by expiration date.

        Executions with different expirations are clearly different strategies
        and should not be grouped together. For example:
        - A Jan 2027 LEAP and a Jan 2026 put spread executed at the same time
          should be treated as separate trades.

        Stock executions (no expiration) are kept separate from options.

        Args:
            executions: List of executions to split

        Returns:
            List of execution groups, one per expiration
        """
        if len(executions) <= 1:
            return [executions] if executions else []

        # Group by normalized expiration
        by_expiry: dict[str, list[Execution]] = {}

        for exec in executions:
            if exec.security_type == "OPT" and exec.expiration:
                # Normalize expiration to date string
                expiry_key = self._normalize_expiration_date(exec.expiration)
            elif exec.security_type == "STK":
                # Stock executions get their own key
                expiry_key = "STK"
            else:
                # Other types (shouldn't happen often)
                expiry_key = "OTHER"

            if expiry_key not in by_expiry:
                by_expiry[expiry_key] = []
            by_expiry[expiry_key].append(exec)

        # Return as list of groups, sorted by expiry for consistency
        return [by_expiry[key] for key in sorted(by_expiry.keys())]

    def _get_leg_key_from_exec(self, execution: Execution) -> str:
        """Get leg key from execution (same as TradeLedger.get_leg_key)."""
        if execution.security_type == "OPT":
            expiry = self._normalize_expiration_date(execution.expiration)
            return f"{expiry}_{execution.strike}_{execution.option_type}"
        return "STK"

    def _normalize_expiration_date(self, expiration: datetime | None) -> str:
        """Normalize expiration datetime to YYYYMMDD string.

        Options expire on a specific calendar date, but may be stored with
        different times depending on the source timezone. This method
        normalizes to the intended expiration date.

        For example:
        - 2025-12-19 00:00:00+02:00 (Israel) = 2025-12-18 22:00:00 UTC
        - 2025-12-19 02:00:00+02:00 (Israel) = 2025-12-19 00:00:00 UTC

        Both refer to options expiring on Dec 19, so we need to normalize.
        We detect this by checking if the UTC time is after 20:00 (8 PM),
        which indicates midnight in a timezone east of UTC like Israel (+2).

        Args:
            expiration: Expiration datetime

        Returns:
            Normalized date string in YYYYMMDD format
        """
        if not expiration:
            return ""

        # Get the UTC time components
        utc_hour = expiration.hour  # Already in UTC if stored with timezone

        # If UTC time is 20:00 or later (8 PM+), it's likely midnight or later
        # in an eastern timezone (like Israel +2 or +3), so add a day
        if utc_hour >= 20:
            expiration = expiration + timedelta(days=1)

        return expiration.strftime("%Y%m%d")

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

    async def _save_trade_from_ledger(self, ledger: TradeLedger, is_closed: bool) -> Trade | None:
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
            "greeks_pending": True,  # Greeks will be fetched by scheduler
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

    async def _create_or_update_trade(self, trade_data: dict) -> Trade | None:
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

    async def _process_underlying_with_existing_trades(
        self, underlying: str, new_executions: list[Execution]
    ) -> tuple[int, int, int]:
        """Process new executions for an underlying, loading existing open trades first.

        This method:
        1. Loads existing OPEN trades for the underlying from the database
        2. Initializes the state machine with those trades' positions
        3. Processes new executions, matching closes to existing trades
        4. Updates existing trades that received closing executions
        5. Creates new trades for new positions

        Args:
            underlying: The underlying symbol
            new_executions: List of new executions to process

        Returns:
            Tuple of (trades_updated, trades_created, trades_closed)
        """
        trades_updated = 0
        trades_created = 0
        trades_closed = 0

        # Load existing OPEN trades for this underlying with their executions
        from sqlalchemy.orm import selectinload
        stmt = select(Trade).where(
            Trade.underlying == underlying,
            Trade.status == "OPEN",
        ).options(selectinload(Trade.executions))

        result = await self.session.execute(stmt)
        existing_open_trades = list(result.scalars().all())

        if not existing_open_trades:
            # No existing open trades - process normally
            state_machine = PositionStateMachine(underlying)
            trade_groups = state_machine.process_executions(new_executions)

            for group in trade_groups:
                trade = await self._create_trade_from_group(group)
                if trade:
                    trades_created += 1
            return trades_updated, trades_created, trades_closed

        # Build a mapping of leg_key sets to existing trades
        # and initialize cumulative position from existing trade executions
        state_machine = PositionStateMachine(underlying)

        for existing_trade in existing_open_trades:
            # Get leg keys from existing trade's executions
            leg_keys = set()
            for exec in existing_trade.executions:
                leg_key = state_machine.get_leg_key(exec)
                leg_keys.add(leg_key)

            # Create a TradeGroup to represent the existing trade
            trade_group = TradeGroup(underlying=underlying)
            trade_group.status = "OPEN"

            # Add all existing executions to the trade group
            for exec in existing_trade.executions:
                trade_group.add_execution(exec)
                leg_key = state_machine.get_leg_key(exec)
                # Calculate opening position from open executions
                if exec.open_close_indicator == 'O':
                    delta = int(exec.quantity) if exec.side == "BOT" else -int(exec.quantity)
                    trade_group.opening_position[leg_key] = (
                        trade_group.opening_position.get(leg_key, 0) + delta
                    )

            # Store reference to the DB trade for later updates
            trade_group.db_trade_id = existing_trade.id

            # Add to state machine's open trades
            frozen_legs = frozenset(leg_keys) if leg_keys else frozenset(["unknown"])
            state_machine.open_trades[frozen_legs] = trade_group

            # Initialize cumulative position from existing trade executions
            for exec in existing_trade.executions:
                leg_key = state_machine.get_leg_key(exec)
                if leg_key not in state_machine.position:
                    state_machine.position[leg_key] = LegPosition(leg_key=leg_key)
                delta = int(exec.quantity) if exec.side == "BOT" else -int(exec.quantity)
                # For closes, delta reduces position toward zero
                if exec.open_close_indicator == 'C':
                    current = state_machine.position[leg_key].quantity
                    if current > 0:
                        state_machine.position[leg_key].quantity = max(0, current + delta)
                    elif current < 0:
                        state_machine.position[leg_key].quantity = min(0, current + delta)
                else:
                    state_machine.position[leg_key].quantity += delta

        # Now process new executions - the state machine knows about existing trades
        trade_groups = state_machine.process_executions(new_executions)

        # Process results - some may be updates to existing trades, some new
        for group in trade_groups:
            # Check if this group has a reference to an existing DB trade
            db_trade_id = getattr(group, 'db_trade_id', None)

            if db_trade_id:
                # Update existing trade with new executions
                existing_trade = await self.session.get(Trade, db_trade_id)
                if existing_trade:
                    # Add new executions to the existing trade
                    new_exec_count = 0
                    for exec in group.executions:
                        if exec.trade_id is None:
                            exec.trade_id = db_trade_id
                            new_exec_count += 1

                    if new_exec_count > 0:
                        # Recalculate trade fields based on all executions
                        await self._update_trade_from_executions(existing_trade, group)
                        trades_updated += 1

                        if group.status == "CLOSED":
                            trades_closed += 1
            else:
                # New trade - only if it has new executions
                has_new_execs = any(e.trade_id is None for e in group.executions)
                if has_new_execs:
                    trade = await self._create_trade_from_group(group)
                    if trade:
                        trades_created += 1
                        if group.status == "CLOSED":
                            trades_closed += 1

        return trades_updated, trades_created, trades_closed

    async def _update_trade_from_executions(
        self, trade: Trade, group: TradeGroup
    ) -> None:
        """Update an existing trade's calculated fields after adding new executions.

        Args:
            trade: The existing Trade model to update
            group: The TradeGroup with all executions (existing + new)
        """
        executions = group.executions

        # Recalculate all fields
        trade.status = group.status
        trade.num_executions = len(executions)

        # Get unique legs
        legs = set()
        for e in executions:
            if e.security_type == "OPT":
                legs.add(f"{e.strike}_{e.option_type}_{e.expiration}")
            else:
                legs.add("STK")
        trade.num_legs = len(legs)

        # Calculate quantity from opening executions
        opening_qty = sum(
            int(e.quantity) for e in executions if e.open_close_indicator == 'O'
        )
        trade.quantity = opening_qty or sum(int(e.quantity) for e in executions) // 2

        # Timestamps
        trade.opened_at = min(e.execution_time for e in executions)
        if group.status == "CLOSED":
            trade.closed_at = max(e.execution_time for e in executions)

        # Calculate strikes
        strikes = sorted([float(e.strike) for e in executions if e.strike])
        if strikes:
            trade.strike_low = strikes[0]
            trade.strike_high = strikes[-1] if len(strikes) > 1 else None

        # Expiration
        expirations = [e.expiration for e in executions if e.expiration]
        if expirations:
            trade.expiration = min(expirations)

        # P&L calculation for closed trades
        if group.status == "CLOSED":
            total_commission = sum(e.commission or 0 for e in executions)
            opening_cost = sum(
                abs(e.net_amount) for e in executions if e.side == "BOT"
            )
            closing_proceeds = sum(
                abs(e.net_amount) for e in executions if e.side == "SLD"
            )
            trade.realized_pnl = closing_proceeds - opening_cost - total_commission
            trade.commission = total_commission

    async def process_new_executions(self) -> dict:
        """Process only unassigned executions into trades.

        This method processes executions that have trade_id = NULL,
        creating new trades or adding to existing ones.

        IMPORTANT: Before processing new executions for each underlying,
        we load existing OPEN trades to properly match closing executions
        to their corresponding opening trades.

        Returns:
            Dict with processing statistics
        """
        stats = {
            "executions_processed": 0,
            "trades_created": 0,
            "trades_updated": 0,
            "trades_closed": 0,
        }

        # Fetch only unassigned executions (trade_id IS NULL), excluding forex/cash/bags
        stmt = select(Execution).where(
            Execution.trade_id.is_(None),
            Execution.security_type.notin_(["CASH", "FOREX", "FX", "BAG"]),
            ~Execution.underlying.contains("."),  # Exclude currency pairs like USD.ILS
        ).order_by(
            Execution.execution_time,
            Execution.underlying,
        )

        result = await self.session.execute(stmt)
        executions = list(result.scalars().all())
        stats["executions_processed"] = len(executions)

        if not executions:
            return stats

        # Group by underlying
        by_underlying = defaultdict(list)
        for exec in executions:
            by_underlying[exec.underlying].append(exec)

        # Process each underlying - load existing open trades first
        for underlying, new_execs in by_underlying.items():
            updated, created, closed = await self._process_underlying_with_existing_trades(
                underlying, new_execs
            )
            stats["trades_updated"] += updated
            stats["trades_created"] += created
            stats["trades_closed"] += closed

        await self.session.commit()

        # Auto-fetch Greeks for newly created option trades
        # DISABLED: Rate limiting makes this too slow. Revisit approach.
        # if stats["trades_created"] > 0:
        #     greeks_stats = await self.fetch_greeks_for_pending_trades()
        #     stats["greeks_fetched"] = greeks_stats["trades_succeeded"]
        #     stats["greeks_failed"] = greeks_stats["trades_failed"]

        return stats

    async def reprocess_all_executions(self) -> dict:
        """Reprocess all executions using the improved state machine algorithm.

        This method:
        1. Normalizes stock splits in executions
        2. Deletes all existing trades
        3. Clears trade_id from all executions
        4. Reprocesses all executions using the position state machine
        5. Links rolls within the same day
        6. Assigns orphaned fractional shares to recent trades
        7. Assigns currency conversions to a special excluded trade

        Returns:
            Dict with processing statistics
        """
        stats = {
            "trades_deleted": 0,
            "executions_processed": 0,
            "trades_created": 0,
            "rolls_detected": 0,
            "splits_normalized": 0,
            "fractional_shares_assigned": 0,
            "currency_conversions_excluded": 0,
            "tags_restored": 0,
        }

        # Step 0: Preserve tag associations before deleting trades
        # Map execution_ids (as frozenset) -> list of tag_ids
        tag_mapping = await self._save_tag_associations()
        logger.info(f"Saved tag associations for {len(tag_mapping)} trades")

        # Step 0.5: Preserve Greeks data before deleting trades
        greeks_mapping = await self._save_greeks_data()
        logger.info(f"Saved Greeks data for {len(greeks_mapping)} trades")

        # Step 1: Normalize stock splits before processing
        # TODO: Fix overflow issues with currency trades and high-value splits
        # from trading_journal.services.split_normalization_service import (
        #     SplitNormalizationService,
        # )
        # split_service = SplitNormalizationService(self.session)
        # split_stats = await split_service.normalize_all_splits()
        # stats["splits_normalized"] = split_stats["executions_normalized"]
        stats["splits_normalized"] = 0  # Temporarily disabled

        # Step 2: Delete all existing trades (CASCADE will delete trade_tags)
        delete_stmt = delete(Trade)
        await self.session.execute(delete_stmt)

        # Step 3: Clear trade_id from all executions
        clear_stmt = select(Execution)
        clear_result = await self.session.execute(clear_stmt)
        for exec in clear_result.scalars().all():
            exec.trade_id = None
        await self.session.flush()

        # Step 4: Handle currency conversions - assign to special excluded trade
        currency_excluded = await self._exclude_currency_conversions()
        stats["currency_conversions_excluded"] = currency_excluded

        # Step 5: Get tradeable executions (excluding forex/cash/currency pairs/bags)
        stmt = select(Execution).where(
            Execution.trade_id.is_(None),  # Not already assigned
            Execution.security_type.notin_(["CASH", "FOREX", "FX", "BAG"]),
            ~Execution.underlying.contains("."),  # Exclude currency pairs like USD.ILS
        )
        result = await self.session.execute(stmt)
        executions = list(result.scalars().all())
        stats["executions_processed"] = len(executions)

        # Step 6: Group by underlying
        by_underlying = defaultdict(list)
        for exec in executions:
            by_underlying[exec.underlying].append(exec)

        # Step 7: Process each underlying with state machine
        all_trades: list[Trade] = []
        roll_chain_counter = 1

        for underlying, execs in by_underlying.items():
            # Use the new position state machine
            state_machine = PositionStateMachine(underlying)
            trade_groups = state_machine.process_executions(execs)

            # Convert trade groups to Trade models
            prev_trade: Trade | None = None
            current_chain_id: int | None = None

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

        await self.session.flush()

        # Step 7.5: Link assignments by timestamp matching
        # This handles cases where prev_trade wasn't the correct option trade
        assignments_linked = await self._link_assignments_by_timestamp()
        stats["assignments_linked"] = assignments_linked
        logger.info(f"Linked {assignments_linked} assignment trades")

        # Step 7.6: Close trades with offsetting residual positions
        # When executions can't be perfectly split, we may have trades with
        # offsetting positions (+N and -N) that should net to 0
        offsetting_closed = await self._close_offsetting_residual_trades()
        stats["offsetting_trades_closed"] = offsetting_closed
        logger.info(f"Closed {offsetting_closed} trades with offsetting residual positions")

        # Step 8: Assign orphaned fractional shares to recent trades
        fractional_assigned = await self._assign_orphaned_fractional_shares()
        stats["fractional_shares_assigned"] = fractional_assigned

        # Step 8.5: Restore tag associations to newly created trades
        tags_restored = await self._restore_tag_associations(tag_mapping)
        stats["tags_restored"] = tags_restored
        logger.info(f"Restored tags to {tags_restored} trades")

        # Step 8.6: Restore Greeks data to newly created trades
        greeks_restored = await self._restore_greeks_data(greeks_mapping)
        stats["greeks_restored"] = greeks_restored
        logger.info(f"Restored Greeks to {greeks_restored} trades")

        await self.session.commit()

        # Run split detection for stock trades
        split_report = await self._check_for_stock_splits()
        stats["split_issues_detected"] = split_report["issues_found"]
        stats["split_issues_auto_fixed"] = split_report.get("auto_fixed", 0)

        # Step 9: Mark expired options as EXPIRED
        from trading_journal.services.trade_service import TradeService
        trade_service = TradeService(self.session)
        expired_stats = await trade_service.mark_expired_trades()
        stats["expired_trades_marked"] = expired_stats["trades_marked"]

        # Step 10: Auto-fetch Greeks for newly created option trades
        # DISABLED: Rate limiting makes this too slow. Revisit approach.
        # greeks_stats = await self.fetch_greeks_for_pending_trades()
        # stats["greeks_fetched"] = greeks_stats["trades_succeeded"]
        # stats["greeks_failed"] = greeks_stats["trades_failed"]
        stats["greeks_fetched"] = 0
        stats["greeks_failed"] = 0

        return stats

    async def _assign_orphaned_fractional_shares(self) -> int:
        """Assign orphaned fractional share executions to recent trades.

        Fractional shares (quantity < 1) often occur as price improvement
        rebates from IBKR and arrive slightly after the main trade closes.
        This method finds these orphans and assigns them to the most recent
        trade for that underlying.

        Returns:
            Number of fractional shares assigned
        """
        # Find orphaned fractional stock executions
        stmt = select(Execution).where(
            Execution.trade_id.is_(None),
            Execution.security_type == "STK",
            Execution.quantity < 1,
        ).order_by(Execution.underlying, Execution.execution_time)

        result = await self.session.execute(stmt)
        fractional_orphans = list(result.scalars().all())

        if not fractional_orphans:
            return 0

        assigned_count = 0

        for orphan in fractional_orphans:
            # Find the most recent trade for this underlying that closed
            # within 30 minutes before or after this execution
            time_window = timedelta(minutes=30)
            earliest_time = orphan.execution_time - time_window
            latest_time = orphan.execution_time + time_window

            # Look for a trade that:
            # 1. Is for the same underlying
            # 2. Is a stock trade
            # 3. Was closed within the time window
            trade_stmt = select(Trade).where(
                Trade.underlying == orphan.underlying,
                Trade.strategy_type.in_(["Long Stock", "Short Stock"]),
                Trade.closed_at.isnot(None),
                Trade.closed_at >= earliest_time,
                Trade.closed_at <= latest_time,
            ).order_by(
                # Prefer the trade closest in time
                Trade.closed_at.desc()
            ).limit(1)

            trade_result = await self.session.execute(trade_stmt)
            matching_trade = trade_result.scalar_one_or_none()

            if matching_trade:
                # Assign fractional share to this trade
                orphan.trade_id = matching_trade.id
                matching_trade.num_executions += 1
                assigned_count += 1
            else:
                # Try to find any recent trade for this underlying (within 30 min)
                # even if it's still open
                trade_stmt = select(Trade).where(
                    Trade.underlying == orphan.underlying,
                    Trade.strategy_type.in_(["Long Stock", "Short Stock"]),
                    Trade.opened_at <= orphan.execution_time,
                ).order_by(
                    Trade.opened_at.desc()
                ).limit(1)

                trade_result = await self.session.execute(trade_stmt)
                matching_trade = trade_result.scalar_one_or_none()

                if matching_trade:
                    orphan.trade_id = matching_trade.id
                    matching_trade.num_executions += 1
                    assigned_count += 1

        return assigned_count

    async def _exclude_currency_conversions(self) -> int:
        """Create a special trade for currency conversion executions.

        Currency pairs (e.g., USD.ILS, EUR.USD) are forex transactions
        that shouldn't be matched as securities trades. This method
        creates a single "Currency Conversion" trade to hold them,
        preventing them from appearing as orphans.

        Returns:
            Number of currency conversion executions assigned
        """
        # Find currency conversion executions (those with "." in underlying)
        stmt = select(Execution).where(
            Execution.underlying.contains("."),
        )
        result = await self.session.execute(stmt)
        currency_execs = list(result.scalars().all())

        if not currency_execs:
            return 0

        # Calculate aggregates
        total_amount = sum(e.net_amount for e in currency_execs)
        total_commission = sum(e.commission for e in currency_execs)
        min_time = min(e.execution_time for e in currency_execs)
        max_time = max(e.execution_time for e in currency_execs)

        # Create special "Currency Conversion" trade
        currency_trade = Trade(
            underlying="FOREX",
            strategy_type="Currency Conversion",
            status="CLOSED",
            opened_at=min_time,
            closed_at=max_time,
            realized_pnl=Decimal("0.00"),
            unrealized_pnl=Decimal("0.00"),
            total_pnl=Decimal("0.00"),
            opening_cost=abs(total_amount) if total_amount < 0 else Decimal("0.00"),
            closing_proceeds=abs(total_amount) if total_amount > 0 else Decimal("0.00"),
            total_commission=total_commission,
            num_legs=1,
            num_executions=len(currency_execs),
        )
        self.session.add(currency_trade)
        await self.session.flush()

        # Assign all currency executions to this trade
        for exec in currency_execs:
            exec.trade_id = currency_trade.id

        return len(currency_execs)

    async def _link_assignments_by_timestamp(self) -> int:
        """Link assignment trades to their source option trades by timestamp.

        When an option is assigned/exercised:
        - The option is closed (often at $0)
        - Stock is acquired (put assignment) or delivered (call assignment)
        - Both happen at the same timestamp

        This method finds stock trades marked as assignments and links them
        to the option trade that closed at the same time.

        For put assignments (Short Put -> Long Stock):
        - Adjusted cost basis = Strike price - Premium received
        - opening_cost is adjusted to reflect the net cost

        For call assignments (Long Call -> Short Stock or Short Call -> delivered stock):
        - Similar adjustment for premium paid/received

        Returns:
            Number of assignments linked
        """
        linked_count = 0

        # Find all stock trades that might be assignments
        # Look for Long Stock trades that opened at the same time an option closed
        stock_stmt = select(Trade).where(
            Trade.strategy_type.in_(["Long Stock", "Short Stock"]),
            Trade.status == "OPEN",
        )
        result = await self.session.execute(stock_stmt)
        stock_trades = list(result.scalars().all())

        for stock_trade in stock_trades:
            # Skip if already linked
            if stock_trade.assigned_from_trade_id is not None:
                continue

            # Find option trades for the same underlying that closed at the same time
            option_stmt = select(Trade).where(
                Trade.underlying == stock_trade.underlying,
                Trade.strategy_type.in_(["Short Put", "Long Put", "Short Call", "Long Call"]),
                Trade.status == "CLOSED",
                Trade.closed_at == stock_trade.opened_at,  # Same timestamp
            )
            option_result = await self.session.execute(option_stmt)
            option_trades = list(option_result.scalars().all())

            if option_trades:
                # Link to the first matching option trade
                option_trade = option_trades[0]
                stock_trade.is_assignment = True
                stock_trade.assigned_from_trade_id = option_trade.id

                # Adjust cost basis based on option premium
                # For Short Put assignment: cost basis = strike - premium received
                # The option trade's closing_proceeds contains the premium received (SLD)
                # and opening_cost contains the cost to close (BOT at $0)
                if option_trade.strategy_type == "Short Put":
                    # Premium received = closing_proceeds (what we got when we sold the put)
                    # For a short put, closing_proceeds is the premium received
                    premium_received = option_trade.closing_proceeds
                    original_cost = stock_trade.opening_cost
                    adjusted_cost = original_cost - premium_received
                    stock_trade.opening_cost = adjusted_cost

                    logger.info(
                        f"Adjusted assignment cost basis for {stock_trade.underlying}: "
                        f"${original_cost:.2f} - ${premium_received:.2f} premium = ${adjusted_cost:.2f}"
                    )
                elif option_trade.strategy_type == "Long Put":
                    # For exercising a long put, we paid premium
                    premium_paid = option_trade.opening_cost
                    original_cost = stock_trade.opening_cost
                    # Actually for long put exercise, we're selling stock, not buying
                    # This case is less common, skip for now
                    pass
                elif option_trade.strategy_type == "Short Call":
                    # For short call assignment, we deliver stock and receive strike
                    # Premium received adds to our proceeds
                    premium_received = option_trade.closing_proceeds
                    # This would affect closing_proceeds for the stock trade
                    pass
                elif option_trade.strategy_type == "Long Call":
                    # For long call exercise, we pay strike to receive stock
                    # Premium paid increases our cost basis
                    premium_paid = option_trade.opening_cost
                    original_cost = stock_trade.opening_cost
                    adjusted_cost = original_cost + premium_paid
                    stock_trade.opening_cost = adjusted_cost

                    logger.info(
                        f"Adjusted assignment cost basis for {stock_trade.underlying}: "
                        f"${original_cost:.2f} + ${premium_paid:.2f} premium = ${adjusted_cost:.2f}"
                    )

                linked_count += 1
                logger.info(
                    f"Linked assignment: {stock_trade.underlying} stock trade {stock_trade.id} "
                    f"from option trade {option_trade.id} ({option_trade.strategy_type})"
                )

        return linked_count

    async def _close_offsetting_residual_trades(self) -> int:
        """Close trades with residual positions that offset to zero.

        When closing executions can't be perfectly split across multiple trades
        (because individual executions can't be split), we may end up with:
        - Trade A: +N at leg X (over-closed)
        - Trade B: -N at leg X (not fully closed)

        If the total position for a leg across all trades is 0, we should close
        any OPEN trades that only have residual positions in legs where the
        overall position is 0.

        Returns:
            Number of trades closed
        """
        closed_count = 0

        # Find all legs where total position across all executions is 0
        # but there are still OPEN trades with that leg
        # Note: Use cast to DATE to handle timezone/DST differences in expiration timestamps
        exp_date = cast(Execution.expiration, Date)
        leg_totals_stmt = (
            select(
                Execution.underlying,
                Execution.strike,
                exp_date.label("exp_date"),
                Execution.option_type,
                func.sum(
                    case(
                        (Execution.side == "BOT", Execution.quantity),
                        else_=-Execution.quantity
                    )
                ).label("net_qty")
            )
            .where(Execution.security_type == "OPT")
            .group_by(
                Execution.underlying,
                Execution.strike,
                exp_date,
                Execution.option_type
            )
            .having(
                func.sum(
                    case(
                        (Execution.side == "BOT", Execution.quantity),
                        else_=-Execution.quantity
                    )
                ) == 0
            )
        )

        result = await self.session.execute(leg_totals_stmt)
        zero_legs = list(result.all())

        for leg in zero_legs:
            underlying, strike, expiration_date, option_type = leg[0], leg[1], leg[2], leg[3]

            # Find OPEN trades with this leg that have non-zero position
            # Use date comparison to handle timezone/DST differences
            trades_stmt = (
                select(Trade)
                .join(Execution, Execution.trade_id == Trade.id)
                .where(
                    Trade.status == "OPEN",
                    Execution.underlying == underlying,
                    Execution.strike == strike,
                    cast(Execution.expiration, Date) == expiration_date,
                    Execution.option_type == option_type
                )
                .distinct()
            )
            trades_result = await self.session.execute(trades_stmt)
            open_trades = list(trades_result.scalars().all())

            for trade in open_trades:
                # Check if ALL legs in this trade are either:
                # 1. At zero position, OR
                # 2. Part of a leg where overall position is 0
                all_legs_balanced = True

                # Get all legs in this trade (use date comparison for expiration)
                legs_stmt = (
                    select(
                        Execution.strike,
                        cast(Execution.expiration, Date).label("exp_date"),
                        Execution.option_type,
                        func.sum(
                            case(
                                (Execution.side == "BOT", Execution.quantity),
                                else_=-Execution.quantity
                            )
                        ).label("net_qty")
                    )
                    .where(
                        Execution.trade_id == trade.id,
                        Execution.security_type == "OPT"
                    )
                    .group_by(
                        Execution.strike,
                        cast(Execution.expiration, Date),
                        Execution.option_type
                    )
                )
                legs_result = await self.session.execute(legs_stmt)
                trade_legs = list(legs_result.all())

                for trade_leg in trade_legs:
                    t_strike, t_exp_date, t_type, t_net = trade_leg
                    if t_net != 0:
                        # Check if this leg's overall position is 0 (use date comparison)
                        overall_stmt = (
                            select(
                                func.sum(
                                    case(
                                        (Execution.side == "BOT", Execution.quantity),
                                        else_=-Execution.quantity
                                    )
                                )
                            )
                            .where(
                                Execution.underlying == trade.underlying,
                                Execution.strike == t_strike,
                                cast(Execution.expiration, Date) == t_exp_date,
                                Execution.option_type == t_type
                            )
                        )
                        overall_result = await self.session.execute(overall_stmt)
                        overall_net = overall_result.scalar()

                        if overall_net != 0:
                            all_legs_balanced = False
                            break

                if all_legs_balanced:
                    # Close this trade
                    trade.status = "CLOSED"
                    # Set closed_at to the latest execution time in the trade
                    exec_stmt = (
                        select(func.max(Execution.execution_time))
                        .where(Execution.trade_id == trade.id)
                    )
                    exec_result = await self.session.execute(exec_stmt)
                    latest_exec = exec_result.scalar()
                    if latest_exec:
                        trade.closed_at = latest_exec
                    closed_count += 1
                    logger.info(
                        f"Closed trade {trade.id} ({trade.underlying} {trade.strategy_type}) "
                        f"with offsetting residual position"
                    )

        return closed_count

    async def _check_for_stock_splits(self) -> dict:
        """Check for stock split issues and auto-fix where possible.

        Returns:
            Report of split issues found and fixed
        """
        split_service = SplitDetectionService(self.session)
        report = await split_service.check_and_report_splits()

        auto_fixed = 0
        for issue in report.get("details", []):
            if issue.get("recommendation") == "Position should be CLOSED":
                # Find the trade for this underlying that's still OPEN
                stmt = select(Trade).where(
                    Trade.underlying == issue["underlying"],
                    Trade.status == "OPEN",
                    Trade.strategy_type.in_(["Long Stock", "Short Stock"]),
                )
                result = await self.session.execute(stmt)
                trade = result.scalar_one_or_none()

                if trade:
                    # Auto-fix using the split service
                    fix_result = await split_service.fix_trade_with_split(trade.id)
                    if fix_result.get("status") == "CLOSED":
                        auto_fixed += 1

        report["auto_fixed"] = auto_fixed
        return report

    async def _create_trade_from_group(self, group: TradeGroup) -> Trade | None:
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

        # Count unique legs (use normalized expiration to handle timezone differences)
        leg_keys = set()
        for exec in executions:
            if exec.security_type == "OPT":
                expiry = self._normalize_expiration_date(exec.expiration)
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
            greeks_pending=True,  # Greeks will be fetched by scheduler
        )

        self.session.add(trade)
        await self.session.flush()

        # Link executions to trade
        for exec in executions:
            exec.trade_id = trade.id

        return trade

    async def _save_tag_associations(self) -> dict[frozenset[int], list[int]]:
        """Save tag associations before deleting trades.

        Maps execution IDs (as frozenset) to tag IDs so tags can be restored
        after trades are recreated.

        Returns:
            Dict mapping frozenset of execution_ids to list of tag_ids
        """
        from sqlalchemy.orm import selectinload

        tag_mapping: dict[frozenset[int], list[int]] = {}

        # Get all trades with their tags and executions
        stmt = (
            select(Trade)
            .options(selectinload(Trade.tag_list))
            .where(Trade.num_executions > 0)
        )
        result = await self.session.execute(stmt)
        trades = list(result.scalars().all())

        for trade in trades:
            if not trade.tag_list:
                continue

            # Get execution IDs for this trade
            exec_stmt = select(Execution.id).where(Execution.trade_id == trade.id)
            exec_result = await self.session.execute(exec_stmt)
            exec_ids = frozenset(exec_result.scalars().all())

            if exec_ids:
                tag_ids = [tag.id for tag in trade.tag_list]
                tag_mapping[exec_ids] = tag_ids

        return tag_mapping

    async def _restore_tag_associations(
        self, tag_mapping: dict[frozenset[int], list[int]]
    ) -> int:
        """Restore tag associations to newly created trades.

        Args:
            tag_mapping: Dict mapping frozenset of execution_ids to list of tag_ids

        Returns:
            Number of trades with restored tags
        """
        from trading_journal.models.tag import Tag

        if not tag_mapping:
            return 0

        restored_count = 0

        # Get all trades with their executions
        stmt = select(Trade).where(Trade.num_executions > 0)
        result = await self.session.execute(stmt)
        trades = list(result.scalars().all())

        for trade in trades:
            # Get execution IDs for this trade
            exec_stmt = select(Execution.id).where(Execution.trade_id == trade.id)
            exec_result = await self.session.execute(exec_stmt)
            exec_ids = frozenset(exec_result.scalars().all())

            # Check if we have saved tags for these execution IDs
            if exec_ids in tag_mapping:
                tag_ids = tag_mapping[exec_ids]

                # Get the Tag objects
                tag_stmt = select(Tag).where(Tag.id.in_(tag_ids))
                tag_result = await self.session.execute(tag_stmt)
                tags = list(tag_result.scalars().all())

                # Add tags to trade - need to eagerly load the relationship first
                # to avoid async context errors with lazy loading
                from sqlalchemy.orm import selectinload
                await self.session.refresh(trade, ["tag_list"])
                trade.tag_list.extend(tags)
                restored_count += 1

        return restored_count

    async def _save_greeks_data(self) -> dict[frozenset[int], dict]:
        """Save Greeks data before deleting trades.

        Maps execution IDs (as frozenset) to Greeks data so it can be restored
        after trades are recreated.

        Returns:
            Dict mapping frozenset of execution_ids to Greeks data dict
        """
        from trading_journal.models.trade_leg_greeks import TradeLegGreeks

        greeks_mapping: dict[frozenset[int], dict] = {}

        # Get all trades that have Greeks data
        stmt = (
            select(Trade)
            .where(
                Trade.num_executions > 0,
                Trade.greeks_source.isnot(None),  # Has fetched Greeks
            )
        )
        result = await self.session.execute(stmt)
        trades = list(result.scalars().all())

        for trade in trades:
            # Get execution IDs for this trade
            exec_stmt = select(Execution.id).where(Execution.trade_id == trade.id)
            exec_result = await self.session.execute(exec_stmt)
            exec_ids = frozenset(exec_result.scalars().all())

            if not exec_ids:
                continue

            # Get leg Greeks for this trade
            leg_stmt = select(TradeLegGreeks).where(TradeLegGreeks.trade_id == trade.id)
            leg_result = await self.session.execute(leg_stmt)
            leg_greeks = list(leg_result.scalars().all())

            # Save trade-level Greeks and leg Greeks
            greeks_mapping[exec_ids] = {
                "trade_greeks": {
                    "underlying_price_open": trade.underlying_price_open,
                    "delta_open": trade.delta_open,
                    "gamma_open": trade.gamma_open,
                    "theta_open": trade.theta_open,
                    "vega_open": trade.vega_open,
                    "iv_open": trade.iv_open,
                    "greeks_source": trade.greeks_source,
                    "greeks_pending": False,  # Already fetched
                },
                "leg_greeks": [
                    {
                        "snapshot_type": lg.snapshot_type,
                        "leg_index": lg.leg_index,
                        "underlying": lg.underlying,
                        "option_type": lg.option_type,
                        "strike": lg.strike,
                        "expiration": lg.expiration,
                        "quantity": lg.quantity,
                        "delta": lg.delta,
                        "gamma": lg.gamma,
                        "theta": lg.theta,
                        "vega": lg.vega,
                        "rho": lg.rho,
                        "iv": lg.iv,
                        "underlying_price": lg.underlying_price,
                        "option_price": lg.option_price,
                        "bid": lg.bid,
                        "ask": lg.ask,
                        "bid_ask_spread": lg.bid_ask_spread,
                        "open_interest": lg.open_interest,
                        "volume": lg.volume,
                        "data_source": lg.data_source,
                        "captured_at": lg.captured_at,
                    }
                    for lg in leg_greeks
                ],
            }

        return greeks_mapping

    async def _restore_greeks_data(
        self, greeks_mapping: dict[frozenset[int], dict]
    ) -> int:
        """Restore Greeks data to newly created trades.

        Args:
            greeks_mapping: Dict mapping frozenset of execution_ids to Greeks data

        Returns:
            Number of trades with restored Greeks
        """
        from trading_journal.models.trade_leg_greeks import TradeLegGreeks

        if not greeks_mapping:
            return 0

        restored_count = 0

        # Get all trades
        stmt = select(Trade).where(Trade.num_executions > 0)
        result = await self.session.execute(stmt)
        trades = list(result.scalars().all())

        for trade in trades:
            # Get execution IDs for this trade
            exec_stmt = select(Execution.id).where(Execution.trade_id == trade.id)
            exec_result = await self.session.execute(exec_stmt)
            exec_ids = frozenset(exec_result.scalars().all())

            # Check if we have saved Greeks for these execution IDs
            if exec_ids not in greeks_mapping:
                continue

            saved_data = greeks_mapping[exec_ids]

            # Restore trade-level Greeks
            trade_greeks = saved_data["trade_greeks"]
            trade.underlying_price_open = trade_greeks["underlying_price_open"]
            trade.delta_open = trade_greeks["delta_open"]
            trade.gamma_open = trade_greeks["gamma_open"]
            trade.theta_open = trade_greeks["theta_open"]
            trade.vega_open = trade_greeks["vega_open"]
            trade.iv_open = trade_greeks["iv_open"]
            trade.greeks_source = trade_greeks["greeks_source"]
            trade.greeks_pending = False  # Already has Greeks

            # Restore leg Greeks
            for lg_data in saved_data["leg_greeks"]:
                # Ensure captured_at is timezone-aware
                captured_at = lg_data["captured_at"]
                if captured_at and captured_at.tzinfo is None:
                    from datetime import timezone
                    captured_at = captured_at.replace(tzinfo=timezone.utc)

                leg_greeks = TradeLegGreeks(
                    trade_id=trade.id,
                    snapshot_type=lg_data["snapshot_type"],
                    leg_index=lg_data["leg_index"],
                    underlying=lg_data["underlying"],
                    option_type=lg_data["option_type"],
                    strike=lg_data["strike"],
                    expiration=lg_data["expiration"],
                    quantity=lg_data["quantity"],
                    delta=lg_data["delta"],
                    gamma=lg_data["gamma"],
                    theta=lg_data["theta"],
                    vega=lg_data["vega"],
                    rho=lg_data["rho"],
                    iv=lg_data["iv"],
                    underlying_price=lg_data["underlying_price"],
                    option_price=lg_data["option_price"],
                    bid=lg_data["bid"],
                    ask=lg_data["ask"],
                    bid_ask_spread=lg_data["bid_ask_spread"],
                    open_interest=lg_data["open_interest"],
                    volume=lg_data["volume"],
                    data_source=lg_data["data_source"],
                    captured_at=captured_at,
                )
                self.session.add(leg_greeks)

            restored_count += 1

        return restored_count

    async def fetch_greeks_for_pending_trades(self, limit: int = 100) -> dict:
        """Fetch Greeks from Polygon API for all trades with greeks_pending=True.

        This method is called automatically after trade grouping to populate
        Greeks data for newly created option trades.

        Args:
            limit: Maximum number of trades to process (to avoid API rate limits)

        Returns:
            Dict with statistics about fetched trades
        """
        from trading_journal.models.trade_leg_greeks import TradeLegGreeks
        from trading_journal.services.fred_service import FredService
        from trading_journal.services.polygon_service import PolygonService, PolygonServiceError
        from trading_journal.services.trade_analytics_service import LegData, TradeAnalyticsService

        stats = {
            "trades_processed": 0,
            "trades_succeeded": 0,
            "trades_failed": 0,
            "trades_skipped": 0,
        }

        # Get trades with pending Greeks - only OPEN trades
        # (Closed/expired trades have options that Polygon may not have data for)
        stmt = (
            select(Trade)
            .where(
                Trade.greeks_pending == True,  # noqa: E712
                Trade.status == "OPEN",  # Only fetch for open trades
            )
            .order_by(Trade.opened_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        trades = list(result.scalars().all())

        if not trades:
            logger.info("No trades with pending Greeks to fetch")
            return stats

        logger.info(f"Fetching Greeks for {len(trades)} pending trades")

        # Get risk-free rate once for all calculations
        try:
            async with FredService() as fred:
                rate_data = await fred.get_risk_free_rate()
                risk_free_rate = rate_data.rate
        except Exception:
            risk_free_rate = Decimal("0.05")

        try:
            async with PolygonService() as polygon:
                for trade in trades:
                    stats["trades_processed"] += 1
                    try:
                        success = await self._fetch_greeks_for_trade(
                            trade, polygon, risk_free_rate
                        )
                        if success:
                            stats["trades_succeeded"] += 1
                        else:
                            stats["trades_skipped"] += 1
                    except Exception as e:
                        logger.warning(f"Failed to fetch Greeks for trade {trade.id}: {e}")
                        stats["trades_failed"] += 1
                        trade.greeks_pending = False  # Mark as processed even if failed

        except PolygonServiceError as e:
            logger.error(f"Polygon API error: {e}")

        await self.session.commit()
        logger.info(
            f"Greeks fetch complete: {stats['trades_succeeded']} succeeded, "
            f"{stats['trades_failed']} failed, {stats['trades_skipped']} skipped"
        )

        return stats

    async def _fetch_greeks_for_trade(
        self,
        trade: Trade,
        polygon: "PolygonService",
        risk_free_rate: Decimal,
    ) -> bool:
        """Fetch Greeks for a single trade from Polygon.

        Args:
            trade: Trade to fetch Greeks for
            polygon: PolygonService instance
            risk_free_rate: Current risk-free rate

        Returns:
            True if successfully fetched, False if skipped (no option legs)
        """
        from trading_journal.models.trade_leg_greeks import TradeLegGreeks
        from trading_journal.services.trade_analytics_service import LegData, TradeAnalyticsService

        # Get executions for this trade
        exec_stmt = (
            select(Execution)
            .where(Execution.trade_id == trade.id)
            .order_by(Execution.execution_time)
        )
        result = await self.session.execute(exec_stmt)
        executions = list(result.scalars().all())

        if not executions:
            trade.greeks_pending = False
            return False

        # Build unique legs from executions
        # Use normalized expiration date in key to handle timezone/DST differences
        legs_map: dict[tuple, dict] = {}

        if trade.status == "CLOSED":
            # For closed trades, look at opening transactions
            for exec in executions:
                if exec.option_type and exec.strike and exec.expiration:
                    if exec.open_close_indicator == "O":
                        # Use normalized expiration for grouping, but keep original for API calls
                        exp_normalized = self._normalize_expiration_date(exec.expiration)
                        key = (exec.option_type, exec.strike, exp_normalized)
                        if key not in legs_map:
                            legs_map[key] = {
                                "option_type": exec.option_type,
                                "strike": exec.strike,
                                "expiration": exec.expiration,
                                "quantity": 0,
                            }
                        if exec.side == "BOT":
                            legs_map[key]["quantity"] += exec.quantity
                        else:
                            legs_map[key]["quantity"] -= exec.quantity
            active_legs = list(legs_map.values())
        else:
            # For open trades, use net position
            for exec in executions:
                if exec.option_type and exec.strike and exec.expiration:
                    # Use normalized expiration for grouping, but keep original for API calls
                    exp_normalized = self._normalize_expiration_date(exec.expiration)
                    key = (exec.option_type, exec.strike, exp_normalized)
                    if key not in legs_map:
                        legs_map[key] = {
                            "option_type": exec.option_type,
                            "strike": exec.strike,
                            "expiration": exec.expiration,
                            "quantity": 0,
                        }
                    if exec.side == "BOT":
                        legs_map[key]["quantity"] += exec.quantity
                    else:
                        legs_map[key]["quantity"] -= exec.quantity
            active_legs = [v for v in legs_map.values() if v["quantity"] != 0]

        if not active_legs:
            trade.greeks_pending = False
            return False

        # Fetch Greeks from Polygon
        leg_data_list: list[LegData] = []

        # Get underlying price
        quote = await polygon.get_underlying_price(trade.underlying)
        underlying_price = quote.price if quote else None

        for idx, leg in enumerate(active_legs):
            greeks = await polygon.get_option_greeks(
                underlying=trade.underlying,
                expiration=leg["expiration"],
                option_type=leg["option_type"],
                strike=leg["strike"],
                fetch_underlying_price=False,
            )

            if greeks:
                leg_data_list.append(
                    LegData(
                        option_type=leg["option_type"],
                        strike=leg["strike"],
                        expiration=leg["expiration"],
                        quantity=leg["quantity"],
                        delta=greeks.delta,
                        gamma=greeks.gamma,
                        theta=greeks.theta,
                        vega=greeks.vega,
                        iv=greeks.iv,
                    )
                )

                # Store leg Greeks
                # Ensure timestamp is timezone-aware
                from datetime import timezone
                captured_at = greeks.timestamp
                if captured_at and captured_at.tzinfo is None:
                    captured_at = captured_at.replace(tzinfo=timezone.utc)

                leg_greeks = TradeLegGreeks(
                    trade_id=trade.id,
                    snapshot_type="OPEN",
                    leg_index=idx,
                    underlying=trade.underlying,
                    option_type=leg["option_type"],
                    strike=leg["strike"],
                    expiration=leg["expiration"],
                    quantity=leg["quantity"],
                    delta=greeks.delta,
                    gamma=greeks.gamma,
                    theta=greeks.theta,
                    vega=greeks.vega,
                    iv=greeks.iv,
                    underlying_price=underlying_price,
                    option_price=greeks.option_price,
                    bid=greeks.bid,
                    ask=greeks.ask,
                    bid_ask_spread=greeks.bid_ask_spread,
                    open_interest=greeks.open_interest,
                    volume=greeks.volume,
                    data_source="POLYGON",
                    captured_at=captured_at,
                )
                self.session.add(leg_greeks)

        # Calculate trade-level analytics
        if leg_data_list:
            analytics_service = TradeAnalyticsService(risk_free_rate=risk_free_rate)
            net_greeks = analytics_service.calculate_net_greeks(leg_data_list, multiplier=1)
            trade_iv = analytics_service.get_trade_iv(leg_data_list, trade.strategy_type)

            # Update trade with analytics
            trade.underlying_price_open = underlying_price
            trade.delta_open = net_greeks["net_delta"]
            trade.gamma_open = net_greeks["net_gamma"]
            trade.theta_open = net_greeks["net_theta"]
            trade.vega_open = net_greeks["net_vega"]
            trade.iv_open = trade_iv
            trade.greeks_source = "POLYGON"

        trade.greeks_pending = False
        return len(leg_data_list) > 0
