"""Collateral Service - Margin and collateral calculations."""

import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.models.margin_settings import MarginSettings
from trading_journal.services.trade_analytics_service import LegData, StrategyType

logger = logging.getLogger(__name__)

# Default margin percentages
DEFAULT_NAKED_PUT_MARGIN = Decimal("20.00")  # 20% of underlying
DEFAULT_NAKED_CALL_MARGIN = Decimal("20.00")  # 20% of underlying
DEFAULT_SPREAD_MARGIN = Decimal("100.00")  # Full width of spread
DEFAULT_IRON_CONDOR_MARGIN = Decimal("100.00")  # Wider side width


class CollateralService:
    """Service for calculating collateral and margin requirements.

    Supports per-underlying margin customization and various strategy types.
    """

    def __init__(self, session: AsyncSession):
        """Initialize Collateral service.

        Args:
            session: Database session
        """
        self.session = session
        self._cache: dict[str, MarginSettings] = {}

    async def get_margin_settings(self, underlying: str) -> MarginSettings | None:
        """Get margin settings for an underlying.

        Args:
            underlying: Underlying symbol

        Returns:
            MarginSettings or None if using defaults
        """
        # Check cache first
        if underlying in self._cache:
            return self._cache[underlying]

        stmt = select(MarginSettings).where(MarginSettings.underlying == underlying)
        result = await self.session.execute(stmt)
        settings = result.scalar_one_or_none()

        if settings:
            self._cache[underlying] = settings

        return settings

    async def set_margin_settings(
        self,
        underlying: str,
        naked_put_margin_pct: Decimal | None = None,
        naked_call_margin_pct: Decimal | None = None,
        spread_margin_pct: Decimal | None = None,
        iron_condor_margin_pct: Decimal | None = None,
        notes: str | None = None,
    ) -> MarginSettings:
        """Set or update margin settings for an underlying.

        Args:
            underlying: Underlying symbol
            naked_put_margin_pct: Margin % for naked puts
            naked_call_margin_pct: Margin % for naked calls
            spread_margin_pct: Margin % for spreads
            iron_condor_margin_pct: Margin % for iron condors
            notes: Optional notes

        Returns:
            Created or updated MarginSettings
        """
        existing = await self.get_margin_settings(underlying)

        if existing:
            if naked_put_margin_pct is not None:
                existing.naked_put_margin_pct = naked_put_margin_pct
            if naked_call_margin_pct is not None:
                existing.naked_call_margin_pct = naked_call_margin_pct
            if spread_margin_pct is not None:
                existing.spread_margin_pct = spread_margin_pct
            if iron_condor_margin_pct is not None:
                existing.iron_condor_margin_pct = iron_condor_margin_pct
            if notes is not None:
                existing.notes = notes
            await self.session.flush()
            self._cache[underlying] = existing
            return existing

        settings = MarginSettings(
            underlying=underlying,
            naked_put_margin_pct=naked_put_margin_pct or DEFAULT_NAKED_PUT_MARGIN,
            naked_call_margin_pct=naked_call_margin_pct or DEFAULT_NAKED_CALL_MARGIN,
            spread_margin_pct=spread_margin_pct or DEFAULT_SPREAD_MARGIN,
            iron_condor_margin_pct=iron_condor_margin_pct or DEFAULT_IRON_CONDOR_MARGIN,
            notes=notes,
        )
        self.session.add(settings)
        await self.session.flush()
        self._cache[underlying] = settings
        return settings

    async def delete_margin_settings(self, underlying: str) -> bool:
        """Delete margin settings for an underlying.

        Args:
            underlying: Underlying symbol

        Returns:
            True if deleted, False if not found
        """
        settings = await self.get_margin_settings(underlying)
        if settings:
            await self.session.delete(settings)
            await self.session.commit()
            self._cache.pop(underlying, None)
            return True
        return False

    async def calculate_collateral(
        self,
        underlying: str,
        legs: list[LegData],
        strategy_type: str,
        underlying_price: Decimal,
        multiplier: int = 100,
    ) -> Decimal:
        """Calculate collateral requirement for a trade.

        Args:
            underlying: Underlying symbol
            legs: List of leg data
            strategy_type: Type of strategy
            underlying_price: Current underlying price
            multiplier: Contract multiplier (default 100)

        Returns:
            Collateral requirement in dollars
        """
        settings = await self.get_margin_settings(underlying)

        # Get margin percentages
        naked_put_pct = settings.naked_put_margin_pct if settings else DEFAULT_NAKED_PUT_MARGIN
        naked_call_pct = settings.naked_call_margin_pct if settings else DEFAULT_NAKED_CALL_MARGIN
        spread_pct = settings.spread_margin_pct if settings else DEFAULT_SPREAD_MARGIN
        ic_pct = settings.iron_condor_margin_pct if settings else DEFAULT_IRON_CONDOR_MARGIN

        # Calculate based on strategy type
        if strategy_type == StrategyType.VERTICAL_CALL.value:
            return self._calculate_spread_collateral(legs, spread_pct, multiplier)

        elif strategy_type == StrategyType.VERTICAL_PUT.value:
            return self._calculate_spread_collateral(legs, spread_pct, multiplier)

        elif strategy_type == StrategyType.IRON_CONDOR.value:
            return self._calculate_iron_condor_collateral(legs, ic_pct, multiplier)

        elif strategy_type == StrategyType.IRON_BUTTERFLY.value:
            return self._calculate_iron_condor_collateral(legs, ic_pct, multiplier)

        elif strategy_type == StrategyType.CASH_SECURED_PUT.value:
            return self._calculate_csp_collateral(legs, multiplier)

        elif strategy_type == StrategyType.COVERED_CALL.value:
            # Covered call collateral is the stock cost
            return underlying_price * multiplier

        elif strategy_type == StrategyType.SINGLE.value:
            leg = legs[0]
            if leg.quantity < 0:  # Short option
                if leg.option_type == "P":
                    return self._calculate_naked_put_collateral(
                        leg, underlying_price, naked_put_pct, multiplier
                    )
                else:
                    return self._calculate_naked_call_collateral(
                        leg, underlying_price, naked_call_pct, multiplier
                    )
            else:  # Long option - collateral is premium paid
                return abs(leg.premium or Decimal("0")) * multiplier

        elif strategy_type in [StrategyType.STRADDLE.value, StrategyType.STRANGLE.value]:
            # Short straddle/strangle: use larger of put or call margin
            short_legs = [leg for leg in legs if leg.quantity < 0]
            if short_legs:
                put_margin = Decimal("0")
                call_margin = Decimal("0")
                for leg in short_legs:
                    if leg.option_type == "P":
                        put_margin = self._calculate_naked_put_collateral(
                            leg, underlying_price, naked_put_pct, multiplier
                        )
                    else:
                        call_margin = self._calculate_naked_call_collateral(
                            leg, underlying_price, naked_call_pct, multiplier
                        )
                return max(put_margin, call_margin)
            else:
                # Long straddle/strangle - premium is the cost
                return sum(
                    abs(leg.premium or Decimal("0")) * multiplier for leg in legs
                )

        # Default: return 0 for undefined strategies
        logger.warning(f"Unknown strategy type for collateral: {strategy_type}")
        return Decimal("0")

    def _calculate_spread_collateral(
        self,
        legs: list[LegData],
        margin_pct: Decimal,
        multiplier: int,
    ) -> Decimal:
        """Calculate collateral for a vertical spread.

        Collateral = Width of spread * margin_pct / 100 * multiplier

        Args:
            legs: List of leg data
            margin_pct: Margin percentage
            multiplier: Contract multiplier

        Returns:
            Collateral requirement
        """
        strikes = [leg.strike for leg in legs]
        if len(strikes) < 2:
            return Decimal("0")

        width = max(strikes) - min(strikes)
        return width * (margin_pct / 100) * multiplier

    def _calculate_iron_condor_collateral(
        self,
        legs: list[LegData],
        margin_pct: Decimal,
        multiplier: int,
    ) -> Decimal:
        """Calculate collateral for an iron condor.

        Collateral = Wider side width * margin_pct / 100 * multiplier

        Args:
            legs: List of leg data
            margin_pct: Margin percentage
            multiplier: Contract multiplier

        Returns:
            Collateral requirement
        """
        put_legs = [leg for leg in legs if leg.option_type == "P"]
        call_legs = [leg for leg in legs if leg.option_type == "C"]

        put_width = Decimal("0")
        call_width = Decimal("0")

        if len(put_legs) >= 2:
            put_strikes = [leg.strike for leg in put_legs]
            put_width = max(put_strikes) - min(put_strikes)

        if len(call_legs) >= 2:
            call_strikes = [leg.strike for leg in call_legs]
            call_width = max(call_strikes) - min(call_strikes)

        max_width = max(put_width, call_width)
        return max_width * (margin_pct / 100) * multiplier

    def _calculate_csp_collateral(
        self,
        legs: list[LegData],
        multiplier: int,
    ) -> Decimal:
        """Calculate collateral for a cash-secured put.

        Collateral = Strike price * multiplier (full cash secured)

        Args:
            legs: List of leg data
            multiplier: Contract multiplier

        Returns:
            Collateral requirement
        """
        if not legs:
            return Decimal("0")

        put_leg = legs[0]
        return put_leg.strike * multiplier

    def _calculate_naked_put_collateral(
        self,
        leg: LegData,
        underlying_price: Decimal,
        margin_pct: Decimal,
        multiplier: int,
    ) -> Decimal:
        """Calculate collateral for a naked put.

        Standard margin: max(20% of underlying - OTM amount, 10% of strike)
        Simplified: margin_pct of underlying * multiplier

        Args:
            leg: Leg data
            underlying_price: Current underlying price
            margin_pct: Margin percentage
            multiplier: Contract multiplier

        Returns:
            Collateral requirement
        """
        # Simplified calculation
        base_margin = underlying_price * (margin_pct / 100) * multiplier

        # Add OTM/ITM adjustment
        otm_amount = underlying_price - leg.strike
        if otm_amount > 0:  # OTM put
            base_margin -= otm_amount * multiplier

        # Minimum margin
        min_margin = leg.strike * Decimal("0.10") * multiplier
        return max(base_margin, min_margin)

    def _calculate_naked_call_collateral(
        self,
        leg: LegData,
        underlying_price: Decimal,
        margin_pct: Decimal,
        multiplier: int,
    ) -> Decimal:
        """Calculate collateral for a naked call.

        Args:
            leg: Leg data
            underlying_price: Current underlying price
            margin_pct: Margin percentage
            multiplier: Contract multiplier

        Returns:
            Collateral requirement
        """
        # Simplified calculation
        base_margin = underlying_price * (margin_pct / 100) * multiplier

        # Add OTM/ITM adjustment
        otm_amount = leg.strike - underlying_price
        if otm_amount > 0:  # OTM call
            base_margin -= otm_amount * multiplier

        # Minimum margin
        min_margin = underlying_price * Decimal("0.10") * multiplier
        return max(base_margin, min_margin)

    def clear_cache(self) -> None:
        """Clear the margin settings cache."""
        self._cache.clear()
