"""Trade service for manual trade operations."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.models.execution import Execution
from trading_journal.models.trade import Trade


class TradeService:
    """Service for manual trade creation and management."""

    def __init__(self, session: AsyncSession):
        """Initialize trade service.

        Args:
            session: Database session
        """
        self.session = session

    async def create_manual_trade(
        self,
        execution_ids: list[int],
        strategy_type: str,
        notes: str | None = None,
        tags: str | None = None,
        auto_match_closes: bool = True,
    ) -> Trade:
        """Create a trade from manually selected executions.

        When opening executions (BTO/STO) are provided and auto_match_closes is True,
        automatically finds and includes matching closing transactions using FIFO.

        Args:
            execution_ids: List of execution database IDs to group
            strategy_type: Strategy type (e.g., "Single", "Vertical Call Spread")
            notes: Optional trade notes
            tags: Optional comma-separated tags
            auto_match_closes: Whether to auto-match closing transactions for opens

        Returns:
            Created Trade object

        Raises:
            ValueError: If executions invalid or already assigned
        """
        if not execution_ids:
            raise ValueError("At least one execution ID is required")

        # Fetch executions
        stmt = select(Execution).where(Execution.id.in_(execution_ids))
        result = await self.session.execute(stmt)
        executions = list(result.scalars().all())

        if len(executions) != len(execution_ids):
            found_ids = {e.id for e in executions}
            missing = set(execution_ids) - found_ids
            raise ValueError(f"Executions not found: {missing}")

        # Verify all executions are unassigned
        already_assigned = [e for e in executions if e.trade_id is not None]
        if already_assigned:
            ids = [e.id for e in already_assigned]
            raise ValueError(f"Executions already assigned to trades: {ids}")

        # Auto-match closing transactions if enabled
        if auto_match_closes:
            matched_closes = await self._auto_match_closes_for_opens(executions)
            if matched_closes:
                executions.extend(matched_closes)

        # Calculate trade metrics
        metrics = self._calculate_trade_metrics(executions)

        # Create trade
        trade = Trade(
            underlying=metrics["underlying"],
            strategy_type=strategy_type,
            status=metrics["status"],
            opened_at=metrics["opened_at"],
            closed_at=metrics["closed_at"],
            realized_pnl=metrics["realized_pnl"],
            unrealized_pnl=metrics["unrealized_pnl"],
            total_pnl=metrics["total_pnl"],
            opening_cost=metrics["opening_cost"],
            closing_proceeds=metrics["closing_proceeds"],
            total_commission=metrics["total_commission"],
            num_legs=metrics["num_legs"],
            num_executions=metrics["num_executions"],
            notes=notes,
            tags=tags,
        )
        self.session.add(trade)
        await self.session.flush()

        # Link executions to trade
        for execution in executions:
            execution.trade_id = trade.id

        await self.session.commit()
        await self.session.refresh(trade)
        return trade

    async def _auto_match_closes_for_opens(
        self, executions: list[Execution]
    ) -> list[Execution]:
        """Find and return matching closing transactions for opening executions.

        Uses FIFO matching: for each opening execution, find the oldest unassigned
        closing transaction for the same contract.

        Args:
            executions: List of executions (may contain opens and closes)

        Returns:
            List of additional closing executions to include
        """
        matched_closes: list[Execution] = []
        matched_close_ids: set[int] = set()

        # Get only opening executions
        opens = [e for e in executions if e.open_close_indicator == 'O']

        for open_exec in opens:
            # Find matching closes for this open
            closes = await self._find_matching_closes_fifo(open_exec, matched_close_ids)
            for close in closes:
                if close.id not in matched_close_ids:
                    matched_closes.append(close)
                    matched_close_ids.add(close.id)

        return matched_closes

    async def _find_matching_closes_fifo(
        self, open_execution: Execution, exclude_ids: set[int]
    ) -> list[Execution]:
        """Find matching closing transactions for an opening execution using FIFO.

        Args:
            open_execution: The opening execution to find closes for
            exclude_ids: Set of execution IDs to exclude (already matched)

        Returns:
            List of matching closing Execution models (up to the open quantity)
        """
        # Build query for matching closes
        stmt = select(Execution).where(
            Execution.underlying == open_execution.underlying,
            Execution.open_close_indicator == 'C',
            Execution.trade_id.is_(None),  # Unassigned only
            Execution.execution_time >= open_execution.execution_time,  # After the open
        )

        # Exclude already-matched closes
        if exclude_ids:
            stmt = stmt.where(Execution.id.notin_(exclude_ids))

        # For options, match by contract details
        if open_execution.security_type == 'OPT':
            stmt = stmt.where(
                Execution.security_type == 'OPT',
                Execution.strike == open_execution.strike,
                Execution.expiration == open_execution.expiration,
                Execution.option_type == open_execution.option_type,
            )
        else:
            # For stocks, just match the security type
            stmt = stmt.where(Execution.security_type == 'STK')

        # Order by execution time (FIFO)
        stmt = stmt.order_by(Execution.execution_time)

        result = await self.session.execute(stmt)
        closes = list(result.scalars().all())

        # Return closes up to the quantity needed
        matched_closes = []
        remaining_qty = open_execution.quantity

        for close in closes:
            if remaining_qty <= 0:
                break
            matched_closes.append(close)
            remaining_qty -= close.quantity

        return matched_closes

    async def update_trade_executions(
        self,
        trade_id: int,
        add_ids: list[int] | None = None,
        remove_ids: list[int] | None = None,
    ) -> Trade | None:
        """Add or remove executions from an existing trade.

        Args:
            trade_id: Trade database ID
            add_ids: Execution IDs to add to the trade
            remove_ids: Execution IDs to remove from the trade

        Returns:
            Updated Trade object, or None if trade was deleted

        Raises:
            ValueError: If trade not found or executions invalid
        """
        # Get trade
        stmt = select(Trade).where(Trade.id == trade_id)
        result = await self.session.execute(stmt)
        trade = result.scalar_one_or_none()

        if not trade:
            raise ValueError(f"Trade not found: {trade_id}")

        # Handle removals
        if remove_ids:
            stmt = select(Execution).where(
                Execution.id.in_(remove_ids),
                Execution.trade_id == trade_id,
            )
            result = await self.session.execute(stmt)
            executions_to_remove = list(result.scalars().all())

            for execution in executions_to_remove:
                execution.trade_id = None

        # Handle additions
        if add_ids:
            stmt = select(Execution).where(Execution.id.in_(add_ids))
            result = await self.session.execute(stmt)
            executions_to_add = list(result.scalars().all())

            # Verify all are unassigned
            already_assigned = [e for e in executions_to_add if e.trade_id is not None]
            if already_assigned:
                ids = [e.id for e in already_assigned]
                raise ValueError(f"Executions already assigned: {ids}")

            for execution in executions_to_add:
                execution.trade_id = trade_id

        # Get current executions for this trade
        stmt = select(Execution).where(Execution.trade_id == trade_id)
        result = await self.session.execute(stmt)
        current_executions = list(result.scalars().all())

        if not current_executions:
            # No executions left - delete trade
            await self.session.delete(trade)
            await self.session.commit()
            return None

        # Recalculate metrics
        metrics = self._calculate_trade_metrics(current_executions)

        # Update trade
        trade.status = metrics["status"]
        trade.opened_at = metrics["opened_at"]
        trade.closed_at = metrics["closed_at"]
        trade.realized_pnl = metrics["realized_pnl"]
        trade.unrealized_pnl = metrics["unrealized_pnl"]
        trade.total_pnl = metrics["total_pnl"]
        trade.opening_cost = metrics["opening_cost"]
        trade.closing_proceeds = metrics["closing_proceeds"]
        trade.total_commission = metrics["total_commission"]
        trade.num_legs = metrics["num_legs"]
        trade.num_executions = metrics["num_executions"]

        await self.session.commit()
        await self.session.refresh(trade)
        return trade

    async def merge_trades(self, trade_ids: list[int]) -> Trade:
        """Merge multiple trades into a single trade.

        All executions from the source trades are combined into the first trade.
        The other trades are deleted. Preserves notes and tags from the first trade.

        Args:
            trade_ids: List of trade IDs to merge (minimum 2)

        Returns:
            The merged Trade object

        Raises:
            ValueError: If trades not found, different underlyings, or invalid count
        """
        if len(trade_ids) < 2:
            raise ValueError("At least 2 trades required for merge")

        # Fetch all trades
        stmt = select(Trade).where(Trade.id.in_(trade_ids))
        result = await self.session.execute(stmt)
        trades = list(result.scalars().all())

        if len(trades) != len(trade_ids):
            found_ids = {t.id for t in trades}
            missing = set(trade_ids) - found_ids
            raise ValueError(f"Trades not found: {missing}")

        # Verify all trades have the same underlying
        underlyings = {t.underlying for t in trades}
        if len(underlyings) > 1:
            raise ValueError(f"Cannot merge trades with different underlyings: {underlyings}")

        # Keep the first trade (by ID), merge others into it
        trades_sorted = sorted(trades, key=lambda t: t.id)
        primary_trade = trades_sorted[0]
        trades_to_delete = trades_sorted[1:]

        # Collect all executions from trades being merged
        all_executions = []
        for trade in trades:
            stmt = select(Execution).where(Execution.trade_id == trade.id)
            result = await self.session.execute(stmt)
            executions = list(result.scalars().all())
            all_executions.extend(executions)

        # Reassign all executions to primary trade
        for execution in all_executions:
            execution.trade_id = primary_trade.id

        # Delete the other trades
        for trade in trades_to_delete:
            await self.session.delete(trade)

        # Recalculate metrics for the merged trade
        metrics = self._calculate_trade_metrics(all_executions)

        # Update primary trade
        primary_trade.status = metrics["status"]
        primary_trade.opened_at = metrics["opened_at"]
        primary_trade.closed_at = metrics["closed_at"]
        primary_trade.realized_pnl = metrics["realized_pnl"]
        primary_trade.unrealized_pnl = metrics["unrealized_pnl"]
        primary_trade.total_pnl = metrics["total_pnl"]
        primary_trade.opening_cost = metrics["opening_cost"]
        primary_trade.closing_proceeds = metrics["closing_proceeds"]
        primary_trade.total_commission = metrics["total_commission"]
        primary_trade.num_legs = metrics["num_legs"]
        primary_trade.num_executions = metrics["num_executions"]

        await self.session.commit()
        await self.session.refresh(primary_trade)
        return primary_trade

    async def ungroup_trade(self, trade_id: int) -> bool:
        """Remove all executions from a trade and delete it.

        Args:
            trade_id: Trade database ID

        Returns:
            True if trade was deleted, False if not found
        """
        # Get trade
        stmt = select(Trade).where(Trade.id == trade_id)
        result = await self.session.execute(stmt)
        trade = result.scalar_one_or_none()

        if not trade:
            return False

        # Unlink all executions
        stmt = select(Execution).where(Execution.trade_id == trade_id)
        result = await self.session.execute(stmt)
        executions = list(result.scalars().all())

        for execution in executions:
            execution.trade_id = None

        # Delete trade
        await self.session.delete(trade)
        await self.session.commit()
        return True

    async def suggest_grouping(
        self,
        execution_ids: list[int] | None = None,
    ) -> list[dict]:
        """Run auto-grouping algorithm and return suggestions without saving.

        Uses the existing TradeGroupingService logic to suggest groupings.

        Args:
            execution_ids: Optional list of specific execution IDs to group.
                          If None, processes all unassigned executions.

        Returns:
            List of suggested groups with execution IDs and metadata
        """
        # Get executions to process
        if execution_ids:
            stmt = select(Execution).where(
                Execution.id.in_(execution_ids),
                Execution.trade_id.is_(None),
            )
        else:
            stmt = select(Execution).where(Execution.trade_id.is_(None))

        stmt = stmt.order_by(Execution.execution_time)
        result = await self.session.execute(stmt)
        executions = list(result.scalars().all())

        if not executions:
            return []

        # Use the grouping service's algorithm to build suggested groups
        # We'll simulate the grouping without saving
        suggestions = self._build_group_suggestions(executions)
        return suggestions

    def _build_group_suggestions(self, executions: list[Execution]) -> list[dict]:
        """Build group suggestions from executions using position state logic.

        Args:
            executions: List of unassigned executions

        Returns:
            List of suggested group dictionaries
        """
        from collections import defaultdict
        from datetime import timedelta

        suggestions = []

        # Group by underlying first
        by_underlying = defaultdict(list)
        for exec in executions:
            by_underlying[exec.underlying].append(exec)

        for _underlying, execs in by_underlying.items():
            # Sort chronologically
            sorted_execs = sorted(execs, key=lambda e: e.execution_time)

            # Group simultaneous executions
            TIME_WINDOW = timedelta(seconds=2)
            groups = []
            current_group = []
            group_start_time = None

            for exec in sorted_execs:
                if not current_group:
                    current_group = [exec]
                    group_start_time = exec.execution_time
                else:
                    time_diff = exec.execution_time - group_start_time
                    if time_diff <= TIME_WINDOW:
                        current_group.append(exec)
                    else:
                        groups.append(current_group)
                        current_group = [exec]
                        group_start_time = exec.execution_time

            if current_group:
                groups.append(current_group)

            # Process groups with position state machine
            cumulative_position: dict[str, int] = {}
            current_trade_execs: list[Execution] = []
            current_trade_legs: set[str] = set()

            for group in groups:
                group_legs = {self._get_leg_key(e) for e in group}

                if not current_trade_execs:
                    # Start new trade
                    current_trade_execs = list(group)
                    for exec in group:
                        self._update_position(cumulative_position, exec)
                    current_trade_legs = group_legs

                elif group_legs.issubset(current_trade_legs):
                    # Add to current trade
                    current_trade_execs.extend(group)
                    for exec in group:
                        self._update_position(cumulative_position, exec)

                    # Check if flat
                    if self._legs_are_flat(current_trade_legs, cumulative_position):
                        # Save suggestion
                        suggestion = self._create_suggestion(current_trade_execs)
                        suggestions.append(suggestion)
                        current_trade_execs = []
                        current_trade_legs = set()

                elif group_legs.isdisjoint(current_trade_legs):
                    # Different legs - save current and start new
                    if current_trade_execs:
                        suggestion = self._create_suggestion(current_trade_execs)
                        suggestions.append(suggestion)

                    current_trade_execs = list(group)
                    for exec in group:
                        self._update_position(cumulative_position, exec)
                    current_trade_legs = group_legs

                else:
                    # Partial overlap - save current and start new
                    if current_trade_execs:
                        suggestion = self._create_suggestion(current_trade_execs)
                        suggestions.append(suggestion)

                    current_trade_execs = list(group)
                    for exec in group:
                        self._update_position(cumulative_position, exec)
                    current_trade_legs = group_legs

            # Handle remaining
            if current_trade_execs:
                suggestion = self._create_suggestion(current_trade_execs)
                suggestions.append(suggestion)

        return suggestions

    def _create_suggestion(self, executions: list[Execution]) -> dict:
        """Create a suggestion dict from executions.

        Args:
            executions: List of executions in the suggested group

        Returns:
            Suggestion dictionary
        """
        metrics = self._calculate_trade_metrics(executions)

        # Build legs summary from executions with fill details
        legs = []
        leg_map: dict[str, dict] = {}

        for exec in executions:
            leg_key = self._get_leg_key(exec)
            if leg_key not in leg_map:
                leg_map[leg_key] = {
                    "option_type": exec.option_type,
                    "strike": float(exec.strike) if exec.strike else None,
                    "expiration": exec.expiration.strftime("%Y-%m-%d") if exec.expiration else None,
                    "security_type": exec.security_type,
                    "total_quantity": 0,
                    "actions": [],
                    "fills": [],  # Detailed fill information
                }

            # Track quantity and action
            action = "BTC" if exec.side == "BOT" and exec.open_close_indicator == "C" else \
                     "BTO" if exec.side == "BOT" else \
                     "STC" if exec.side == "SLD" and exec.open_close_indicator == "C" else "STO"

            delta = exec.quantity if exec.side == "BOT" else -exec.quantity
            leg_map[leg_key]["total_quantity"] += delta
            if action not in leg_map[leg_key]["actions"]:
                leg_map[leg_key]["actions"].append(action)

            # Add fill detail
            leg_map[leg_key]["fills"].append({
                "id": exec.id,
                "action": action,
                "quantity": exec.quantity,
                "price": float(exec.price),
                "execution_time": exec.execution_time.strftime("%Y-%m-%d %H:%M:%S"),
                "net_amount": float(exec.net_amount),
            })

        legs = list(leg_map.values())

        # Get date range
        dates = [e.execution_time for e in executions]
        open_date = min(dates).strftime("%Y-%m-%d") if dates else None
        close_date = max(dates).strftime("%Y-%m-%d") if dates else None

        return {
            "execution_ids": [e.id for e in executions],
            "suggested_strategy": self._classify_strategy(executions),
            "underlying": metrics["underlying"],
            "total_pnl": float(metrics["total_pnl"]),
            "status": metrics["status"],
            "legs": legs,
            "open_date": open_date,
            "close_date": close_date if metrics["status"] == "CLOSED" else None,
            "num_executions": len(executions),
        }

    def _calculate_trade_metrics(self, executions: list[Execution]) -> dict:
        """Calculate trade metrics from a list of executions.

        Args:
            executions: List of execution objects

        Returns:
            Dictionary with trade metrics
        """
        if not executions:
            raise ValueError("Cannot calculate metrics for empty execution list")

        # Get underlying (should all be same)
        underlyings = {e.underlying for e in executions}
        if len(underlyings) > 1:
            raise ValueError(f"Executions have multiple underlyings: {underlyings}")
        underlying = executions[0].underlying

        # Calculate timestamps
        opened_at = min(e.execution_time for e in executions)

        # Build position ledger to determine if closed
        position_ledger: dict[str, int] = {}
        for exec in executions:
            leg_key = self._get_leg_key(exec)
            delta = exec.quantity if exec.side == "BOT" else -exec.quantity
            position_ledger[leg_key] = position_ledger.get(leg_key, 0) + delta

        is_closed = all(qty == 0 for qty in position_ledger.values())
        closed_at = max(e.execution_time for e in executions) if is_closed else None

        # Calculate costs and P&L
        total_commission = sum(e.commission for e in executions)

        if is_closed:
            # All executions contributed to opening or closing
            opening_cost = sum(
                abs(e.net_amount) for e in executions if e.side == "BOT"
            )
            closing_proceeds = sum(
                abs(e.net_amount) for e in executions if e.side == "SLD"
            )
            # P&L = proceeds - cost - commission
            realized_pnl = closing_proceeds - opening_cost - total_commission
        else:
            # Trade still open
            bot_cost = sum(abs(e.net_amount) for e in executions if e.side == "BOT")
            sld_credit = sum(abs(e.net_amount) for e in executions if e.side == "SLD")
            opening_cost = bot_cost - sld_credit
            closing_proceeds = Decimal("0.00")
            realized_pnl = Decimal("0.00")

        return {
            "underlying": underlying,
            "opened_at": opened_at,
            "closed_at": closed_at,
            "status": "CLOSED" if is_closed else "OPEN",
            "opening_cost": opening_cost,
            "closing_proceeds": closing_proceeds,
            "realized_pnl": realized_pnl,
            "unrealized_pnl": Decimal("0.00"),
            "total_pnl": realized_pnl,
            "total_commission": total_commission,
            "num_legs": len(position_ledger),
            "num_executions": len(executions),
        }

    def _get_leg_key(self, execution: Execution) -> str:
        """Generate unique key for a position leg.

        Args:
            execution: Execution object

        Returns:
            Unique leg key string
        """
        if execution.security_type == "OPT":
            expiry = execution.expiration.strftime("%Y%m%d") if execution.expiration else ""
            return f"{expiry}_{execution.strike}_{execution.option_type}"
        return "STK"

    def _update_position(self, position: dict[str, int], execution: Execution) -> None:
        """Update position dict with execution.

        Args:
            position: Position dictionary (leg_key -> quantity)
            execution: Execution to apply
        """
        leg_key = self._get_leg_key(execution)
        delta = execution.quantity if execution.side == "BOT" else -execution.quantity
        position[leg_key] = position.get(leg_key, 0) + delta

    def _legs_are_flat(self, legs: set[str], position: dict[str, int]) -> bool:
        """Check if all legs are at zero quantity.

        Args:
            legs: Set of leg keys
            position: Current position dictionary

        Returns:
            True if all legs are flat
        """
        return all(position.get(leg, 0) == 0 for leg in legs)

    def _classify_strategy(self, executions: list[Execution]) -> str:
        """Classify strategy based on execution structure.

        For closed trades, we look at the OPENING position to determine strategy.
        For open trades, we look at the current position.

        Args:
            executions: List of executions

        Returns:
            Strategy classification string
        """
        # Build position ledger from opening executions only
        # This tells us what the original position was
        opening_position: dict[str, int] = {}
        for exec in executions:
            if exec.open_close_indicator == 'O':
                leg_key = self._get_leg_key(exec)
                delta = exec.quantity if exec.side == "BOT" else -exec.quantity
                opening_position[leg_key] = opening_position.get(leg_key, 0) + delta

        # If no opening executions found (all closing), infer original position
        # from the closing executions (opposite direction)
        if not opening_position:
            for exec in executions:
                leg_key = self._get_leg_key(exec)
                # Closing trades: BTC means was short, STC means was long
                # So we invert: BOT closing means original was short (-), SLD closing means original was long (+)
                if exec.open_close_indicator == 'C':
                    delta = -exec.quantity if exec.side == "BOT" else exec.quantity
                    opening_position[leg_key] = opening_position.get(leg_key, 0) + delta

        # Use opening position for classification
        legs = {k: v for k, v in opening_position.items() if v != 0}
        len(opening_position)

        if len(legs) == 0:
            # Fallback to counting unique leg keys
            all_legs = {self._get_leg_key(e) for e in executions}
            if len(all_legs) == 1:
                return "Single"
            return f"{len(all_legs)}-Leg Complex"

        if len(legs) == 1:
            return "Single"

        if len(legs) == 2:
            leg_keys = list(legs.keys())
            parts1 = leg_keys[0].split("_")
            parts2 = leg_keys[1].split("_")

            if len(parts1) == 3 and len(parts2) == 3:
                exp1, strike1_str, right1 = parts1
                exp2, strike2_str, right2 = parts2

                if exp1 == exp2 and right1 == right2:
                    # Same expiration and same type = vertical spread
                    # Determine Bull vs Bear based on OPENING position
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
                        # qty > 0 = long, qty < 0 = short (in opening position)
                        lower_is_long = qty1 > 0
                        upper_is_long = qty2 > 0

                        if right1 == "C":
                            # Call spreads
                            # Bull Call: Long lower, Short upper (debit)
                            # Bear Call: Short lower, Long upper (credit)
                            if lower_is_long and not upper_is_long:
                                return "Bull Call Spread"
                            elif not lower_is_long and upper_is_long:
                                return "Bear Call Spread"
                        else:
                            # Put spreads
                            # Bull Put: Long lower, Short upper (credit)
                            # Bear Put: Short lower, Long upper (debit)
                            if lower_is_long and not upper_is_long:
                                return "Bull Put Spread"
                            elif not lower_is_long and upper_is_long:
                                return "Bear Put Spread"
                    except (ValueError, IndexError):
                        pass

                    # Fallback if can't determine direction
                    if right1 == "C":
                        return "Vertical Call Spread"
                    else:
                        return "Vertical Put Spread"

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

    async def mark_expired_trades(self) -> dict:
        """Mark OPEN option trades as EXPIRED if their expiration has passed.

        Options that expire worthless (OTM at expiration) don't generate closing
        executions from IBKR. This method finds such trades and marks them as
        EXPIRED with appropriate P&L calculation.

        Returns:
            Dict with statistics: {trades_marked, total_pnl_impact}
        """
        stats = {
            "trades_marked": 0,
            "total_pnl_impact": Decimal("0.00"),
            "details": [],
        }

        # Find all OPEN trades
        stmt = select(Trade).where(Trade.status == "OPEN")
        result = await self.session.execute(stmt)
        open_trades = list(result.scalars().all())

        today = datetime.now(UTC)

        for trade in open_trades:
            # Get executions for this trade to find expiration dates
            exec_stmt = select(Execution).where(Execution.trade_id == trade.id)
            exec_result = await self.session.execute(exec_stmt)
            executions = list(exec_result.scalars().all())

            # Find option executions and their expirations
            option_expirations = []
            for exec in executions:
                if exec.security_type == "OPT" and exec.expiration:
                    option_expirations.append(exec.expiration)

            if not option_expirations:
                # No options in this trade (probably stock), skip
                continue

            # Get the latest expiration date for this trade
            latest_expiration = max(option_expirations)

            # Normalize expiration to end of day (options expire at market close)
            # Add a buffer of 1 day to account for after-hours processing
            expiration_cutoff = latest_expiration.replace(
                hour=23, minute=59, second=59
            ) + timedelta(days=1)

            if today > expiration_cutoff:
                # This trade's options have expired
                # Calculate P&L for worthless expiration

                # For credit trades (opening_cost < 0): full credit is profit
                # For debit trades (opening_cost > 0): full cost is loss
                opening_cost = trade.opening_cost or Decimal("0.00")
                total_commission = trade.total_commission or Decimal("0.00")

                # When options expire worthless:
                # - If you sold options (credit), you keep the premium = profit
                # - If you bought options (debit), you lose the premium = loss
                # P&L = -opening_cost - commission
                # (opening_cost is negative for credits, positive for debits)
                realized_pnl = -opening_cost - total_commission

                # Update trade
                trade.status = "EXPIRED"
                trade.closed_at = latest_expiration
                trade.realized_pnl = realized_pnl
                trade.total_pnl = realized_pnl
                trade.closing_proceeds = Decimal("0.00")  # Expired worthless

                stats["trades_marked"] += 1
                stats["total_pnl_impact"] += realized_pnl
                stats["details"].append({
                    "trade_id": trade.id,
                    "underlying": trade.underlying,
                    "strategy_type": trade.strategy_type,
                    "expiration": latest_expiration.strftime("%Y-%m-%d"),
                    "realized_pnl": float(realized_pnl),
                })

        if stats["trades_marked"] > 0:
            await self.session.commit()

        return stats

    async def get_expired_candidates(self) -> list[dict]:
        """Get list of OPEN trades that have expired options (for preview).

        Returns:
            List of trade details that would be marked as expired
        """
        candidates = []

        stmt = select(Trade).where(Trade.status == "OPEN")
        result = await self.session.execute(stmt)
        open_trades = list(result.scalars().all())

        today = datetime.now(UTC)

        for trade in open_trades:
            exec_stmt = select(Execution).where(Execution.trade_id == trade.id)
            exec_result = await self.session.execute(exec_stmt)
            executions = list(exec_result.scalars().all())

            option_expirations = []
            for exec in executions:
                if exec.security_type == "OPT" and exec.expiration:
                    option_expirations.append(exec.expiration)

            if not option_expirations:
                continue

            latest_expiration = max(option_expirations)
            expiration_cutoff = latest_expiration.replace(
                hour=23, minute=59, second=59
            ) + timedelta(days=1)

            if today > expiration_cutoff:
                opening_cost = trade.opening_cost or Decimal("0.00")
                total_commission = trade.total_commission or Decimal("0.00")
                realized_pnl = -opening_cost - total_commission

                days_expired = (today - latest_expiration).days

                candidates.append({
                    "trade_id": trade.id,
                    "underlying": trade.underlying,
                    "strategy_type": trade.strategy_type,
                    "opened_at": trade.opened_at.strftime("%Y-%m-%d") if trade.opened_at else None,
                    "expiration": latest_expiration.strftime("%Y-%m-%d"),
                    "days_expired": days_expired,
                    "opening_cost": float(opening_cost),
                    "projected_pnl": float(realized_pnl),
                })

        return candidates
