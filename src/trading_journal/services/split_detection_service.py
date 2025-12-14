"""Stock split detection service.

Detects stock splits by analyzing execution data patterns:
- Price drops that match common split ratios (2:1, 4:1, 10:1, etc.)
- Quantity mismatches where shares sold far exceed shares bought
- Dollar amounts that still balance correctly despite quantity mismatch
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.models.execution import Execution
from trading_journal.models.trade import Trade

# Common split ratios to check (forward splits)
COMMON_SPLIT_RATIOS = [2, 3, 4, 5, 10, 20]

# Tolerance for price ratio matching (e.g., 0.15 = 15% tolerance)
PRICE_RATIO_TOLERANCE = 0.15


class StockSplit:
    """Represents a detected stock split."""

    def __init__(
        self,
        underlying: str,
        split_ratio: int,
        split_date: datetime,
        pre_split_price: Decimal,
        post_split_price: Decimal,
        pre_split_quantity: int,
        adjusted_quantity: int,
    ):
        self.underlying = underlying
        self.split_ratio = split_ratio
        self.split_date = split_date
        self.pre_split_price = pre_split_price
        self.post_split_price = post_split_price
        self.pre_split_quantity = pre_split_quantity
        self.adjusted_quantity = adjusted_quantity

    def __repr__(self) -> str:
        return (
            f"<StockSplit({self.underlying} {self.split_ratio}:1 on {self.split_date.date()}, "
            f"{self.pre_split_quantity} -> {self.adjusted_quantity} shares)>"
        )


class SplitDetectionService:
    """Service for detecting and handling stock splits."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def detect_splits_for_underlying(self, underlying: str) -> list[StockSplit]:
        """Detect potential stock splits for a given underlying.

        Analyzes stock executions to find:
        1. Significant price drops between consecutive executions
        2. Price ratios matching common split ratios
        3. Quantity mismatches suggesting pre-split shares

        Args:
            underlying: Stock symbol to analyze

        Returns:
            List of detected StockSplit objects
        """
        # Get all stock executions for this underlying, ordered by time
        stmt = (
            select(Execution)
            .where(Execution.underlying == underlying)
            .where(Execution.security_type == "STK")
            .order_by(Execution.execution_time)
        )

        result = await self.session.execute(stmt)
        executions = list(result.scalars().all())

        if len(executions) < 2:
            return []

        detected_splits = []

        # Look for price drops between executions
        for i in range(len(executions) - 1):
            current_exec = executions[i]
            next_exec = executions[i + 1]

            # Skip if prices are similar (no split)
            if current_exec.price == 0 or next_exec.price == 0:
                continue

            price_ratio = float(current_exec.price / next_exec.price)

            # Check if ratio matches a common split ratio
            for split_ratio in COMMON_SPLIT_RATIOS:
                lower_bound = split_ratio * (1 - PRICE_RATIO_TOLERANCE)
                upper_bound = split_ratio * (1 + PRICE_RATIO_TOLERANCE)

                if lower_bound <= price_ratio <= upper_bound:
                    # Found a potential split!
                    # Calculate pre-split quantities
                    pre_split_qty = sum(
                        e.quantity if e.side == "BOT" else 0
                        for e in executions[: i + 1]
                    )

                    split = StockSplit(
                        underlying=underlying,
                        split_ratio=split_ratio,
                        split_date=next_exec.execution_time,
                        pre_split_price=current_exec.price,
                        post_split_price=next_exec.price,
                        pre_split_quantity=pre_split_qty,
                        adjusted_quantity=pre_split_qty * split_ratio,
                    )
                    detected_splits.append(split)
                    break

        return detected_splits

    async def analyze_position_for_splits(self, underlying: str) -> dict:
        """Analyze a stock position for split-related issues.

        Returns detailed analysis including:
        - Raw share counts (bought vs sold)
        - Detected splits and adjusted counts
        - Whether position should be flat

        Uses two detection methods:
        1. Price ratio analysis between consecutive executions
        2. Quantity deficit analysis to infer split ratios

        Args:
            underlying: Stock symbol to analyze

        Returns:
            Analysis dictionary
        """
        stmt = (
            select(Execution)
            .where(Execution.underlying == underlying)
            .where(Execution.security_type == "STK")
            .order_by(Execution.execution_time)
        )

        result = await self.session.execute(stmt)
        executions = list(result.scalars().all())

        # Calculate raw totals
        shares_bought = sum(e.quantity for e in executions if e.side == "BOT")
        shares_sold = sum(e.quantity for e in executions if e.side == "SLD")
        total_cost = sum(e.net_amount for e in executions if e.side == "BOT")
        total_proceeds = sum(e.net_amount for e in executions if e.side == "SLD")
        net_pnl = total_cost + total_proceeds  # cost is negative, proceeds is positive

        # Detect splits using price analysis
        price_based_splits = await self.detect_splits_for_underlying(underlying)

        # Also try quantity-based split inference
        raw_net_position = shares_bought - shares_sold

        # Prefer quantity-based inference as it's more accurate for position balancing
        splits = []
        if raw_net_position < 0:
            # More sold than bought - likely a split occurred
            # Try to infer split ratio from quantity deficit
            inferred_split = self._infer_split_from_quantities(
                executions, shares_bought, shares_sold
            )
            if inferred_split:
                splits = [inferred_split]

        # Fall back to price-based detection if quantity inference didn't work
        if not splits and price_based_splits:
            splits = price_based_splits

        # Calculate adjusted quantities
        adjusted_bought = shares_bought
        for split in splits:
            # Adjust pre-split shares
            adjusted_bought = (adjusted_bought - split.pre_split_quantity) + split.adjusted_quantity

        # Determine if position should be flat
        adjusted_net_position = adjusted_bought - shares_sold

        return {
            "underlying": underlying,
            "raw_shares_bought": shares_bought,
            "raw_shares_sold": shares_sold,
            "raw_net_position": raw_net_position,
            "adjusted_shares_bought": adjusted_bought,
            "adjusted_net_position": adjusted_net_position,
            "total_cost": total_cost,
            "total_proceeds": total_proceeds,
            "net_pnl": net_pnl,
            "detected_splits": splits,
            "position_should_be_flat": abs(adjusted_net_position) < 10,  # Allow small rounding
            "has_split_issue": raw_net_position != 0 and abs(adjusted_net_position) < 10,
        }

    def _infer_split_from_quantities(
        self,
        executions: list[Execution],
        total_bought: int,
        total_sold: int,
    ) -> StockSplit | None:
        """Infer a stock split from quantity mismatch.

        If shares_sold > shares_bought, there was likely a split.
        We find the split point (where prices dropped) and calculate
        the required split ratio to balance the position.

        Args:
            executions: All executions for the position
            total_bought: Total shares bought
            total_sold: Total shares sold

        Returns:
            Inferred StockSplit or None
        """
        if total_sold <= total_bought:
            return None

        # Find the price drop point (split date)
        split_point_idx = None
        for i in range(len(executions) - 1):
            current = executions[i]
            next_exec = executions[i + 1]

            if current.price == 0 or next_exec.price == 0:
                continue

            price_ratio = float(current.price / next_exec.price)

            # Look for significant price drops (at least 1.5x)
            if price_ratio >= 1.5:
                split_point_idx = i
                break

        if split_point_idx is None:
            return None

        # Calculate pre-split quantity (bought before the split point)
        pre_split_qty = sum(
            e.quantity for e in executions[: split_point_idx + 1]
            if e.side == "BOT"
        )

        # Calculate post-split buys
        post_split_buys = sum(
            e.quantity for e in executions[split_point_idx + 1:]
            if e.side == "BOT"
        )

        if pre_split_qty == 0:
            return None

        # Calculate required split ratio: pre_split_qty * ratio + post_split_buys = total_sold
        # ratio = (total_sold - post_split_buys) / pre_split_qty
        required_ratio = (total_sold - post_split_buys) / pre_split_qty

        # Round to nearest common split ratio
        for ratio in COMMON_SPLIT_RATIOS:
            if abs(required_ratio - ratio) < 0.5:
                split_date = executions[split_point_idx + 1].execution_time
                return StockSplit(
                    underlying=executions[0].underlying,
                    split_ratio=ratio,
                    split_date=split_date,
                    pre_split_price=executions[split_point_idx].price,
                    post_split_price=executions[split_point_idx + 1].price,
                    pre_split_quantity=pre_split_qty,
                    adjusted_quantity=pre_split_qty * ratio,
                )

        return None

    async def scan_all_stocks_for_splits(self) -> list[dict]:
        """Scan all stock positions for potential split issues.

        Returns:
            List of analysis results for stocks with detected issues
        """
        # Get unique stock underlyings
        stmt = (
            select(Execution.underlying)
            .where(Execution.security_type == "STK")
            .distinct()
        )

        result = await self.session.execute(stmt)
        underlyings = [row[0] for row in result.fetchall()]

        issues = []
        for underlying in underlyings:
            analysis = await self.analyze_position_for_splits(underlying)
            if analysis["has_split_issue"] or analysis["detected_splits"]:
                issues.append(analysis)

        return issues

    async def fix_trade_with_split(self, trade_id: int) -> dict:
        """Fix a trade that has split-related issues.

        Updates the trade status and P&L based on actual dollar amounts,
        ignoring the incorrect share count.

        Args:
            trade_id: Trade ID to fix

        Returns:
            Update result
        """
        # Get the trade
        stmt = select(Trade).where(Trade.id == trade_id)
        result = await self.session.execute(stmt)
        trade = result.scalar_one_or_none()

        if not trade:
            return {"error": f"Trade {trade_id} not found"}

        # Get executions for this trade
        exec_stmt = (
            select(Execution)
            .where(Execution.trade_id == trade_id)
            .where(Execution.security_type == "STK")
        )
        exec_result = await self.session.execute(exec_stmt)
        executions = list(exec_result.scalars().all())

        if not executions:
            return {"error": f"No stock executions found for trade {trade_id}"}

        # Calculate P&L from net_amount (which is correct regardless of split)
        total_pnl = sum(e.net_amount for e in executions)

        # Find closing date
        closing_execs = [e for e in executions if e.open_close_indicator == "C" or e.side == "SLD"]
        closed_at = max(e.execution_time for e in closing_execs) if closing_execs else None

        # Analyze for splits
        analysis = await self.analyze_position_for_splits(trade.underlying)

        # Update trade if position should be flat
        if analysis["position_should_be_flat"]:
            trade.status = "CLOSED"
            trade.closed_at = closed_at
            trade.realized_pnl = total_pnl
            trade.total_pnl = total_pnl
            trade.updated_at = datetime.now(UTC)

            await self.session.commit()

            return {
                "trade_id": trade_id,
                "underlying": trade.underlying,
                "status": "CLOSED",
                "realized_pnl": float(total_pnl),
                "detected_splits": [str(s) for s in analysis["detected_splits"]],
                "message": "Trade fixed - position is flat after accounting for splits",
            }

        return {
            "trade_id": trade_id,
            "underlying": trade.underlying,
            "status": trade.status,
            "message": "Position is not flat even after accounting for splits",
            "analysis": analysis,
        }

    async def check_and_report_splits(self) -> dict:
        """Check all stock positions and report any split-related issues.

        Returns:
            Report of all detected issues
        """
        issues = await self.scan_all_stocks_for_splits()

        report = {
            "total_stocks_scanned": 0,
            "issues_found": len(issues),
            "details": [],
        }

        # Get total stock count
        stmt = (
            select(Execution.underlying)
            .where(Execution.security_type == "STK")
            .distinct()
        )
        result = await self.session.execute(stmt)
        report["total_stocks_scanned"] = len(result.fetchall())

        for issue in issues:
            detail = {
                "underlying": issue["underlying"],
                "raw_net_position": issue["raw_net_position"],
                "adjusted_net_position": issue["adjusted_net_position"],
                "net_pnl": float(issue["net_pnl"]),
                "detected_splits": [
                    {
                        "ratio": f"{s.split_ratio}:1",
                        "date": s.split_date.strftime("%Y-%m-%d"),
                        "pre_split_qty": s.pre_split_quantity,
                        "adjusted_qty": s.adjusted_quantity,
                    }
                    for s in issue["detected_splits"]
                ],
                "recommendation": (
                    "Position should be CLOSED"
                    if issue["position_should_be_flat"]
                    else "Needs manual review"
                ),
            }
            report["details"].append(detail)

        return report
