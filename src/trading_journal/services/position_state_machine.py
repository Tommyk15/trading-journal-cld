"""Position State Machine - Core algorithm for trade grouping.

This module implements a state-based approach to grouping executions into trades:
1. Maintains position state per underlying/leg
2. Detects trade events: OPEN, ADD, PARTIAL_CLOSE, CLOSE, ROLL
3. Creates proper trade boundaries
4. Links rolls and adjustments
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum

from trading_journal.models.execution import Execution


class TradeEvent(str, Enum):
    """Trade lifecycle events."""
    OPEN = "OPEN"                    # New position opened from flat
    ADD = "ADD"                      # Added to existing position
    PARTIAL_CLOSE = "PARTIAL_CLOSE"  # Reduced position but not flat
    CLOSE = "CLOSE"                  # Position fully closed
    ROLL = "ROLL"                    # Closed legs and opened different legs same session
    ADJUST = "ADJUST"                # Changed position structure (added/removed legs)


class PositionState(str, Enum):
    """Position state."""
    FLAT = "FLAT"
    OPEN = "OPEN"


@dataclass
class LegPosition:
    """Position state for a single leg."""
    leg_key: str
    quantity: int = 0
    total_cost: Decimal = field(default_factory=lambda: Decimal("0.00"))
    avg_cost: Decimal = field(default_factory=lambda: Decimal("0.00"))
    executions: list[Execution] = field(default_factory=list)

    @property
    def is_flat(self) -> bool:
        return self.quantity == 0

    @property
    def is_long(self) -> bool:
        return self.quantity > 0

    @property
    def is_short(self) -> bool:
        return self.quantity < 0


@dataclass
class TradeGroup:
    """A grouped trade with its executions."""
    underlying: str
    executions: list[Execution] = field(default_factory=list)
    opening_position: dict[str, int] = field(default_factory=dict)  # leg_key -> opening qty
    strategy_type: str = "Unknown"
    status: str = "OPEN"
    parent_trade_id: int | None = None
    roll_type: str | None = None  # "ROLL" or "ADJUST" or None
    is_assignment: bool = False  # True if this trade is from option assignment/exercise
    assigned_from_trade_id: int | None = None  # ID of the option trade that was assigned

    def add_execution(self, exec: Execution) -> None:
        """Add execution to this trade group."""
        self.executions.append(exec)

    @property
    def execution_ids(self) -> list[int]:
        return [e.id for e in self.executions]

    @property
    def opened_at(self) -> datetime | None:
        if not self.executions:
            return None
        return min(e.execution_time for e in self.executions)

    @property
    def closed_at(self) -> datetime | None:
        if self.status != "CLOSED" or not self.executions:
            return None
        return max(e.execution_time for e in self.executions)


class PositionStateMachine:
    """State machine for tracking positions and creating trade groups.

    This class processes executions chronologically and:
    1. Tracks cumulative position per leg
    2. Detects when trades open/close/roll
    3. Groups executions into logical trades

    IMPORTANT: A "trade" is a combo of legs opened together. Multiple spreads
    on the same underlying but opened at different times are SEPARATE trades.
    """

    # Time window for grouping simultaneous executions (multi-leg orders)
    SIMULTANEOUS_WINDOW = timedelta(seconds=5)

    # Time window for detecting rolls (same day)
    ROLL_WINDOW = timedelta(hours=24)

    def __init__(self, underlying: str):
        """Initialize state machine for an underlying.

        Args:
            underlying: The underlying symbol
        """
        self.underlying = underlying
        self.position: dict[str, LegPosition] = {}  # leg_key -> LegPosition
        # Track multiple concurrent trades by their leg sets
        self.open_trades: dict[frozenset[str], TradeGroup] = {}  # leg_keys -> TradeGroup
        self.completed_trades: list[TradeGroup] = []
        self.last_trade_close_time: datetime | None = None

    def get_leg_key(self, exec: Execution) -> str:
        """Generate unique key for a position leg.

        Args:
            exec: Execution object

        Returns:
            Unique leg key string
        """
        if exec.security_type == "OPT":
            expiry = self._normalize_expiration_date(exec.expiration)
            strike = f"{exec.strike}" if exec.strike else ""
            return f"{expiry}_{strike}_{exec.option_type}"
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
            from datetime import timedelta
            expiration = expiration + timedelta(days=1)

        return expiration.strftime("%Y%m%d")

    def is_flat(self) -> bool:
        """Check if all positions are flat."""
        return all(leg.is_flat for leg in self.position.values())

    def get_active_legs(self) -> set[str]:
        """Get set of legs with non-zero position."""
        return {k for k, v in self.position.items() if not v.is_flat}

    def process_executions(self, executions: list[Execution]) -> list[TradeGroup]:
        """Process a list of executions and return trade groups.

        A trade is a combo of legs opened together. Multiple spreads on the
        same underlying opened at different times are SEPARATE trades.

        Args:
            executions: List of executions (should be for same underlying)

        Returns:
            List of completed and open trade groups
        """
        if not executions:
            return []

        # Sort chronologically
        sorted_execs = sorted(executions, key=lambda e: e.execution_time)

        # Group simultaneous executions (multi-leg orders)
        exec_groups = self._group_simultaneous(sorted_execs)

        # Process each group
        for group in exec_groups:
            self._process_execution_group_v2(group)

        # Add any remaining open trades
        for trade in self.open_trades.values():
            if trade.executions:
                # Check if the legs are flat FOR THIS SPECIFIC TRADE
                # Use per-trade remaining quantity to handle multiple trades with same leg
                trade_legs = set(trade.opening_position.keys())
                for exec in trade.executions:
                    trade_legs.add(self.get_leg_key(exec))

                all_flat = all(
                    self._calculate_trade_remaining_qty(trade, leg) == 0
                    for leg in trade_legs
                )
                trade.status = "CLOSED" if all_flat else "OPEN"
                self.completed_trades.append(trade)

        return self.completed_trades

    # Maximum expiration difference (in days) for executions to be in the same trade
    # Executions with expirations > 30 days apart are likely different strategies
    EXPIRATION_CLUSTER_DAYS = 30

    def _group_simultaneous(self, executions: list[Execution]) -> list[list[Execution]]:
        """Group near-simultaneous executions, then split by order/expiration/strike.

        Executions are grouped by:
        1. Time (within SIMULTANEOUS_WINDOW)
        2. Check if time group forms a valid spread (keep together if so)
        3. If not a spread, split by order ID / expiration / strike

        Args:
            executions: Sorted list of executions

        Returns:
            List of execution groups
        """
        if not executions:
            return []

        # First pass: group by time
        time_groups = []
        current_group = []
        group_start_time = None

        for exec in executions:
            if not current_group:
                current_group = [exec]
                group_start_time = exec.execution_time
            else:
                time_diff = exec.execution_time - group_start_time
                if time_diff <= self.SIMULTANEOUS_WINDOW:
                    current_group.append(exec)
                else:
                    time_groups.append(current_group)
                    current_group = [exec]
                    group_start_time = exec.execution_time

        if current_group:
            time_groups.append(current_group)

        # Second pass: check each time group for spread structure BEFORE splitting
        # If a time group is a valid spread, keep it together
        spread_checked_groups = []
        for time_group in time_groups:
            if self._is_valid_spread(time_group):
                # This is a spread - keep together, don't split by order_id
                spread_checked_groups.append(time_group)
            else:
                # Not a spread - split by order_id
                order_subgroups = self._split_by_order_id(time_group)
                spread_checked_groups.extend(order_subgroups)

        # Third pass: split each group by expiration cluster
        expiration_groups = []
        for group in spread_checked_groups:
            expiration_subgroups = self._split_by_expiration(group)
            expiration_groups.extend(expiration_subgroups)

        # Fourth pass: split non-spread groups by strike
        final_groups = []
        for exp_group in expiration_groups:
            strike_subgroups = self._split_non_spreads_by_strike(exp_group)
            final_groups.extend(strike_subgroups)

        return final_groups

    def _split_by_order_id(self, executions: list[Execution]) -> list[list[Execution]]:
        """Split executions by order_id - different orders are different trades.

        Order ID of 0 is treated as "unknown" and those executions are grouped
        together for further analysis.

        Args:
            executions: List of executions to split

        Returns:
            List of execution groups, one per unique order_id
        """
        if not executions:
            return []

        # Group by order_id
        by_order: dict[int, list[Execution]] = {}
        unknown_order: list[Execution] = []

        for exec in executions:
            order_id = exec.order_id or 0
            if order_id == 0:
                # Order ID 0 or None - needs further analysis
                unknown_order.append(exec)
            else:
                if order_id not in by_order:
                    by_order[order_id] = []
                by_order[order_id].append(exec)

        groups = list(by_order.values())

        # Unknown orders need strike-based splitting
        if unknown_order:
            groups.append(unknown_order)

        return groups

    def _split_non_spreads_by_strike(self, executions: list[Execution]) -> list[list[Execution]]:
        """Split executions by strike if they don't form a valid spread.

        A valid spread has:
        - Multiple different strikes
        - Matching quantities (same qty bought and sold)
        - Same option type (all calls or all puts)

        If executions don't form a valid spread, split them by strike.

        Args:
            executions: List of executions

        Returns:
            List of execution groups
        """
        if not executions or len(executions) <= 1:
            return [executions] if executions else []

        # Get unique strikes
        strikes = set(e.strike for e in executions if e.strike is not None)

        # If only one strike, no need to split
        if len(strikes) <= 1:
            return [executions]

        # Check if this looks like a valid spread
        if self._is_valid_spread(executions):
            return [executions]

        # Not a valid spread - split by strike
        by_strike: dict[float, list[Execution]] = {}
        for exec in executions:
            strike = float(exec.strike) if exec.strike else 0.0
            if strike not in by_strike:
                by_strike[strike] = []
            by_strike[strike].append(exec)

        return list(by_strike.values())

    def _is_valid_spread(self, executions: list[Execution]) -> bool:
        """Check if executions form a valid spread structure.

        A valid spread MUST have:
        - 2+ different strikes with matching quantities
        - Both buys and sells
        - Evidence they're part of the same spread order:
          * Same non-zero order_id for all, OR
          * ALL have O/C = 'O' (all openings - entered as a spread)

        Key insight: IBKR often assigns DIFFERENT order_ids to each leg of a
        spread order, so we can't rely on order_id alone. Instead, we check:
        - If ALL executions have O/C = 'O' (openings) → likely a spread
        - If ANY execution has O/C = 'C' (closing) → NOT a spread
          (one leg is closing an old trade, the other opening a new one)

        Args:
            executions: List of executions to check

        Returns:
            True if this is definitively a spread order
        """
        if len(executions) < 2:
            return False

        # Must have both buys and sells
        buys = [e for e in executions if e.side == "BOT"]
        sells = [e for e in executions if e.side == "SLD"]
        if not buys or not sells:
            return False

        # Check O/C indicators - this is the KEY differentiator
        # If ALL are openings (O/C = 'O'), it's likely a spread entered together
        # If ANY is a closing (O/C = 'C'), they're separate trades
        oc_indicators = [e.open_close_indicator for e in executions]
        has_closing = any(oc == 'C' for oc in oc_indicators)

        if has_closing:
            # At least one leg is closing - NOT a spread
            # (e.g., TSLA 492.5 closing + 510 opening = separate trades)
            return False

        # Check if all have O/C = 'O' (explicit openings)
        all_opening = all(oc == 'O' for oc in oc_indicators)

        # Check order_ids
        order_ids = set(e.order_id for e in executions if e.order_id)

        if len(order_ids) == 1:
            # Single order_id - definitely a spread (same order)
            pass
        elif len(order_ids) > 1:
            # Multiple order_ids - only a spread if ALL are explicit openings
            # (IBKR assigns different order_ids per leg for spread orders)
            if not all_opening:
                return False
        else:
            # No order_ids - only accept if all are explicit openings
            if not all_opening:
                return False

        # Calculate total quantities per side
        buy_qty = sum(e.quantity for e in buys)
        sell_qty = sum(e.quantity for e in sells)

        # Quantities should be roughly equal for a spread
        if buy_qty == 0 or sell_qty == 0:
            return False

        qty_ratio = min(buy_qty, sell_qty) / max(buy_qty, sell_qty)
        if qty_ratio < 0.9:
            return False

        return True

    def _split_by_expiration(self, executions: list[Execution]) -> list[list[Execution]]:
        """Split executions into groups based on expiration clusters.

        Options with expirations more than EXPIRATION_CLUSTER_DAYS apart are
        placed in separate groups. Stock executions (no expiration) are grouped
        separately.

        Args:
            executions: List of executions to split

        Returns:
            List of execution groups, each with similar expirations
        """
        if not executions:
            return []

        # Separate stock executions from options
        stock_execs = [e for e in executions if e.security_type != "OPT" or not e.expiration]
        option_execs = [e for e in executions if e.security_type == "OPT" and e.expiration]

        groups = []

        # Stock executions form their own group if present
        if stock_execs:
            groups.append(stock_execs)

        # Cluster options by expiration
        if option_execs:
            # Sort by expiration
            sorted_options = sorted(option_execs, key=lambda e: e.expiration)

            current_cluster = [sorted_options[0]]
            cluster_anchor_exp = sorted_options[0].expiration

            for exec in sorted_options[1:]:
                days_diff = (exec.expiration - cluster_anchor_exp).days
                if abs(days_diff) <= self.EXPIRATION_CLUSTER_DAYS:
                    current_cluster.append(exec)
                else:
                    # Start new cluster
                    groups.append(current_cluster)
                    current_cluster = [exec]
                    cluster_anchor_exp = exec.expiration

            if current_cluster:
                groups.append(current_cluster)

        return groups

    def _process_execution_group_v2(self, group: list[Execution]) -> None:
        """Process a group of simultaneous executions (v2 - multi-trade aware).

        Key principle: A trade is a combo of legs opened TOGETHER. Multiple
        spreads on the same underlying opened at different times are SEPARATE trades.

        However, ROLLS are special: when closing one leg and opening another in the
        same execution group, we need to:
        1. Add the closing executions to the existing trade
        2. Check if we're opening new legs (a roll)
        3. If rolling, the new legs become a NEW trade (linked as a roll)

        Args:
            group: List of executions in this group
        """
        frozenset(self.get_leg_key(e) for e in group)
        self._calculate_deltas(group)
        exec_time = group[0].execution_time

        # Separate executions into closing vs opening based on open_close_indicator
        # or by analyzing position changes
        closing_execs = []
        opening_execs = []

        for exec in group:
            leg = self.get_leg_key(exec)
            current_qty = self.position.get(leg, LegPosition(leg)).quantity

            if exec.open_close_indicator == 'C':
                closing_execs.append(exec)
            elif exec.open_close_indicator == 'O':
                opening_execs.append(exec)
            elif current_qty != 0:
                # Has existing position - check if reducing
                delta = exec.quantity if exec.side == "BOT" else -exec.quantity
                if (current_qty > 0 and delta < 0) or (current_qty < 0 and delta > 0):
                    closing_execs.append(exec)
                else:
                    opening_execs.append(exec)
            else:
                # No position, must be opening
                opening_execs.append(exec)

        closing_legs = frozenset(self.get_leg_key(e) for e in closing_execs)
        opening_legs = frozenset(self.get_leg_key(e) for e in opening_execs)

        # Process closing executions first - assign to existing trades
        # Orphaned closes (no matching trade) are treated as openings
        # IMPORTANT: Must check remaining quantity to avoid over-closing a trade
        orphaned_closes = []
        if closing_execs:
            closing_deltas = self._calculate_deltas(closing_execs)

            for exec in closing_execs:
                leg_key = self.get_leg_key(exec)
                leg = frozenset([leg_key])
                exec_qty = int(exec.quantity) if exec.side == "BOT" else -int(exec.quantity)

                # Find a trade that can accept this closing execution
                # without over-closing (crossing zero)
                assigned = False
                for trade_key, trade in sorted(
                    self.open_trades.items(),
                    key=lambda x: x[1].opened_at or datetime.min
                ):
                    remaining = self._calculate_trade_remaining_qty(trade, leg_key)
                    if remaining == 0:
                        continue

                    # Check if this execution would over-close the trade
                    # remaining > 0 (long) + exec_qty < 0 (sell to close) = closing long
                    # remaining < 0 (short) + exec_qty > 0 (buy to close) = closing short
                    would_over_close = False
                    if remaining > 0 and exec_qty < 0:
                        # Closing a long position - can close up to 'remaining' qty
                        if abs(exec_qty) > remaining:
                            would_over_close = True
                    elif remaining < 0 and exec_qty > 0:
                        # Closing a short position - can close up to abs(remaining) qty
                        if exec_qty > abs(remaining):
                            would_over_close = True

                    if not would_over_close:
                        trade.add_execution(exec)
                        assigned = True
                        break

                if not assigned:
                    # No trade can accept this execution without over-closing
                    # Fallback: assign to the trade with the MOST remaining quantity
                    # (minimizes over-close impact on any single trade)
                    best_trade = None
                    best_remaining = 0
                    for trade_key, trade in self.open_trades.items():
                        remaining = self._calculate_trade_remaining_qty(trade, leg_key)
                        # Only consider trades with matching direction
                        # (short position for buy-to-close, long for sell-to-close)
                        if remaining != 0:
                            if (remaining < 0 and exec_qty > 0) or (remaining > 0 and exec_qty < 0):
                                if abs(remaining) > abs(best_remaining):
                                    best_remaining = remaining
                                    best_trade = trade

                    if best_trade is not None:
                        best_trade.add_execution(exec)
                        assigned = True
                    else:
                        # No matching trade at all - treat as orphaned close
                        orphaned_closes.append(exec)

            # Apply closing deltas to position (only for matched closes)
            matched_closes = [e for e in closing_execs if e not in orphaned_closes]
            if matched_closes:
                matched_deltas = self._calculate_deltas(matched_closes)
                self._apply_deltas(matched_deltas, matched_closes)

        # Add orphaned closes to opening executions
        if orphaned_closes:
            opening_execs.extend(orphaned_closes)
            # Recalculate opening_legs to include orphaned closes
            opening_legs = frozenset(self.get_leg_key(e) for e in opening_execs)

        # Check if any trades are now fully closed (after processing matched closes)
        # Use per-trade remaining quantity (not global position) to properly
        # handle multiple trades with the same leg
        matched_closes = [e for e in closing_execs if e not in orphaned_closes] if closing_execs else []
        if matched_closes:
            # Only check for closed trades if we actually processed some closes
            trades_to_close = []
            for trade_key, trade in list(self.open_trades.items()):
                # Get ALL legs this trade has touched (from opening_position + any added legs)
                trade_legs = set(trade.opening_position.keys())
                # Also check executions for any legs
                for exec in trade.executions:
                    trade_legs.add(self.get_leg_key(exec))

                # Check if all legs are flat FOR THIS SPECIFIC TRADE
                all_flat = all(
                    self._calculate_trade_remaining_qty(trade, leg) == 0
                    for leg in trade_legs
                )

                if all_flat:
                    trades_to_close.append(trade_key)

            for trade_key in trades_to_close:
                trade = self.open_trades[trade_key]
                trade.status = "CLOSED"
                self.completed_trades.append(trade)
                del self.open_trades[trade_key]
                self.last_trade_close_time = exec_time

        # Process opening executions - create new trade(s) or add to existing
        # Key insight: If opening executions form a SPREAD (multiple different strikes
        # at the same timestamp), they should be kept together as a NEW trade,
        # not split across existing trades.
        if opening_execs:
            opening_leg_keys = set(self.get_leg_key(e) for e in opening_execs)
            opening_legs_frozen = frozenset(opening_leg_keys)

            # Check for assignment: option closing at $0 with stock opening
            is_assignment_from_option = self._detect_assignment(closing_execs, opening_execs)

            # Check if there's an existing trade with the EXACT same legs (adding to position)
            existing_trade_key = None
            for trade_key in self.open_trades:
                # For spread additions, check if ALL legs match (same structure)
                if opening_legs_frozen == trade_key:
                    existing_trade_key = trade_key
                    break
                # Also check if legs are a subset (adding to same expiration spread)
                if opening_legs_frozen.issubset(trade_key) or trade_key.issubset(opening_legs_frozen):
                    # Verify expiration compatibility
                    existing_exp = self._get_expirations_from_legs(trade_key)
                    new_exp = self._get_expirations_from_legs(opening_legs_frozen)
                    if existing_exp and new_exp and self._expirations_are_compatible(existing_exp, new_exp):
                        existing_trade_key = trade_key
                        break

            if existing_trade_key is not None and not is_assignment_from_option:
                # Add to existing trade with same leg structure
                existing_trade = self.open_trades[existing_trade_key]
                for exec in opening_execs:
                    existing_trade.add_execution(exec)

                # Update trade key to include any new legs
                new_key = existing_trade_key | opening_legs_frozen
                if new_key != existing_trade_key:
                    self.open_trades[new_key] = self.open_trades.pop(existing_trade_key)

                # Apply deltas
                deltas = self._calculate_deltas(opening_execs)
                self._apply_deltas(deltas, opening_execs)
            else:
                # Check if this is a new spread structure
                is_new_spread = self._is_new_spread_structure(opening_execs, opening_leg_keys)

                if is_new_spread or is_assignment_from_option:
                    # Create ALL opening executions as a NEW trade together
                    # Don't split them across existing trades
                    self._create_new_trade(
                        opening_execs,
                        closing_execs,
                        closing_legs,
                        force_assignment=is_assignment_from_option
                    )
                else:
                    # Single leg additions - use existing logic to match to existing trades
                    execs_by_target: dict[frozenset[str] | None, list[Execution]] = {}

                    for exec in opening_execs:
                        exec_leg = frozenset([self.get_leg_key(exec)])
                        target_trade_key = None

                        # Find existing trade with this leg
                        for trade_key in self.open_trades:
                            if exec_leg & trade_key:
                                # Check expiration compatibility
                                existing_expirations = self._get_expirations_from_legs(trade_key)
                                new_expirations = self._get_expirations_from_legs(exec_leg)
                                if existing_expirations and new_expirations:
                                    if not self._expirations_are_compatible(existing_expirations, new_expirations):
                                        continue
                                target_trade_key = trade_key
                                break

                        if target_trade_key not in execs_by_target:
                            execs_by_target[target_trade_key] = []
                        execs_by_target[target_trade_key].append(exec)

                    # Process each target group
                    for target_key, execs in execs_by_target.items():
                        if target_key is not None:
                            # Add to existing trade
                            existing_trade = self.open_trades[target_key]
                            for exec in execs:
                                existing_trade.add_execution(exec)

                            # Update trade key to include any new legs
                            new_legs = frozenset(self.get_leg_key(e) for e in execs)
                            new_key = target_key | new_legs
                            if new_key != target_key:
                                self.open_trades[new_key] = self.open_trades.pop(target_key)
                                target_key = new_key

                            # Apply deltas
                            deltas = self._calculate_deltas(execs)
                            self._apply_deltas(deltas, execs)
                        else:
                            # Create new trade for these executions
                            self._create_new_trade(execs, closing_execs, closing_legs)

    def _find_matching_trade(self, group_legs: frozenset[str]) -> tuple[frozenset[str], TradeGroup] | None:
        """Find an open trade that matches the given legs (FIFO order).

        A trade matches if the group legs overlap with the trade's legs AND
        the trade still has remaining open quantity for at least one of those legs.
        We need to check both the original trade_key AND any legs added via rolls.

        Returns the OLDEST matching trade (FIFO) to properly distribute closings
        across multiple trades with the same leg.

        Args:
            group_legs: Set of leg keys in the execution group

        Returns:
            Tuple of (trade_key, trade) or None if no match
        """
        matching_trades = []

        for trade_key, trade in self.open_trades.items():
            # Get all legs this trade has touched
            all_trade_legs = set(trade_key)
            all_trade_legs.update(trade.opening_position.keys())
            for exec in trade.executions:
                all_trade_legs.add(self.get_leg_key(exec))

            # Check if group legs overlap with any of the trade's legs
            overlapping_legs = group_legs & all_trade_legs
            if overlapping_legs:
                # Check if trade has remaining open quantity for any overlapping leg
                has_open_qty = False
                for leg in overlapping_legs:
                    remaining = self._calculate_trade_remaining_qty(trade, leg)
                    if remaining != 0:
                        has_open_qty = True
                        break

                if has_open_qty:
                    matching_trades.append((trade_key, trade))

        if not matching_trades:
            return None

        # Sort by opened_at (FIFO) - oldest trade first
        matching_trades.sort(key=lambda x: x[1].opened_at or datetime.min)
        return matching_trades[0]

    def _calculate_trade_remaining_qty(self, trade: TradeGroup, leg: str) -> int:
        """Calculate remaining open quantity for a specific leg in a trade.

        This is used to determine which trade should receive closing executions
        when multiple trades have the same leg open.

        Calculates position purely from executions to avoid double-counting issues
        with opening_position. Each execution's contribution:
        - Opening ('O'): adds to position (buy = +, sell = -)
        - Closing ('C'): reduces position toward zero

        Args:
            trade: The trade to check
            leg: The leg key to calculate quantity for

        Returns:
            Remaining open quantity (positive for long, negative for short, 0 if closed)
        """
        qty = 0

        # Calculate from all executions in this trade
        for exec in trade.executions:
            if self.get_leg_key(exec) == leg:
                exec_delta = int(exec.quantity) if exec.side == "BOT" else -int(exec.quantity)

                if exec.open_close_indicator == 'O':
                    # Opening: add to position
                    qty += exec_delta
                elif exec.open_close_indicator == 'C':
                    # Closing: reduce position toward zero
                    if qty > 0:
                        qty = max(0, qty + exec_delta)
                    elif qty < 0:
                        qty = min(0, qty + exec_delta)
                else:
                    # No indicator: infer from position direction
                    # If delta moves position toward zero, treat as closing
                    if (qty > 0 and exec_delta < 0) or (qty < 0 and exec_delta > 0):
                        if qty > 0:
                            qty = max(0, qty + exec_delta)
                        else:
                            qty = min(0, qty + exec_delta)
                    else:
                        # Adding to position
                        qty += exec_delta

        return qty

    def _trade_is_closed(self, trade_key: frozenset[str]) -> bool:
        """Check if all legs of a trade are now flat (closed).

        Args:
            trade_key: Frozenset of leg keys for the trade

        Returns:
            True if all legs are at zero quantity
        """
        return all(
            self.position.get(leg, LegPosition(leg)).quantity == 0
            for leg in trade_key
        )

    def _get_expirations_from_legs(self, legs: frozenset[str]) -> set[date]:
        """Extract expiration dates from leg keys.

        Leg keys have format: {expiry}_{strike}_{option_type} for options,
        or "STK" for stocks.

        Args:
            legs: Frozenset of leg keys

        Returns:
            Set of expiration dates (empty for stock-only legs)
        """
        expirations: set[date] = set()
        for leg in legs:
            if leg == "STK":
                continue
            parts = leg.split("_")
            if len(parts) >= 1 and parts[0]:
                try:
                    # Parse YYYYMMDD format
                    exp_str = parts[0]
                    exp_date = date(
                        int(exp_str[:4]),
                        int(exp_str[4:6]),
                        int(exp_str[6:8])
                    )
                    expirations.add(exp_date)
                except (ValueError, IndexError):
                    pass
        return expirations

    def _expirations_are_compatible(
        self,
        expirations1: set[date],
        expirations2: set[date]
    ) -> bool:
        """Check if two sets of expirations are close enough to be the same trade.

        Args:
            expirations1: First set of expiration dates
            expirations2: Second set of expiration dates

        Returns:
            True if all expirations are within EXPIRATION_CLUSTER_DAYS of each other
        """
        if not expirations1 or not expirations2:
            return True  # If either is empty, allow merge

        # Check if any expiration from set2 is too far from all expirations in set1
        for exp2 in expirations2:
            min_diff = min(abs((exp2 - exp1).days) for exp1 in expirations1)
            if min_diff > self.EXPIRATION_CLUSTER_DAYS:
                return False
        return True

    def _is_new_spread_structure(
        self,
        opening_execs: list[Execution],
        opening_leg_keys: set[str]
    ) -> bool:
        """Check if opening executions form a new spread structure.

        A spread structure is:
        - 2+ different option legs (different strikes or types)
        - Same expiration (approximately)
        - Has both long and short sides (vertical spread)

        This prevents spread legs from being split across different trades.

        Args:
            opening_execs: List of opening executions
            opening_leg_keys: Set of leg keys

        Returns:
            True if this is a new spread that should stay together
        """
        # Need at least 2 different option legs
        option_legs = [k for k in opening_leg_keys if k != "STK"]
        if len(option_legs) < 2:
            return False

        # Check if we have both buys and sells (spread structure)
        has_buys = any(e.side == "BOT" and e.security_type == "OPT" for e in opening_execs)
        has_sells = any(e.side == "SLD" and e.security_type == "OPT" for e in opening_execs)

        if not (has_buys and has_sells):
            return False

        # Extract strikes from option legs
        strikes = set()
        for leg in option_legs:
            parts = leg.split("_")
            if len(parts) >= 2:
                try:
                    strikes.add(float(parts[1]))
                except (ValueError, IndexError):
                    pass

        # Multiple different strikes = spread
        return len(strikes) >= 2

    def _detect_assignment(
        self,
        closing_execs: list[Execution],
        opening_execs: list[Execution]
    ) -> bool:
        """Detect if this is an option assignment (exercise).

        An assignment is detected when:
        - Option is closing (being exercised/assigned)
        - Option price is $0 or very low (intrinsic value only)
        - Stock is opening at the same time
        - Stock quantity = option quantity * 100

        Args:
            closing_execs: Executions closing positions
            opening_execs: Executions opening positions

        Returns:
            True if this appears to be an assignment
        """
        if not closing_execs or not opening_execs:
            return False

        # Find option closes at $0 (or very low price indicating exercise)
        option_closes = [
            e for e in closing_execs
            if e.security_type == "OPT" and e.price <= 0.05
        ]

        if not option_closes:
            return False

        # Find stock opens
        stock_opens = [
            e for e in opening_execs
            if e.security_type == "STK"
        ]

        if not stock_opens:
            return False

        # Check quantity relationship: stock qty should be ~100x option qty
        total_option_qty = sum(e.quantity for e in option_closes)
        total_stock_qty = sum(e.quantity for e in stock_opens)

        expected_stock_qty = total_option_qty * 100

        # Allow some tolerance for partial fills
        if abs(total_stock_qty - expected_stock_qty) <= expected_stock_qty * 0.1:
            return True

        return False

    def _create_new_trade(
        self,
        opening_execs: list[Execution],
        closing_execs: list[Execution],
        closing_legs: frozenset[str],
        force_assignment: bool = False
    ) -> None:
        """Create a new trade from opening executions.

        Args:
            opening_execs: Executions that open the new trade
            closing_execs: Any closing executions in the same group (for roll detection)
            closing_legs: Leg keys of closing executions
            force_assignment: Force this trade to be marked as assignment
        """
        opening_deltas = self._calculate_deltas(opening_execs)
        opening_legs = frozenset(self.get_leg_key(e) for e in opening_execs)

        # Check if this is a roll or assignment
        is_roll = False
        is_assignment = force_assignment

        if not is_assignment and bool(closing_execs) and closing_legs.isdisjoint(opening_legs):
            closing_has_options = any(leg != "STK" for leg in closing_legs)
            opening_has_stock = "STK" in opening_legs
            opening_has_options = any(leg != "STK" for leg in opening_legs)

            if closing_has_options and opening_has_stock and not opening_has_options:
                is_assignment = True
            elif closing_has_options and opening_has_options:
                is_roll = True

        new_trade = TradeGroup(underlying=self.underlying)
        if is_roll:
            new_trade.roll_type = "ROLL"
        if is_assignment:
            new_trade.is_assignment = True

        for exec in opening_execs:
            new_trade.add_execution(exec)

        # Record opening position
        for leg, delta in opening_deltas.items():
            new_trade.opening_position[leg] = delta

        # Apply opening deltas to position
        self._apply_deltas(opening_deltas, opening_execs)

        # Store as open trade
        self.open_trades[opening_legs] = new_trade

    def _process_execution_group(self, group: list[Execution]) -> None:
        """Process a group of simultaneous executions (DEPRECATED - use v2).

        Args:
            group: List of executions in this group
        """
        # Analyze what this group does
        group_legs = {self.get_leg_key(e) for e in group}
        group_deltas = self._calculate_deltas(group)

        # Determine the event type
        event = self._determine_event(group_deltas, group_legs, group[0].execution_time)

        # Handle the event
        if event == TradeEvent.OPEN:
            self._handle_open(group, group_deltas)
        elif event == TradeEvent.CLOSE:
            self._handle_close(group, group_deltas)
        elif event == TradeEvent.ROLL:
            self._handle_roll(group, group_deltas)
        elif event in (TradeEvent.ADD, TradeEvent.PARTIAL_CLOSE, TradeEvent.ADJUST):
            self._handle_continuation(group, group_deltas)

    def _calculate_deltas(self, group: list[Execution]) -> dict[str, int]:
        """Calculate position deltas from execution group.

        Args:
            group: List of executions

        Returns:
            Dict of leg_key -> quantity delta
        """
        deltas: dict[str, int] = {}
        for exec in group:
            leg_key = self.get_leg_key(exec)
            delta = exec.quantity if exec.side == "BOT" else -exec.quantity
            deltas[leg_key] = deltas.get(leg_key, 0) + delta
        return deltas

    def _determine_event(
        self,
        group_deltas: dict[str, int],
        group_legs: set[str],
        exec_time: datetime
    ) -> TradeEvent:
        """Determine what trade event this execution group represents.

        Args:
            group_deltas: Position changes from this group
            group_legs: Set of legs affected
            exec_time: Execution timestamp

        Returns:
            The trade event type
        """
        was_flat = self.is_flat()
        active_legs = self.get_active_legs()

        # Calculate what position will be after applying deltas
        will_be_flat = self._will_be_flat_after(group_deltas)

        # Case 1: Starting from flat - this is an OPEN
        if was_flat:
            return TradeEvent.OPEN

        # Case 2: Ending flat - this is a CLOSE
        if will_be_flat:
            return TradeEvent.CLOSE

        # Case 3: Check for roll - closing some legs while opening different legs
        closing_legs, opening_legs = self._identify_close_open_legs(group_deltas)

        if closing_legs and opening_legs and closing_legs.isdisjoint(opening_legs):
            # Different legs being closed and opened
            # Check if this is same trading session (same day for roll detection)
            if self.last_trade_close_time:
                time_since_last_close = exec_time - self.last_trade_close_time
                if time_since_last_close <= self.ROLL_WINDOW:
                    return TradeEvent.ROLL

        # Case 4: Check for adjustment (partial overlap with current trade legs)
        if group_legs != active_legs and not group_legs.issubset(active_legs):
            return TradeEvent.ADJUST

        # Case 5: Adding or reducing within same legs
        is_reducing = any(
            self._is_closing_delta(leg, delta)
            for leg, delta in group_deltas.items()
        )

        if is_reducing:
            return TradeEvent.PARTIAL_CLOSE

        return TradeEvent.ADD

    def _will_be_flat_after(self, deltas: dict[str, int]) -> bool:
        """Check if position will be flat after applying deltas."""
        new_position = {k: v.quantity for k, v in self.position.items()}
        for leg, delta in deltas.items():
            new_position[leg] = new_position.get(leg, 0) + delta
        return all(qty == 0 for qty in new_position.values())

    def _identify_close_open_legs(self, deltas: dict[str, int]) -> tuple[set[str], set[str]]:
        """Identify which legs are being closed vs opened.

        Args:
            deltas: Position changes

        Returns:
            Tuple of (closing_legs, opening_legs)
        """
        closing_legs = set()
        opening_legs = set()

        for leg, delta in deltas.items():
            current_qty = self.position.get(leg, LegPosition(leg)).quantity

            if current_qty == 0:
                # No current position - this is opening
                opening_legs.add(leg)
            elif self._is_closing_delta(leg, delta):
                closing_legs.add(leg)
            else:
                # Adding to existing position
                pass

        return closing_legs, opening_legs

    def _is_closing_delta(self, leg: str, delta: int) -> bool:
        """Check if delta is closing (reducing) the position.

        Args:
            leg: Leg key
            delta: Position change

        Returns:
            True if this delta reduces the position toward zero
        """
        current_qty = self.position.get(leg, LegPosition(leg)).quantity
        if current_qty == 0:
            return False
        # Closing if delta has opposite sign of current position
        return (current_qty > 0 and delta < 0) or (current_qty < 0 and delta > 0)

    def _handle_open(self, group: list[Execution], deltas: dict[str, int]) -> None:
        """Handle OPEN event - new trade starting from flat."""
        # Start new trade
        self.current_trade = TradeGroup(underlying=self.underlying)

        for exec in group:
            self.current_trade.add_execution(exec)

        # Record opening position
        for leg, delta in deltas.items():
            self.current_trade.opening_position[leg] = delta

        # Update position state
        self._apply_deltas(deltas, group)

    def _handle_close(self, group: list[Execution], deltas: dict[str, int]) -> None:
        """Handle CLOSE event - trade closing to flat."""
        if self.current_trade is None:
            self.current_trade = TradeGroup(underlying=self.underlying)

        for exec in group:
            self.current_trade.add_execution(exec)

        # Apply deltas
        self._apply_deltas(deltas, group)

        # Finalize trade
        self.current_trade.status = "CLOSED"
        self.completed_trades.append(self.current_trade)

        # Record close time for roll detection
        self.last_trade_close_time = max(e.execution_time for e in group)

        # Reset for next trade
        self.current_trade = None

    def _handle_roll(self, group: list[Execution], deltas: dict[str, int]) -> None:
        """Handle ROLL event - closing old position and opening new one."""
        # Split executions into closes and opens
        close_execs = []
        open_execs = []

        for exec in group:
            leg = self.get_leg_key(exec)
            current_qty = self.position.get(leg, LegPosition(leg)).quantity

            if exec.open_close_indicator == 'C':
                close_execs.append(exec)
            elif exec.open_close_indicator == 'O':
                open_execs.append(exec)
            elif current_qty != 0 and self._is_closing_delta(leg, deltas.get(leg, 0)):
                close_execs.append(exec)
            else:
                open_execs.append(exec)

        # First, close the current trade with closing executions
        if self.current_trade and close_execs:
            for exec in close_execs:
                self.current_trade.add_execution(exec)

            self.current_trade.status = "CLOSED"
            self.completed_trades.append(self.current_trade)
            self.last_trade_close_time = max(e.execution_time for e in close_execs)
        else:
            pass

        # Apply all deltas
        self._apply_deltas(deltas, group)

        # Start new trade with opening executions (linked to old trade)
        if open_execs:
            self.current_trade = TradeGroup(underlying=self.underlying)
            self.current_trade.roll_type = "ROLL"

            for exec in open_execs:
                self.current_trade.add_execution(exec)
                leg = self.get_leg_key(exec)
                delta = exec.quantity if exec.side == "BOT" else -exec.quantity
                self.current_trade.opening_position[leg] = \
                    self.current_trade.opening_position.get(leg, 0) + delta
        else:
            self.current_trade = None

    def _handle_continuation(self, group: list[Execution], deltas: dict[str, int]) -> None:
        """Handle ADD, PARTIAL_CLOSE, or ADJUST events."""
        if self.current_trade is None:
            self.current_trade = TradeGroup(underlying=self.underlying)
            # Record opening position from current state
            for leg, pos in self.position.items():
                if not pos.is_flat:
                    self.current_trade.opening_position[leg] = pos.quantity

        for exec in group:
            self.current_trade.add_execution(exec)

        self._apply_deltas(deltas, group)

    def _apply_deltas(self, deltas: dict[str, int], group: list[Execution]) -> None:
        """Apply position deltas and update state.

        Args:
            deltas: Position changes to apply
            group: Source executions for cost tracking
        """
        # Build cost map from executions
        cost_by_leg: dict[str, Decimal] = {}
        for exec in group:
            leg = self.get_leg_key(exec)
            multiplier = exec.multiplier or 1
            cost = exec.price * abs(exec.quantity) * multiplier
            if exec.side == "SLD":
                cost = -cost
            cost_by_leg[leg] = cost_by_leg.get(leg, Decimal("0.00")) + cost

        # Apply to position
        for leg, delta in deltas.items():
            if leg not in self.position:
                self.position[leg] = LegPosition(leg_key=leg)

            pos = self.position[leg]
            pos.quantity += delta
            pos.total_cost += cost_by_leg.get(leg, Decimal("0.00"))


def classify_strategy_from_opening(opening_position: dict[str, int]) -> str:
    """Classify strategy based on opening position structure.

    Args:
        opening_position: Dict of leg_key -> quantity (positive=long, negative=short)

    Returns:
        Strategy classification string
    """
    legs = {k: v for k, v in opening_position.items() if v != 0}

    if len(legs) == 0:
        return "Unknown"

    if len(legs) == 1:
        leg_key = list(legs.keys())[0]
        qty = list(legs.values())[0]

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

    if len(legs) == 2:
        leg_keys = list(legs.keys())
        parts1 = leg_keys[0].split("_")
        parts2 = leg_keys[1].split("_")

        if len(parts1) == 3 and len(parts2) == 3:
            exp1, strike1_str, right1 = parts1
            exp2, strike2_str, right2 = parts2

            if exp1 == exp2 and right1 == right2:
                # Same expiration and type = vertical spread
                try:
                    strike1 = float(strike1_str)
                    strike2 = float(strike2_str)
                    qty1 = legs[leg_keys[0]]
                    qty2 = legs[leg_keys[1]]

                    # Sort by strike
                    if strike1 > strike2:
                        strike1, strike2 = strike2, strike1
                        qty1, qty2 = qty2, qty1

                    # Now strike1 is lower, strike2 is higher
                    lower_is_long = qty1 > 0
                    upper_is_long = qty2 > 0

                    if right1 == "C":
                        if lower_is_long and not upper_is_long:
                            return "Bull Call Spread"
                        elif not lower_is_long and upper_is_long:
                            return "Bear Call Spread"
                    else:
                        if lower_is_long and not upper_is_long:
                            return "Bull Put Spread"
                        elif not lower_is_long and upper_is_long:
                            return "Bear Put Spread"
                except (ValueError, IndexError):
                    pass

                # Fallback
                return f"Vertical {'Call' if right1 == 'C' else 'Put'} Spread"

            elif exp1 != exp2 and right1 == right2:
                # Different expiration, same type = Calendar spread
                return f"Calendar {'Call' if right1 == 'C' else 'Put'} Spread"

            elif right1 != right2:
                # Different types = Straddle or Strangle
                try:
                    strike1 = float(strike1_str)
                    strike2 = float(strike2_str)
                    if strike1 == strike2:
                        return "Straddle"
                    return "Strangle"
                except (ValueError, IndexError):
                    pass

        return "Two-Leg"

    if len(legs) == 3:
        return "Butterfly"

    if len(legs) == 4:
        calls = [k for k in legs.keys() if k.endswith("_C")]
        puts = [k for k in legs.keys() if k.endswith("_P")]

        if len(calls) == 2 and len(puts) == 2:
            return "Iron Condor"

        return "Four-Leg"

    return f"{len(legs)}-Leg Complex"
