"""Position State Machine - Core algorithm for trade grouping.

This module implements a state-based approach to grouping executions into trades:
1. Maintains position state per underlying/leg
2. Detects trade events: OPEN, ADD, PARTIAL_CLOSE, CLOSE, ROLL
3. Creates proper trade boundaries
4. Links rolls and adjustments
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional

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
    parent_trade_id: Optional[int] = None
    roll_type: Optional[str] = None  # "ROLL" or "ADJUST" or None
    is_assignment: bool = False  # True if this trade is from option assignment/exercise
    assigned_from_trade_id: Optional[int] = None  # ID of the option trade that was assigned

    def add_execution(self, exec: Execution) -> None:
        """Add execution to this trade group."""
        self.executions.append(exec)

    @property
    def execution_ids(self) -> list[int]:
        return [e.id for e in self.executions]

    @property
    def opened_at(self) -> Optional[datetime]:
        if not self.executions:
            return None
        return min(e.execution_time for e in self.executions)

    @property
    def closed_at(self) -> Optional[datetime]:
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
        self.last_trade_close_time: Optional[datetime] = None

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
                # Check if the legs are flat
                trade_legs = frozenset(trade.opening_position.keys())
                all_flat = all(
                    self.position.get(leg, LegPosition(leg)).quantity == 0
                    for leg in trade_legs
                )
                trade.status = "CLOSED" if all_flat else "OPEN"
                self.completed_trades.append(trade)

        return self.completed_trades

    def _group_simultaneous(self, executions: list[Execution]) -> list[list[Execution]]:
        """Group near-simultaneous executions.

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

        for exec in executions:
            if not current_group:
                current_group = [exec]
                group_start_time = exec.execution_time
            else:
                time_diff = exec.execution_time - group_start_time
                if time_diff <= self.SIMULTANEOUS_WINDOW:
                    current_group.append(exec)
                else:
                    groups.append(current_group)
                    current_group = [exec]
                    group_start_time = exec.execution_time

        if current_group:
            groups.append(current_group)

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
        group_legs = frozenset(self.get_leg_key(e) for e in group)
        group_deltas = self._calculate_deltas(group)
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
        if closing_execs:
            closing_deltas = self._calculate_deltas(closing_execs)

            for exec in closing_execs:
                leg = frozenset([self.get_leg_key(exec)])
                matching_trade = self._find_matching_trade(leg)

                if matching_trade is not None:
                    trade_key, trade = matching_trade
                    trade.add_execution(exec)

            # Apply closing deltas to position
            self._apply_deltas(closing_deltas, closing_execs)

            # Check if any trades are now fully closed
            # Need to check all active legs of each trade
            trades_to_close = []
            for trade_key, trade in list(self.open_trades.items()):
                # Get ALL legs this trade has touched (from opening_position + any added legs)
                trade_legs = set(trade.opening_position.keys())
                # Also check executions for any legs
                for exec in trade.executions:
                    trade_legs.add(self.get_leg_key(exec))

                # Check if all legs are flat
                all_flat = all(
                    self.position.get(leg, LegPosition(leg)).quantity == 0
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

        # Process opening executions - create new trade(s)
        if opening_execs:
            opening_deltas = self._calculate_deltas(opening_execs)

            # Check if this is a roll or assignment (opening new legs right after closing)
            is_roll = False
            is_assignment = False

            if bool(closing_execs) and closing_legs.isdisjoint(opening_legs):
                # Determine if this is a roll (option -> option) or assignment (option -> stock)
                closing_has_options = any(leg != "STK" for leg in closing_legs)
                opening_has_stock = "STK" in opening_legs
                opening_has_options = any(leg != "STK" for leg in opening_legs)

                if closing_has_options and opening_has_stock and not opening_has_options:
                    # Option closed, stock opened = Assignment (put assigned or call exercised)
                    is_assignment = True
                elif closing_has_options and opening_has_options:
                    # Option closed, option opened = Roll
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

    def _find_matching_trade(self, group_legs: frozenset[str]) -> Optional[tuple[frozenset[str], TradeGroup]]:
        """Find an open trade that matches the given legs.

        A trade matches if the group legs overlap with the trade's legs.
        We need to check both the original trade_key AND any legs added via rolls.

        Args:
            group_legs: Set of leg keys in the execution group

        Returns:
            Tuple of (trade_key, trade) or None if no match
        """
        for trade_key, trade in self.open_trades.items():
            # Get all legs this trade has touched
            all_trade_legs = set(trade_key)
            all_trade_legs.update(trade.opening_position.keys())
            for exec in trade.executions:
                all_trade_legs.add(self.get_leg_key(exec))

            # Check if group legs overlap with any of the trade's legs
            if group_legs & all_trade_legs:
                return (trade_key, trade)
        return None

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
            old_trade = self.current_trade
            self.last_trade_close_time = max(e.execution_time for e in close_execs)
        else:
            old_trade = None

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
