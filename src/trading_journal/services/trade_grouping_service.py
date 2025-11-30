"""Trade grouping service - converts executions into trades with strategy classification."""

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.models.execution import Execution
from trading_journal.models.trade import Trade


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
    """Service for grouping executions into trades."""

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

        # Group by underlying
        by_underlying = defaultdict(list)
        for exec in executions:
            by_underlying[exec.underlying].append(exec)

        # Process each underlying
        for underlying, execs in by_underlying.items():
            ledger = TradeLedger(underlying)
            trades_data = []

            for execution in execs:
                ledger.add_execution(execution)

                # Check if position is flat (trade complete)
                if ledger.is_flat():
                    trade_data = self._create_trade_data(ledger, is_closed=True)
                    trades_data.append(trade_data)

                    # Reset ledger for next trade
                    ledger = TradeLedger(underlying)

            # Handle any remaining open position
            if ledger.executions:
                trade_data = self._create_trade_data(ledger, is_closed=False)
                trades_data.append(trade_data)

            # Create trade records
            for trade_data in trades_data:
                trade = await self._create_or_update_trade(trade_data)
                if trade:
                    stats["trades_created"] += 1

        await self.session.commit()
        return stats

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
        opening_cost = sum(
            abs(e.net_amount) for e in ledger.executions
            if e.side == "BOT"
        )
        closing_proceeds = sum(
            abs(e.net_amount) for e in ledger.executions
            if e.side == "SLD"
        ) if is_closed else Decimal("0.00")

        total_commission = sum(e.commission for e in ledger.executions)

        return {
            "underlying": ledger.underlying,
            "strategy_type": strategy,
            "status": "CLOSED" if is_closed else "OPEN",
            "opened_at": opened_at,
            "closed_at": closed_at,
            "realized_pnl": ledger.get_pnl() if is_closed else Decimal("0.00"),
            "unrealized_pnl": ledger.get_pnl() if not is_closed else Decimal("0.00"),
            "total_pnl": ledger.get_pnl(),
            "opening_cost": opening_cost,
            "closing_proceeds": closing_proceeds,
            "total_commission": total_commission,
            "num_legs": len(legs),
            "num_executions": len(ledger.executions),
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
                    exp1, strike1, right1 = parts1
                    exp2, strike2, right2 = parts2

                    # Same expiry and type = vertical spread
                    if exp1 == exp2 and right1 == right2:
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
