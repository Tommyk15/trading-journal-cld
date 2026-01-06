"""Wash Sale Detection and Adjustment Service.

IRS Wash Sale Rule: If you sell a security at a loss and buy a "substantially identical"
security within 30 days before or after the sale, the loss is disallowed for tax purposes.
The disallowed loss is added to the cost basis of the replacement shares.

For options, "substantially identical" typically means same underlying, same strike,
same expiration, and same type (call/put).
"""

from datetime import timedelta
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from trading_journal.models.execution import Execution
from trading_journal.models.trade import Trade


class WashSaleMatch(NamedTuple):
    """Represents a wash sale match between a loss trade and replacement trade."""

    loss_trade_id: int
    loss_trade: Trade
    replacement_trade_id: int
    replacement_trade: Trade
    loss_amount: Decimal
    replacement_shares: int
    loss_shares: int
    disallowed_loss: Decimal


class WashSaleService:
    """Service for detecting and calculating wash sale adjustments."""

    WASH_SALE_WINDOW_DAYS = 30

    def __init__(self, session: AsyncSession):
        """Initialize with database session."""
        self.session = session

    async def detect_wash_sales_for_trade(self, trade: Trade) -> list[WashSaleMatch]:
        """Detect wash sales that affect a specific trade.

        A trade can be affected by wash sales in two ways:
        1. The trade is a REPLACEMENT purchase (receives disallowed loss adjustment)
        2. The trade is a LOSS sale (its loss is disallowed)

        Args:
            trade: The trade to check for wash sale impacts

        Returns:
            List of WashSaleMatch objects describing the wash sale relationships
        """
        matches = []

        # Get the trade's executions to understand what was traded
        exec_stmt = select(Execution).where(Execution.trade_id == trade.id)
        exec_result = await self.session.execute(exec_stmt)
        executions = list(exec_result.scalars().all())

        if not executions:
            return matches

        # Get the option details from the first execution
        first_exec = executions[0]
        underlying = first_exec.underlying
        strike = first_exec.strike
        expiration = first_exec.expiration
        option_type = first_exec.option_type

        # Case 1: This trade is a potential REPLACEMENT (it's an open position or recent purchase)
        # Look for closed trades at a loss within 30 days before this trade opened
        if trade.status == "OPEN":
            loss_trades = await self._find_loss_trades_before(
                underlying=underlying,
                strike=strike,
                expiration=expiration,
                option_type=option_type,
                before_date=trade.opened_at,
                exclude_trade_id=trade.id,
            )

            for loss_trade in loss_trades:
                match = await self._calculate_wash_sale_match(
                    loss_trade=loss_trade,
                    replacement_trade=trade,
                )
                if match:
                    matches.append(match)

        # Case 2: This trade was closed at a loss
        # Look for replacement purchases within 30 days after this trade closed
        if trade.status == "CLOSED" and trade.realized_pnl < 0:
            replacement_trades = await self._find_replacement_trades_after(
                underlying=underlying,
                strike=strike,
                expiration=expiration,
                option_type=option_type,
                after_date=trade.closed_at,
                exclude_trade_id=trade.id,
            )

            for replacement_trade in replacement_trades:
                match = await self._calculate_wash_sale_match(
                    loss_trade=trade,
                    replacement_trade=replacement_trade,
                )
                if match:
                    matches.append(match)

        return matches

    async def _find_loss_trades_before(
        self,
        underlying: str,
        strike: float | None,
        expiration,
        option_type: str | None,
        before_date,
        exclude_trade_id: int,
    ) -> list[Trade]:
        """Find trades closed at a loss within 30 days before a given date."""
        window_start = before_date - timedelta(days=self.WASH_SALE_WINDOW_DAYS)

        stmt = (
            select(Trade)
            .where(
                and_(
                    Trade.id != exclude_trade_id,
                    Trade.underlying == underlying,
                    Trade.status == "CLOSED",
                    Trade.realized_pnl < 0,  # Loss
                    Trade.closed_at >= window_start,
                    Trade.closed_at <= before_date,
                )
            )
            .options(selectinload(Trade.tag_list))
        )
        result = await self.session.execute(stmt)
        potential_trades = list(result.scalars().all())

        # Filter by matching option details (strike, expiration, type)
        matching_trades = []
        for trade in potential_trades:
            if await self._is_substantially_identical(
                trade, strike, expiration, option_type
            ):
                matching_trades.append(trade)

        return matching_trades

    async def _find_replacement_trades_after(
        self,
        underlying: str,
        strike: float | None,
        expiration,
        option_type: str | None,
        after_date,
        exclude_trade_id: int,
    ) -> list[Trade]:
        """Find trades opened within 30 days after a given date."""
        window_end = after_date + timedelta(days=self.WASH_SALE_WINDOW_DAYS)

        stmt = (
            select(Trade)
            .where(
                and_(
                    Trade.id != exclude_trade_id,
                    Trade.underlying == underlying,
                    Trade.opened_at >= after_date,
                    Trade.opened_at <= window_end,
                )
            )
            .options(selectinload(Trade.tag_list))
        )
        result = await self.session.execute(stmt)
        potential_trades = list(result.scalars().all())

        # Filter by matching option details
        matching_trades = []
        for trade in potential_trades:
            if await self._is_substantially_identical(
                trade, strike, expiration, option_type
            ):
                matching_trades.append(trade)

        return matching_trades

    async def _is_substantially_identical(
        self,
        trade: Trade,
        target_strike: float | None,
        target_expiration,
        target_option_type: str | None,
    ) -> bool:
        """Check if a trade contains substantially identical positions.

        For options, substantially identical means:
        - Same underlying (already filtered)
        - Same strike price
        - Same expiration date
        - Same option type (call/put)

        Returns True if ANY execution in the trade matches the target.
        """
        exec_stmt = select(Execution).where(Execution.trade_id == trade.id)
        result = await self.session.execute(exec_stmt)
        executions = list(result.scalars().all())

        if not executions:
            return False

        # For stock trades (no strike), just match underlying
        if target_strike is None:
            return any(e.strike is None for e in executions)

        # For options, check if any execution matches
        for exec in executions:
            if (
                exec.strike == target_strike
                and exec.expiration == target_expiration
                and exec.option_type == target_option_type
            ):
                return True

        return False

    async def _get_matching_leg_loss(
        self,
        trade: Trade,
        target_strike: float | None,
        target_expiration,
        target_option_type: str | None,
    ) -> tuple[Decimal, int]:
        """Calculate the loss and quantity for matching executions only.

        For multi-leg trades (spreads), only considers the P&L from the
        leg that matches the target option.

        Returns:
            Tuple of (loss_amount, quantity) for matching executions
        """
        exec_stmt = select(Execution).where(Execution.trade_id == trade.id)
        result = await self.session.execute(exec_stmt)
        executions = list(result.scalars().all())

        # Filter to matching executions
        matching_execs = [
            e for e in executions
            if e.strike == target_strike
            and e.expiration == target_expiration
            and e.option_type == target_option_type
        ]

        if not matching_execs:
            return Decimal("0.00"), 0

        # Calculate the cost and proceeds for matching leg
        buy_cost = sum(abs(e.net_amount) for e in matching_execs if e.side == "BOT")
        sell_proceeds = sum(abs(e.net_amount) for e in matching_execs if e.side == "SLD")
        commission = sum(e.commission for e in matching_execs)

        # P&L for this leg
        leg_pnl = sell_proceeds - buy_cost - commission

        # Quantity (use buy qty for closed trades)
        buy_qty = sum(e.quantity for e in matching_execs if e.side == "BOT")

        # Only return if this leg had a loss
        if leg_pnl >= 0:
            return Decimal("0.00"), 0

        return abs(leg_pnl), int(buy_qty)

    async def _calculate_wash_sale_match(
        self,
        loss_trade: Trade,
        replacement_trade: Trade,
        target_strike: float | None = None,
        target_expiration=None,
        target_option_type: str | None = None,
    ) -> WashSaleMatch | None:
        """Calculate the wash sale disallowed loss.

        For multi-leg trades (spreads), only considers the loss from the
        matching leg, not the entire trade.

        The disallowed loss is proportional to the replacement shares.
        If replacement_shares >= loss_shares: entire leg loss is disallowed
        If replacement_shares < loss_shares: proportional leg loss is disallowed
        """
        # Get replacement trade details if target not specified
        if target_strike is None:
            exec_stmt = select(Execution).where(
                Execution.trade_id == replacement_trade.id
            ).limit(1)
            result = await self.session.execute(exec_stmt)
            exec = result.scalar_one_or_none()
            if exec:
                target_strike = float(exec.strike) if exec.strike else None
                target_expiration = exec.expiration
                target_option_type = exec.option_type

        # Get the loss amount for just the matching leg
        leg_loss, loss_qty = await self._get_matching_leg_loss(
            loss_trade, target_strike, target_expiration, target_option_type
        )

        if leg_loss == 0 or loss_qty == 0:
            return None

        # Get replacement quantity (for the matching option)
        replacement_qty = await self._get_trade_quantity(replacement_trade)

        if replacement_qty == 0:
            return None

        # Calculate disallowed portion
        if replacement_qty >= loss_qty:
            # Entire leg loss is disallowed
            disallowed_loss = leg_loss
        else:
            # Proportional leg loss is disallowed
            disallowed_loss = leg_loss * Decimal(replacement_qty) / Decimal(loss_qty)

        return WashSaleMatch(
            loss_trade_id=loss_trade.id,
            loss_trade=loss_trade,
            replacement_trade_id=replacement_trade.id,
            replacement_trade=replacement_trade,
            loss_amount=leg_loss,
            replacement_shares=int(replacement_qty),
            loss_shares=int(loss_qty),
            disallowed_loss=disallowed_loss,
        )

    async def _get_trade_quantity(self, trade: Trade) -> int:
        """Get the total quantity of contracts/shares in a trade."""
        exec_stmt = select(Execution).where(Execution.trade_id == trade.id)
        result = await self.session.execute(exec_stmt)
        executions = list(result.scalars().all())

        # Calculate net quantity (buys - sells for open position)
        buy_qty = sum(e.quantity for e in executions if e.side == "BOT")
        sell_qty = sum(e.quantity for e in executions if e.side == "SLD")

        # For closed trades, use the total bought (equals total sold)
        if trade.status == "CLOSED":
            return int(buy_qty)

        # For open trades, use net position
        return int(buy_qty - sell_qty)

    async def apply_wash_sale_adjustments(
        self, trade: Trade, commit: bool = True
    ) -> Decimal:
        """Apply wash sale adjustments to a trade's cost basis.

        Args:
            trade: The trade to adjust
            commit: Whether to commit changes to the database

        Returns:
            The total wash sale adjustment applied
        """
        matches = await self.detect_wash_sales_for_trade(trade)

        total_adjustment = Decimal("0.00")
        from_trade_ids = []

        for match in matches:
            # Only apply adjustment if this trade is the replacement
            if match.replacement_trade_id == trade.id:
                total_adjustment += match.disallowed_loss
                from_trade_ids.append(str(match.loss_trade_id))

        if total_adjustment > 0:
            trade.wash_sale_adjustment = total_adjustment
            trade.wash_sale_from_trade_ids = ",".join(from_trade_ids) if from_trade_ids else None

            if commit:
                await self.session.commit()

        return total_adjustment

    async def recalculate_all_wash_sales(self) -> dict:
        """Recalculate wash sale adjustments for all trades.

        Returns:
            Statistics about the recalculation
        """
        # Get all open trades that might have wash sale adjustments
        stmt = select(Trade).where(Trade.status == "OPEN")
        result = await self.session.execute(stmt)
        open_trades = list(result.scalars().all())

        stats = {
            "trades_checked": 0,
            "trades_adjusted": 0,
            "total_adjustment": Decimal("0.00"),
        }

        for trade in open_trades:
            stats["trades_checked"] += 1

            # Reset existing adjustment
            trade.wash_sale_adjustment = Decimal("0.00")
            trade.wash_sale_from_trade_ids = None

            # Calculate new adjustment
            adjustment = await self.apply_wash_sale_adjustments(trade, commit=False)

            if adjustment > 0:
                stats["trades_adjusted"] += 1
                stats["total_adjustment"] += adjustment

        await self.session.commit()
        return stats

    def get_adjusted_cost_basis(self, trade: Trade) -> Decimal:
        """Get the wash-sale-adjusted cost basis for a trade.

        Args:
            trade: The trade to get adjusted cost basis for

        Returns:
            Opening cost + wash sale adjustment
        """
        return trade.opening_cost + (trade.wash_sale_adjustment or Decimal("0.00"))

    def get_adjusted_avg_cost_per_share(
        self, trade: Trade, quantity: int, multiplier: int = 100
    ) -> Decimal:
        """Get the wash-sale-adjusted average cost per share.

        Args:
            trade: The trade
            quantity: Number of contracts
            multiplier: Contract multiplier (100 for options)

        Returns:
            Adjusted average cost per share
        """
        if quantity == 0:
            return Decimal("0.00")

        adjusted_cost = self.get_adjusted_cost_basis(trade)
        return adjusted_cost / Decimal(quantity) / Decimal(multiplier)
