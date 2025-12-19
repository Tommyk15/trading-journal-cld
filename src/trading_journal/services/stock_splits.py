"""Stock split configuration and normalization utilities.

This module maintains a registry of known stock splits and provides
utilities to normalize pre-split executions to post-split values.

Supports both forward splits (e.g., 10:1 where 1 share becomes 10)
and reverse splits (e.g., 1:5 where 5 shares become 1).
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


@dataclass
class StockSplit:
    """Represents a stock split event.

    For forward splits (e.g., NVDA 10:1):
        - ratio_from=1, ratio_to=10 (or just ratio=10 with is_reverse=False)
        - 1 old share becomes 10 new shares
        - Strike prices divided by 10, quantities multiplied by 10

    For reverse splits (e.g., MSTY 5:1 reverse):
        - ratio_from=5, ratio_to=1 (or ratio=5 with is_reverse=True)
        - 5 old shares become 1 new share
        - Strike prices multiplied by 5, quantities divided by 5
    """
    symbol: str
    split_date: date
    ratio: int  # The split ratio (e.g., 10 for 10:1 or 5 for 5:1 reverse)
    is_reverse: bool = False  # True for reverse splits (consolidation)
    min_pre_split_strike: int = 500  # Minimum strike that indicates pre-split option
    apply_to_stocks: bool = True  # Whether to normalize stock positions

    @property
    def effective_ratio(self) -> Decimal:
        """Get the effective ratio for calculations.

        For forward splits: returns ratio (multiply qty, divide price)
        For reverse splits: returns 1/ratio (divide qty, multiply price)
        """
        if self.is_reverse:
            return Decimal(1) / Decimal(self.ratio)
        return Decimal(self.ratio)

    def normalize_strike(self, strike: Decimal, execution_date: datetime) -> Decimal:
        """Normalize a strike price if execution is pre-split."""
        if execution_date.date() < self.split_date:
            if self.is_reverse:
                return strike * self.ratio  # Reverse: strike goes up
            return strike / self.ratio  # Forward: strike goes down
        return strike

    def normalize_quantity(self, quantity: Decimal, execution_date: datetime) -> Decimal:
        """Normalize quantity if execution is pre-split."""
        if execution_date.date() < self.split_date:
            if self.is_reverse:
                return quantity / self.ratio  # Reverse: fewer shares
            return quantity * self.ratio  # Forward: more shares
        return quantity

    def normalize_price(self, price: Decimal, execution_date: datetime) -> Decimal:
        """Normalize price if execution is pre-split."""
        if execution_date.date() < self.split_date:
            if self.is_reverse:
                return price * self.ratio  # Reverse: price goes up
            return price / self.ratio  # Forward: price goes down
        return price

    def is_pre_split_strike(self, strike: Decimal) -> bool:
        """Check if a strike price looks like a pre-split value.

        For forward splits (10:1): pre-split strikes are ~10x higher
        For reverse splits (5:1): pre-split strikes are ~5x lower
        """
        if self.is_reverse:
            # For reverse splits, pre-split strikes are LOWER
            # e.g., MSTY pre-split $20 strike → post-split $100 strike
            return strike <= self.min_pre_split_strike
        # For forward splits, pre-split strikes are HIGHER
        return strike >= self.min_pre_split_strike

    def is_pre_split_price(self, price: Decimal) -> bool:
        """Check if a stock price looks like a pre-split value.

        For forward splits: pre-split prices are higher
        For reverse splits: pre-split prices are lower
        """
        if self.is_reverse:
            # For reverse splits, pre-split prices are LOWER
            return price <= self.min_pre_split_strike
        # For forward splits, pre-split prices are HIGHER
        return price >= self.min_pre_split_strike


# Registry of known stock splits
# Add new splits here as they occur
# min_pre_split_strike: strikes >= this value are considered pre-split (for forward splits)
#                       strikes <= this value are considered pre-split (for reverse splits)
# Set to roughly 5x the typical post-split strike to avoid false positives
STOCK_SPLITS: dict[str, list[StockSplit]] = {
    # === FORWARD SPLITS (share count increases) ===
    "NVDA": [
        # NVDA was ~$120 post-split, so pre-split strikes were ~$1200
        StockSplit(symbol="NVDA", split_date=date(2024, 6, 7), ratio=10, min_pre_split_strike=500),
    ],
    "SMCI": [
        # SMCI was ~$40 post-split, so pre-split strikes were ~$400
        StockSplit(symbol="SMCI", split_date=date(2024, 10, 1), ratio=10, min_pre_split_strike=200),
    ],
    "TSLA": [
        StockSplit(symbol="TSLA", split_date=date(2022, 8, 25), ratio=3, min_pre_split_strike=500),
        StockSplit(symbol="TSLA", split_date=date(2020, 8, 31), ratio=5, min_pre_split_strike=1000),
    ],
    "AMZN": [
        # AMZN was ~$125 post-split, pre-split ~$2500
        StockSplit(symbol="AMZN", split_date=date(2022, 6, 6), ratio=20, min_pre_split_strike=500),
    ],
    "GOOGL": [
        # GOOGL was ~$110 post-split, pre-split ~$2200
        StockSplit(symbol="GOOGL", split_date=date(2022, 7, 18), ratio=20, min_pre_split_strike=500),
    ],
    "GOOG": [
        StockSplit(symbol="GOOG", split_date=date(2022, 7, 18), ratio=20, min_pre_split_strike=500),
    ],
    "SHOP": [
        # SHOP was ~$35 post-split, pre-split ~$350
        StockSplit(symbol="SHOP", split_date=date(2022, 6, 29), ratio=10, min_pre_split_strike=150),
    ],
    # === REVERSE SPLITS (share count decreases) ===
    "MSTY": [
        # MSTY 5:1 reverse split - 5 old shares become 1 new share
        # Pre-split price ~$20, post-split ~$100
        StockSplit(
            symbol="MSTY",
            split_date=date(2025, 11, 25),
            ratio=5,
            is_reverse=True,
            min_pre_split_strike=50,  # Pre-split strikes were lower
            apply_to_stocks=True,
        ),
    ],
}


def get_splits_for_symbol(symbol: str) -> list[StockSplit]:
    """Get all splits for a given symbol.

    Args:
        symbol: Stock symbol

    Returns:
        List of StockSplit objects, sorted by date descending (most recent first)
    """
    splits = STOCK_SPLITS.get(symbol, [])
    return sorted(splits, key=lambda s: s.split_date, reverse=True)


def is_pre_split_execution(
    symbol: str,
    execution_date: datetime,
    strike: Decimal | None = None
) -> tuple[bool, StockSplit | None]:
    """Check if an execution is pre-split and needs normalization.

    Args:
        symbol: Stock symbol
        execution_date: Execution datetime
        strike: Optional strike price to help detect pre-split options

    Returns:
        Tuple of (is_pre_split, applicable_split)
    """
    splits = get_splits_for_symbol(symbol)

    for split in splits:
        if execution_date.date() < split.split_date:
            # For options, check if strike looks pre-split using split-specific threshold
            if strike is not None and split.is_pre_split_strike(strike):
                return True, split
            elif strike is None:
                # Stock execution
                return True, split

    return False, None


def normalize_execution(
    symbol: str,
    execution_date: datetime,
    strike: Decimal | None,
    quantity: Decimal,
    price: Decimal,
    is_stock: bool = False,
) -> tuple[Decimal | None, Decimal, Decimal]:
    """Normalize execution values for any applicable splits.

    Handles both forward splits (qty increases, price decreases) and
    reverse splits (qty decreases, price increases).

    Args:
        symbol: Stock symbol
        execution_date: Execution datetime
        strike: Strike price (None for stock)
        quantity: Execution quantity
        price: Execution price
        is_stock: Whether this is a stock execution (not an option)

    Returns:
        Tuple of (normalized_strike, normalized_quantity, normalized_price)
    """
    splits = get_splits_for_symbol(symbol)

    normalized_strike = strike
    normalized_quantity = quantity
    normalized_price = price

    for split in splits:
        if execution_date.date() < split.split_date:
            # Check if this looks like a pre-split execution
            needs_normalization = False

            if strike is not None:
                # Option - check if strike looks pre-split using split-specific threshold
                if split.is_pre_split_strike(strike):
                    needs_normalization = True
            elif is_stock and split.apply_to_stocks:
                # Stock - normalize based on date if apply_to_stocks is enabled
                needs_normalization = True

            if needs_normalization:
                # Use StockSplit methods which handle forward vs reverse correctly
                if normalized_strike is not None:
                    normalized_strike = split.normalize_strike(normalized_strike, execution_date)
                normalized_quantity = split.normalize_quantity(normalized_quantity, execution_date)
                normalized_price = split.normalize_price(normalized_price, execution_date)

    return normalized_strike, normalized_quantity, normalized_price
