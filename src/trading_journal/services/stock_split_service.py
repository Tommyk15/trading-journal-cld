"""Service for applying stock split adjustments."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.models.stock_split import StockSplit


class StockSplitService:
    """Service for calculating split-adjusted quantities and prices."""

    def __init__(self, session: AsyncSession):
        """Initialize the service.

        Args:
            session: Database session
        """
        self.session = session
        self._splits_cache: dict[str, list[StockSplit]] = {}

    async def get_splits_for_symbol(self, symbol: str) -> list[StockSplit]:
        """Get all splits for a symbol, ordered by date descending.

        Args:
            symbol: Stock symbol

        Returns:
            List of stock splits, most recent first
        """
        if symbol in self._splits_cache:
            return self._splits_cache[symbol]

        stmt = (
            select(StockSplit)
            .where(StockSplit.symbol == symbol.upper())
            .order_by(StockSplit.split_date.desc())
        )
        result = await self.session.execute(stmt)
        splits = list(result.scalars().all())
        self._splits_cache[symbol] = splits
        return splits

    async def get_all_splits(self) -> dict[str, list[StockSplit]]:
        """Get all splits grouped by symbol.

        Returns:
            Dictionary of symbol -> list of splits
        """
        stmt = select(StockSplit).order_by(StockSplit.symbol, StockSplit.split_date.desc())
        result = await self.session.execute(stmt)
        splits = list(result.scalars().all())

        splits_by_symbol: dict[str, list[StockSplit]] = {}
        for split in splits:
            if split.symbol not in splits_by_symbol:
                splits_by_symbol[split.symbol] = []
            splits_by_symbol[split.symbol].append(split)

        self._splits_cache = splits_by_symbol
        return splits_by_symbol

    async def adjust_quantity(
        self,
        symbol: str,
        original_quantity: int | float,
        execution_date: datetime,
    ) -> tuple[float, list[StockSplit]]:
        """Adjust a quantity for all splits that occurred after the execution date.

        Args:
            symbol: Stock symbol
            original_quantity: Original quantity from execution
            execution_date: Date of the original execution

        Returns:
            Tuple of (adjusted_quantity, list of splits applied)
        """
        splits = await self.get_splits_for_symbol(symbol)

        adjusted_qty = float(original_quantity)
        applied_splits: list[StockSplit] = []

        for split in splits:
            # Only apply splits that occurred AFTER the execution date
            if split.split_date > execution_date:
                adjusted_qty *= float(split.adjustment_factor)
                applied_splits.append(split)

        return adjusted_qty, applied_splits

    async def adjust_price(
        self,
        symbol: str,
        original_price: Decimal | float,
        execution_date: datetime,
    ) -> tuple[Decimal, list[StockSplit]]:
        """Adjust a price for all splits that occurred after the execution date.

        Args:
            symbol: Stock symbol
            original_price: Original price from execution
            execution_date: Date of the original execution

        Returns:
            Tuple of (adjusted_price, list of splits applied)
        """
        splits = await self.get_splits_for_symbol(symbol)

        adjusted_price = Decimal(str(original_price))
        applied_splits: list[StockSplit] = []

        for split in splits:
            # Only apply splits that occurred AFTER the execution date
            if split.split_date > execution_date:
                adjusted_price *= split.price_factor
                applied_splits.append(split)

        return adjusted_price, applied_splits

    async def get_split_adjustment_factors(
        self,
        symbol: str,
        execution_date: datetime,
    ) -> tuple[float, Decimal]:
        """Get the cumulative adjustment factors for a symbol and date.

        Args:
            symbol: Stock symbol
            execution_date: Date of the original execution

        Returns:
            Tuple of (quantity_factor, price_factor)
        """
        splits = await self.get_splits_for_symbol(symbol)

        qty_factor = 1.0
        price_factor = Decimal("1")

        for split in splits:
            if split.split_date > execution_date:
                qty_factor *= float(split.adjustment_factor)
                price_factor *= split.price_factor

        return qty_factor, price_factor
