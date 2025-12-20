"""Service for normalizing executions affected by stock splits.

This service handles:
1. Detecting pre-split executions that need normalization
2. Normalizing strike prices, quantities, and prices for both options and stocks
3. Supporting both forward splits (10:1) and reverse splits (1:5)
4. Batch normalization of all affected executions
"""

from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.services.stock_splits import (
    STOCK_SPLITS,
    get_splits_for_symbol,
    normalize_execution,
)
from trading_journal.models.execution import Execution


class SplitNormalizationService:
    """Service for normalizing stock split affected executions."""

    def __init__(self, session: AsyncSession):
        """Initialize the service.

        Args:
            session: Database session
        """
        self.session = session

    async def normalize_all_splits(self) -> dict:
        """Normalize all executions affected by stock splits.

        Returns:
            Statistics about the normalization process
        """
        stats = {
            "symbols_checked": 0,
            "executions_normalized": 0,
            "options_normalized": 0,
            "stocks_normalized": 0,
            "by_symbol": {},
        }

        # Process each symbol with known splits
        for symbol in STOCK_SPLITS.keys():
            result = await self._normalize_symbol(symbol)
            stats["symbols_checked"] += 1
            if result["total"] > 0:
                stats["executions_normalized"] += result["total"]
                stats["options_normalized"] += result["options"]
                stats["stocks_normalized"] += result["stocks"]
                stats["by_symbol"][symbol] = result

        return stats

    async def _normalize_symbol(self, symbol: str) -> dict:
        """Normalize all pre-split executions for a symbol.

        Args:
            symbol: Stock symbol to normalize

        Returns:
            Dict with normalization counts {total, options, stocks}
        """
        splits = get_splits_for_symbol(symbol)
        if not splits:
            return {"total": 0, "options": 0, "stocks": 0}

        options_normalized = 0
        stocks_normalized = 0

        for split in splits:
            # Find pre-split executions
            stmt = select(Execution).where(
                Execution.underlying == symbol,
                Execution.execution_time < split.split_date,
            )

            result = await self.session.execute(stmt)
            executions = list(result.scalars().all())

            for exec in executions:
                # Skip currency/forex trades (huge quantities, tiny prices)
                if exec.quantity and exec.quantity > 1000000:
                    continue  # Likely a currency trade, not a stock
                if exec.price and exec.price < Decimal("0.01"):
                    continue  # Likely a currency trade

                needs_update = False
                new_strike = exec.strike
                new_quantity = exec.quantity
                new_price = exec.price

                if exec.security_type == "OPT" and exec.strike:
                    # Option - check if strike looks pre-split using split-specific threshold
                    if split.is_pre_split_strike(exec.strike):
                        new_strike = split.normalize_strike(exec.strike, exec.execution_time)
                        new_quantity = split.normalize_quantity(exec.quantity, exec.execution_time)
                        new_price = split.normalize_price(exec.price, exec.execution_time)
                        needs_update = True

                elif exec.security_type == "STK" and split.apply_to_stocks:
                    # Stock - normalize if apply_to_stocks is enabled for this split
                    # For reverse splits: quantity decreases, price increases
                    # For forward splits: quantity increases, price decreases
                    new_quantity = split.normalize_quantity(exec.quantity, exec.execution_time)
                    new_price = split.normalize_price(exec.price, exec.execution_time)
                    needs_update = True

                if needs_update:
                    exec.strike = new_strike
                    exec.quantity = new_quantity
                    exec.price = new_price

                    # Note: net_amount should NOT be recalculated for stocks
                    # The dollar value of the position doesn't change with a split
                    # Only recalculate for options where strike/multiplier matter
                    if exec.security_type == "OPT":
                        multiplier = exec.multiplier or 100
                        exec.net_amount = (
                            new_price * new_quantity * multiplier
                            * (-1 if exec.side == "BOT" else 1)
                        )
                        options_normalized += 1
                    else:
                        stocks_normalized += 1

        await self.session.flush()
        return {
            "total": options_normalized + stocks_normalized,
            "options": options_normalized,
            "stocks": stocks_normalized,
        }

    async def check_for_unnormalized_splits(self) -> dict:
        """Check for executions that may need split normalization.

        Returns:
            Report of potentially unnormalized executions
        """
        report = {
            "potential_issues": [],
            "total_suspicious": 0,
        }

        for symbol, splits in STOCK_SPLITS.items():
            for split in splits:
                # Look for options with pre-split strikes before split date
                if split.is_reverse:
                    # For reverse splits, pre-split strikes are LOWER
                    strike_condition = Execution.strike <= split.min_pre_split_strike
                else:
                    # For forward splits, pre-split strikes are HIGHER
                    strike_condition = Execution.strike >= split.min_pre_split_strike

                stmt = select(Execution).where(
                    Execution.underlying == symbol,
                    Execution.security_type == "OPT",
                    Execution.execution_time < split.split_date,
                    strike_condition,
                )

                result = await self.session.execute(stmt)
                suspicious_options = list(result.scalars().all())

                # Also check for stock positions that may need normalization
                suspicious_stocks = []
                if split.apply_to_stocks:
                    stmt = select(Execution).where(
                        Execution.underlying == symbol,
                        Execution.security_type == "STK",
                        Execution.execution_time < split.split_date,
                    )
                    result = await self.session.execute(stmt)
                    suspicious_stocks = list(result.scalars().all())

                total_suspicious = len(suspicious_options) + len(suspicious_stocks)

                if total_suspicious > 0:
                    report["potential_issues"].append({
                        "symbol": symbol,
                        "split_date": str(split.split_date),
                        "split_ratio": split.ratio,
                        "is_reverse": split.is_reverse,
                        "options_count": len(suspicious_options),
                        "stocks_count": len(suspicious_stocks),
                        "sample_strikes": list(set(
                            float(e.strike) for e in suspicious_options[:5] if e.strike
                        )),
                    })
                    report["total_suspicious"] += total_suspicious

        return report

    async def normalize_symbol(self, symbol: str) -> dict:
        """Public method to normalize a specific symbol.

        Args:
            symbol: Stock symbol to normalize

        Returns:
            Dict with normalization counts
        """
        result = await self._normalize_symbol(symbol)
        await self.session.commit()
        return result


async def normalize_single_execution(
    execution: Execution,
) -> bool:
    """Normalize a single execution for splits (in-memory, no DB update).

    This is useful during import to normalize before saving.
    Handles both forward and reverse splits.

    Args:
        execution: Execution to normalize

    Returns:
        True if execution was modified
    """
    if not execution.underlying:
        return False

    splits = get_splits_for_symbol(execution.underlying)
    if not splits:
        return False

    modified = False

    for split in splits:
        if execution.execution_time.date() < split.split_date:
            if execution.security_type == "OPT" and execution.strike:
                if split.is_pre_split_strike(execution.strike):
                    execution.strike = split.normalize_strike(execution.strike, execution.execution_time)
                    execution.quantity = split.normalize_quantity(execution.quantity, execution.execution_time)
                    execution.price = split.normalize_price(execution.price, execution.execution_time)
                    modified = True
            elif execution.security_type == "STK" and split.apply_to_stocks:
                execution.quantity = split.normalize_quantity(execution.quantity, execution.execution_time)
                execution.price = split.normalize_price(execution.price, execution.execution_time)
                modified = True

    return modified
