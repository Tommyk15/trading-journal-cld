"""Trade Analytics Service - Greeks, IV metrics, and risk analytics calculations."""

import logging
import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from scipy.stats import norm

logger = logging.getLogger(__name__)


class StrategyType(str, Enum):
    """Options strategy types."""

    SINGLE = "Single"
    VERTICAL_CALL = "Vertical Call Spread"
    VERTICAL_PUT = "Vertical Put Spread"
    IRON_CONDOR = "Iron Condor"
    IRON_BUTTERFLY = "Iron Butterfly"
    BUTTERFLY = "Butterfly"
    CALENDAR = "Calendar"
    STRADDLE = "Straddle"
    STRANGLE = "Strangle"
    COVERED_CALL = "Covered Call"
    CASH_SECURED_PUT = "Cash Secured Put"
    COMPLEX = "Complex"


@dataclass
class LegData:
    """Data for a single option leg."""

    option_type: str  # "C" or "P"
    strike: Decimal
    expiration: datetime
    quantity: int  # Signed: positive for long, negative for short
    delta: Decimal | None = None
    gamma: Decimal | None = None
    theta: Decimal | None = None
    vega: Decimal | None = None
    iv: Decimal | None = None
    premium: Decimal | None = None


@dataclass
class TradeAnalytics:
    """Calculated analytics for a trade."""

    # Net Greeks (weighted sum across legs)
    net_delta: Decimal | None
    net_gamma: Decimal | None
    net_theta: Decimal | None
    net_vega: Decimal | None

    # IV metrics
    trade_iv: Decimal | None  # Short strike IV for credit strategies
    iv_percentile: Decimal | None
    iv_rank: Decimal | None

    # Risk analytics
    pop: Decimal | None  # Probability of profit (0-100)
    breakeven: list[Decimal]  # Can have multiple breakevens
    max_profit: Decimal | None
    max_risk: Decimal | None
    risk_reward_ratio: Decimal | None

    # Collateral
    collateral_required: Decimal | None

    # Days to expiration (for front month if multi-expiry)
    dte: int | None


class TradeAnalyticsService:
    """Service for calculating trade analytics.

    Computes Greeks, IV metrics, probability of profit, max profit/risk,
    and collateral requirements for options trades.
    """

    def __init__(self, risk_free_rate: Decimal = Decimal("0.05")):
        """Initialize analytics service.

        Args:
            risk_free_rate: Annual risk-free rate (default 5%)
        """
        self.risk_free_rate = risk_free_rate

    def calculate_net_greeks(self, legs: list[LegData], multiplier: int = 100) -> dict:
        """Calculate net Greeks for a multi-leg trade.

        Greeks are summed across legs, weighted by signed quantity.

        Args:
            legs: List of leg data with Greeks
            multiplier: Contract multiplier (default 100)

        Returns:
            Dictionary with net delta, gamma, theta, vega
        """
        net_delta = Decimal("0")
        net_gamma = Decimal("0")
        net_theta = Decimal("0")
        net_vega = Decimal("0")

        for leg in legs:
            qty = leg.quantity
            if leg.delta is not None:
                net_delta += leg.delta * qty
            if leg.gamma is not None:
                net_gamma += leg.gamma * qty
            if leg.theta is not None:
                net_theta += leg.theta * qty
            if leg.vega is not None:
                net_vega += leg.vega * qty

        return {
            "net_delta": net_delta * multiplier,
            "net_gamma": net_gamma * multiplier,
            "net_theta": net_theta * multiplier,
            "net_vega": net_vega * multiplier,
        }

    def get_trade_iv(self, legs: list[LegData], strategy_type: str) -> Decimal | None:
        """Get trade-level IV based on strategy type.

        For credit strategies, use the short strike IV.
        For debit strategies, use the long strike IV.
        For complex strategies, use weighted average.

        Args:
            legs: List of leg data with IV
            strategy_type: Type of strategy

        Returns:
            Trade-level IV or None if not available
        """
        if not legs:
            return None

        # Find short and long legs
        short_legs = [leg for leg in legs if leg.quantity < 0 and leg.iv is not None]
        long_legs = [leg for leg in legs if leg.quantity > 0 and leg.iv is not None]

        # Credit strategies: use short strike IV
        credit_strategies = [
            StrategyType.VERTICAL_CALL.value,
            StrategyType.VERTICAL_PUT.value,
            StrategyType.IRON_CONDOR.value,
            StrategyType.IRON_BUTTERFLY.value,
            StrategyType.CASH_SECURED_PUT.value,
            StrategyType.COVERED_CALL.value,
        ]

        if strategy_type in credit_strategies and short_legs:
            # Use average IV of short legs
            return sum(leg.iv for leg in short_legs) / len(short_legs)

        # Debit strategies: use long strike IV
        if long_legs:
            return sum(leg.iv for leg in long_legs) / len(long_legs)

        # Fallback: weighted average of all legs
        all_legs_with_iv = [leg for leg in legs if leg.iv is not None]
        if all_legs_with_iv:
            total_qty = sum(abs(leg.quantity) for leg in all_legs_with_iv)
            weighted_iv = sum(leg.iv * abs(leg.quantity) for leg in all_legs_with_iv)
            return weighted_iv / total_qty

        return None

    def calculate_pop_black_scholes(
        self,
        underlying_price: Decimal,
        breakeven: Decimal,
        iv: Decimal,
        dte: int,
        is_credit: bool = True,
    ) -> Decimal:
        """Calculate Probability of Profit using Black-Scholes model.

        Uses the cumulative normal distribution to estimate the probability
        that the underlying will be above/below breakeven at expiration.

        Args:
            underlying_price: Current underlying price
            breakeven: Breakeven price
            iv: Implied volatility (as decimal, e.g., 0.20 for 20%)
            dte: Days to expiration
            is_credit: True for credit strategies (profit if price stays away)

        Returns:
            Probability of profit as percentage (0-100)
        """
        if dte <= 0 or iv <= 0:
            return Decimal("50")  # 50-50 if no time or IV

        # Convert to float for scipy
        S = float(underlying_price)
        K = float(breakeven)
        sigma = float(iv)
        t = dte / 365.0
        r = float(self.risk_free_rate)

        # Calculate d2 (probability that S > K at expiration)
        d2 = (math.log(S / K) + (r - 0.5 * sigma**2) * t) / (sigma * math.sqrt(t))

        # norm.cdf(d2) ≈ P(S_T > breakeven)
        prob_above = norm.cdf(d2) * 100
        prob_below = 100 - prob_above

        if is_credit:
            # Credit strategies: profit if price stays away from breakeven
            # If breakeven > current price: profit if S < breakeven (short call)
            # If breakeven < current price: profit if S > breakeven (short put)
            if K > S:
                pop = prob_below  # Short call: profit if stock stays below breakeven
            else:
                pop = prob_above  # Short put: profit if stock stays above breakeven
        else:
            # Debit strategies: profit if price moves past breakeven
            # If breakeven > current price: profit if S > breakeven (long call)
            # If breakeven < current price: profit if S < breakeven (long put)
            if K > S:
                pop = prob_above  # Long call: profit if stock rises above breakeven
            else:
                pop = prob_below  # Long put: profit if stock falls below breakeven

        return Decimal(str(round(pop, 2)))

    def calculate_breakevens(
        self,
        legs: list[LegData],
        strategy_type: str,
        net_premium: Decimal,
    ) -> list[Decimal]:
        """Calculate breakeven prices for a trade.

        Args:
            legs: List of leg data
            strategy_type: Type of strategy
            net_premium: Net premium received (positive) or paid (negative)

        Returns:
            List of breakeven prices
        """
        breakevens = []

        if not legs:
            return breakevens

        # Map database strategy types to calculation categories
        vertical_call_types = [
            StrategyType.VERTICAL_CALL.value,
            "Bull Call Spread",
            "Bear Call Spread",
        ]
        vertical_put_types = [
            StrategyType.VERTICAL_PUT.value,
            "Bull Put Spread",
            "Bear Put Spread",
        ]
        single_types = [
            StrategyType.SINGLE.value,
            "Long Call",
            "Short Call",
            "Long Put",
            "Short Put",
        ]

        if strategy_type in vertical_call_types:
            # Call spread: breakeven = lower strike + premium paid/received
            call_legs = [leg for leg in legs if leg.option_type == "C"]
            if call_legs:
                lower_strike = min(leg.strike for leg in call_legs)
                breakevens.append(lower_strike + abs(net_premium))

        elif strategy_type in vertical_put_types:
            # Put spread: breakeven = higher strike - premium paid/received
            put_legs = [leg for leg in legs if leg.option_type == "P"]
            if put_legs:
                higher_strike = max(leg.strike for leg in put_legs)
                breakevens.append(higher_strike - abs(net_premium))

        elif strategy_type == StrategyType.IRON_CONDOR.value:
            # Two breakevens: put side and call side
            put_legs = [leg for leg in legs if leg.option_type == "P"]
            call_legs = [leg for leg in legs if leg.option_type == "C"]

            if put_legs:
                higher_put = max(leg.strike for leg in put_legs)
                breakevens.append(higher_put - abs(net_premium))

            if call_legs:
                lower_call = min(leg.strike for leg in call_legs)
                breakevens.append(lower_call + abs(net_premium))

        elif strategy_type == StrategyType.STRADDLE.value:
            # Two breakevens: strike ± premium
            strike = legs[0].strike
            breakevens.append(strike - abs(net_premium))
            breakevens.append(strike + abs(net_premium))

        elif strategy_type == StrategyType.STRANGLE.value:
            put_strike = min(leg.strike for leg in legs if leg.option_type == "P")
            call_strike = max(leg.strike for leg in legs if leg.option_type == "C")
            breakevens.append(put_strike - abs(net_premium))
            breakevens.append(call_strike + abs(net_premium))

        elif strategy_type in single_types:
            # Single option
            leg = legs[0]
            if leg.quantity > 0:  # Long
                if leg.option_type == "C":
                    breakevens.append(leg.strike + abs(net_premium))
                else:
                    breakevens.append(leg.strike - abs(net_premium))
            else:  # Short
                if leg.option_type == "C":
                    breakevens.append(leg.strike + abs(net_premium))
                else:
                    breakevens.append(leg.strike - abs(net_premium))

        elif strategy_type == StrategyType.CASH_SECURED_PUT.value:
            put_strike = legs[0].strike
            breakevens.append(put_strike - abs(net_premium))

        elif strategy_type == StrategyType.COVERED_CALL.value:
            # Breakeven is cost basis - premium received
            # This requires knowing the stock cost basis
            call_strike = legs[0].strike
            breakevens.append(call_strike)  # Simplified

        return sorted(breakevens)

    def calculate_max_profit_risk(
        self,
        legs: list[LegData],
        strategy_type: str,
        net_premium: Decimal,
        multiplier: int = 100,
    ) -> tuple[Decimal | None, Decimal | None]:
        """Calculate maximum profit and maximum risk for a trade.

        Args:
            legs: List of leg data
            strategy_type: Type of strategy
            net_premium: Net premium received (positive) or paid (negative)
            multiplier: Contract multiplier (default 100)

        Returns:
            Tuple of (max_profit, max_risk)
        """
        if not legs:
            return None, None

        # Get strike information
        strikes = sorted({leg.strike for leg in legs})

        # Map database strategy types to calculation categories
        vertical_call_types = [
            StrategyType.VERTICAL_CALL.value,
            "Bull Call Spread",
            "Bear Call Spread",
        ]
        vertical_put_types = [
            StrategyType.VERTICAL_PUT.value,
            "Bull Put Spread",
            "Bear Put Spread",
        ]
        single_types = [
            StrategyType.SINGLE.value,
            "Long Call",
            "Short Call",
            "Long Put",
            "Short Put",
        ]

        if strategy_type in vertical_call_types:
            # Credit spread: max profit = premium, max risk = width - premium
            # Debit spread: max profit = width - premium, max risk = premium
            width = max(strikes) - min(strikes)
            if net_premium > 0:  # Credit spread
                max_profit = net_premium * multiplier
                max_risk = (width - net_premium) * multiplier
            else:  # Debit spread
                max_profit = (width + net_premium) * multiplier
                max_risk = abs(net_premium) * multiplier
            return max_profit, max_risk

        elif strategy_type in vertical_put_types:
            width = max(strikes) - min(strikes)
            if net_premium > 0:  # Credit spread
                max_profit = net_premium * multiplier
                max_risk = (width - net_premium) * multiplier
            else:  # Debit spread
                max_profit = (width + net_premium) * multiplier
                max_risk = abs(net_premium) * multiplier
            return max_profit, max_risk

        elif strategy_type == StrategyType.IRON_CONDOR.value:
            # Max profit = net premium received
            # Max risk = wider spread width - net premium
            put_strikes = sorted(leg.strike for leg in legs if leg.option_type == "P")
            call_strikes = sorted(leg.strike for leg in legs if leg.option_type == "C")

            put_width = put_strikes[-1] - put_strikes[0] if len(put_strikes) >= 2 else Decimal("0")
            call_width = call_strikes[-1] - call_strikes[0] if len(call_strikes) >= 2 else Decimal("0")
            max_width = max(put_width, call_width)

            max_profit = net_premium * multiplier
            max_risk = (max_width - net_premium) * multiplier
            return max_profit, max_risk

        elif strategy_type == StrategyType.IRON_BUTTERFLY.value:
            # Similar to iron condor but ATM short strikes
            put_strikes = sorted(leg.strike for leg in legs if leg.option_type == "P")
            call_strikes = sorted(leg.strike for leg in legs if leg.option_type == "C")

            if put_strikes and call_strikes:
                width = max(call_strikes[-1] - call_strikes[0], put_strikes[-1] - put_strikes[0])
                max_profit = net_premium * multiplier
                max_risk = (width - net_premium) * multiplier
                return max_profit, max_risk

        elif strategy_type in [StrategyType.STRADDLE.value, StrategyType.STRANGLE.value]:
            if net_premium > 0:  # Short straddle/strangle
                max_profit = net_premium * multiplier
                max_risk = None  # Unlimited
            else:  # Long straddle/strangle
                max_profit = None  # Unlimited
                max_risk = abs(net_premium) * multiplier
            return max_profit, max_risk

        elif strategy_type in single_types:
            leg = legs[0]
            # Determine if long or short based on strategy name or leg quantity
            is_long = leg.quantity > 0 or strategy_type.startswith("Long")
            is_short = leg.quantity < 0 or strategy_type.startswith("Short")

            if is_long:  # Long option
                max_profit = None  # Unlimited for calls
                max_risk = abs(net_premium) * multiplier
                if leg.option_type == "P":
                    max_profit = (leg.strike - abs(net_premium)) * multiplier
            else:  # Short option
                max_profit = abs(net_premium) * multiplier
                max_risk = None  # Unlimited for calls
                if leg.option_type == "P":
                    max_risk = (leg.strike - abs(net_premium)) * multiplier
            return max_profit, max_risk

        elif strategy_type == StrategyType.CASH_SECURED_PUT.value:
            leg = legs[0]
            max_profit = net_premium * multiplier
            max_risk = (leg.strike - net_premium) * multiplier
            return max_profit, max_risk

        elif strategy_type == StrategyType.COVERED_CALL.value:
            # Simplified - would need stock cost basis for accurate calculation
            max_profit = net_premium * multiplier
            max_risk = None  # Risk is in the stock
            return max_profit, max_risk

        return None, None

    def calculate_dte(self, legs: list[LegData]) -> int | None:
        """Calculate days to expiration for the front month.

        For calendar spreads, uses the nearest expiration.

        Args:
            legs: List of leg data

        Returns:
            Days to expiration or None
        """
        if not legs:
            return None

        expirations = [leg.expiration for leg in legs if leg.expiration]
        if not expirations:
            return None

        # Use front month (earliest expiration)
        front_exp = min(expirations)
        today = datetime.now().date()
        exp_date = front_exp.date() if isinstance(front_exp, datetime) else front_exp

        return (exp_date - today).days

    def calculate_analytics(
        self,
        legs: list[LegData],
        strategy_type: str,
        underlying_price: Decimal,
        net_premium: Decimal,
        iv_percentile: Decimal | None = None,
        iv_rank: Decimal | None = None,
        collateral: Decimal | None = None,
    ) -> TradeAnalytics:
        """Calculate complete analytics for a trade.

        Args:
            legs: List of leg data with Greeks and IV
            strategy_type: Type of strategy
            underlying_price: Current underlying price
            net_premium: Net premium received (positive) or paid (negative)
            iv_percentile: Pre-calculated IV percentile (optional)
            iv_rank: Pre-calculated IV rank (optional)
            collateral: Pre-calculated collateral requirement (optional)

        Returns:
            TradeAnalytics object with all calculations
        """
        # Net Greeks
        greeks = self.calculate_net_greeks(legs)

        # Trade-level IV
        trade_iv = self.get_trade_iv(legs, strategy_type)

        # Breakevens
        breakevens = self.calculate_breakevens(legs, strategy_type, net_premium)

        # Max profit/risk
        max_profit, max_risk = self.calculate_max_profit_risk(
            legs, strategy_type, net_premium
        )

        # Risk/reward ratio
        risk_reward = None
        if max_profit and max_risk and max_risk > 0:
            risk_reward = max_profit / max_risk

        # DTE
        dte = self.calculate_dte(legs)

        # Probability of profit
        pop = None
        if breakevens and trade_iv and dte and dte > 0:
            # Use first breakeven for simplicity
            is_credit = net_premium > 0
            pop = self.calculate_pop_black_scholes(
                underlying_price,
                breakevens[0],
                trade_iv,
                dte,
                is_credit,
            )

        return TradeAnalytics(
            net_delta=greeks["net_delta"],
            net_gamma=greeks["net_gamma"],
            net_theta=greeks["net_theta"],
            net_vega=greeks["net_vega"],
            trade_iv=trade_iv,
            iv_percentile=iv_percentile,
            iv_rank=iv_rank,
            pop=pop,
            breakeven=breakevens,
            max_profit=max_profit,
            max_risk=max_risk,
            risk_reward_ratio=risk_reward,
            collateral_required=collateral,
            dte=dte,
        )

    async def populate_all_trade_fields(
        self,
        trade,  # Trade model
        session,  # AsyncSession
    ) -> bool:
        """Populate ALL trade fields with Greeks and analytics.

        Fetches Greeks from IBKR (primary) or Polygon (fallback), then
        calculates and stores all analytics fields on the trade.

        Args:
            trade: Trade model to populate
            session: Database session

        Returns:
            True if successful, False if critical fields missing
        """
        from sqlalchemy import select
        from trading_journal.models.execution import Execution

        # Get executions for this trade
        stmt = select(Execution).where(Execution.trade_id == trade.id)
        result = await session.execute(stmt)
        executions = list(result.scalars().all())

        if not executions:
            logger.warning(f"No executions found for trade {trade.id}")
            return False

        # Build legs from executions
        legs = self._build_legs_from_executions(executions)

        if not legs:
            logger.warning(f"No option legs found for trade {trade.id}")
            return False

        # 1. Fetch Greeks from IBKR (primary) or Polygon (fallback)
        greeks_source, legs_with_greeks, underlying_price = await self._fetch_greeks_multi_source(
            trade, legs
        )

        if not legs_with_greeks:
            logger.warning(f"Could not fetch Greeks for trade {trade.id}")
            trade.greeks_pending = True
            return False

        # 2. Calculate net Greeks
        net_greeks = self.calculate_net_greeks(legs_with_greeks, multiplier=1)
        trade.delta_open = net_greeks["net_delta"]
        trade.gamma_open = net_greeks["net_gamma"]
        trade.theta_open = net_greeks["net_theta"]
        trade.vega_open = net_greeks["net_vega"]

        # 3. Get trade-level IV
        trade.iv_open = self.get_trade_iv(legs_with_greeks, trade.strategy_type or "")
        trade.underlying_price_open = underlying_price
        trade.greeks_source = greeks_source

        # 4. Calculate net premium from executions
        net_premium = self._calculate_net_premium(executions)

        # 5. Calculate max profit/risk
        max_profit, max_risk = self.calculate_max_profit_risk(
            legs_with_greeks,
            trade.strategy_type or "",
            net_premium,
            multiplier=1,  # Per contract
        )
        trade.max_profit = max_profit
        trade.max_risk = max_risk

        # 6. Calculate PoP
        dte = self.calculate_dte(legs_with_greeks)
        if trade.iv_open and underlying_price and dte and dte > 0:
            breakevens = self.calculate_breakevens(
                legs_with_greeks, trade.strategy_type or "", net_premium
            )
            if breakevens:
                is_credit = net_premium > 0
                pop = self.calculate_pop_black_scholes(
                    underlying_price,
                    breakevens[0],
                    trade.iv_open,
                    dte,
                    is_credit,
                )
                trade.pop_open = pop

        # 7. Calculate collateral
        trade.collateral_calculated = self._calculate_collateral(
            trade.strategy_type or "",
            legs_with_greeks,
        )

        # Mark Greeks as fetched
        trade.greeks_pending = False

        await session.flush()
        logger.info(f"Populated all fields for trade {trade.id} (source: {greeks_source})")
        return True

    async def populate_analytics_only(
        self,
        trade,  # Trade model
        session,  # AsyncSession
    ) -> bool:
        """Populate only analytics fields for a trade that already has Greeks.

        Use this when Greeks are already fetched but analytics fields
        (max_profit, max_risk, pop_open) are missing.

        Args:
            trade: Trade model with Greeks already populated
            session: Database session

        Returns:
            True if successful
        """
        from sqlalchemy import select
        from trading_journal.models.execution import Execution

        if trade.delta_open is None:
            logger.warning(f"Trade {trade.id} has no Greeks, skipping analytics")
            return False

        # Get executions for this trade
        stmt = select(Execution).where(Execution.trade_id == trade.id)
        result = await session.execute(stmt)
        executions = list(result.scalars().all())

        if not executions:
            return False

        # Build legs from executions (without Greeks, just for structure)
        legs = self._build_legs_from_executions(executions)

        if not legs:
            return False

        # Calculate net premium
        net_premium = self._calculate_net_premium(executions)

        # Get the number of contracts (use max absolute quantity from legs)
        num_contracts = max(abs(leg.quantity) for leg in legs) if legs else 1

        # Calculate max profit/risk in dollar terms (multiplier=100 for options)
        max_profit, max_risk = self.calculate_max_profit_risk(
            legs,
            trade.strategy_type or "",
            net_premium,
            multiplier=100,  # Standard option contract multiplier
        )

        # Multiply by number of contracts for total position value
        if max_profit is not None:
            trade.max_profit = max_profit * num_contracts
        else:
            trade.max_profit = None
        if max_risk is not None:
            trade.max_risk = max_risk * num_contracts
        else:
            trade.max_risk = None

        # Calculate PoP if we have IV
        dte = self.calculate_dte(legs)
        if trade.iv_open and trade.underlying_price_open and dte and dte > 0:
            breakevens = self.calculate_breakevens(
                legs, trade.strategy_type or "", net_premium
            )
            if breakevens:
                is_credit = net_premium > 0
                pop = self.calculate_pop_black_scholes(
                    trade.underlying_price_open,
                    breakevens[0],
                    trade.iv_open,
                    dte,
                    is_credit,
                )
                trade.pop_open = pop

        # Calculate collateral (multiply by num_contracts for total position)
        collateral = self._calculate_collateral(
            trade.strategy_type or "",
            legs,
        )
        if collateral is not None:
            trade.collateral_calculated = collateral * num_contracts
        else:
            trade.collateral_calculated = None

        await session.flush()
        return True

    async def populate_max_profit_risk_only(
        self,
        trade,  # Trade model
        session,  # AsyncSession
    ) -> bool:
        """Populate max_profit and max_risk without requiring Greeks.

        This can run for ALL trades regardless of Greeks status.
        Only calculates max_profit and max_risk from execution data.

        Args:
            trade: Trade model
            session: Database session

        Returns:
            True if successful
        """
        from sqlalchemy import select
        from trading_journal.models.execution import Execution

        # Get executions for this trade
        stmt = select(Execution).where(Execution.trade_id == trade.id)
        result = await session.execute(stmt)
        executions = list(result.scalars().all())

        if not executions:
            logger.debug(f"Trade {trade.id} has no executions, skipping max profit/risk")
            return False

        # Build legs from executions
        legs = self._build_legs_from_executions(executions)
        if not legs:
            logger.debug(f"Trade {trade.id} has no option legs, skipping max profit/risk")
            return False

        # Calculate net premium
        net_premium = self._calculate_net_premium(executions)

        # Get the number of contracts (use max absolute quantity from legs)
        num_contracts = max(abs(leg.quantity) for leg in legs) if legs else 1

        # Calculate max profit/risk in dollar terms (multiplier=100 for options)
        max_profit, max_risk = self.calculate_max_profit_risk(
            legs,
            trade.strategy_type or "",
            net_premium,
            multiplier=100,  # Standard option contract multiplier
        )

        # Multiply by number of contracts for total position value
        if max_profit is not None:
            max_profit = max_profit * num_contracts
        if max_risk is not None:
            max_risk = max_risk * num_contracts

        trade.max_profit = max_profit
        trade.max_risk = max_risk

        await session.flush()
        logger.debug(f"Populated max_profit=${max_profit}, max_risk=${max_risk} for trade {trade.id} ({num_contracts} contracts)")
        return True

    async def _fetch_greeks_multi_source(
        self,
        trade,
        legs: list[LegData],
    ) -> tuple[str | None, list[LegData] | None, Decimal | None]:
        """Fetch Greeks from IBKR (primary) or Polygon (fallback).

        Args:
            trade: Trade model
            legs: List of leg data without Greeks

        Returns:
            Tuple of (source, legs_with_greeks, underlying_price)
        """
        # Try IBKR first
        result = await self._fetch_greeks_ibkr(trade, legs)
        if result[1]:  # legs_with_greeks is not None
            return ("IBKR", result[1], result[2])

        # Fallback to Polygon
        result = await self._fetch_greeks_polygon(trade, legs)
        if result[1]:
            return ("POLYGON", result[1], result[2])

        return (None, None, None)

    async def _fetch_greeks_ibkr(
        self,
        trade,
        legs: list[LegData],
    ) -> tuple[str, list[LegData] | None, Decimal | None]:
        """Fetch Greeks from IBKR via worker.

        Args:
            trade: Trade model
            legs: List of leg data

        Returns:
            Tuple of (source, legs_with_greeks, underlying_price)
        """
        try:
            from trading_journal.services.market_data_service import MarketDataService

            market_data = MarketDataService()
            worker = market_data._get_ibkr_worker()

            if not worker or not worker.is_running():
                logger.debug("IBKR worker not running")
                return ("IBKR", None, None)

            # Get underlying price
            stock_quote = worker.get_stock_quote(trade.underlying)
            if not stock_quote or not stock_quote.get("price"):
                logger.debug(f"Could not get stock quote for {trade.underlying}")
                return ("IBKR", None, None)

            underlying_price = Decimal(str(stock_quote["price"]))

            # Fetch Greeks for each leg
            legs_with_greeks = []
            for leg in legs:
                exp_str = leg.expiration.strftime("%Y%m%d") if leg.expiration else ""
                option_data = worker.get_option_data(
                    underlying=trade.underlying,
                    expiration=exp_str,
                    strike=float(leg.strike),
                    option_type=leg.option_type,
                )

                if not option_data or not option_data.get("greeks"):
                    logger.debug(f"Could not get Greeks for {trade.underlying} {exp_str} {leg.strike} {leg.option_type}")
                    return ("IBKR", None, None)

                greeks = option_data["greeks"]
                leg_with_greeks = LegData(
                    option_type=leg.option_type,
                    strike=leg.strike,
                    expiration=leg.expiration,
                    quantity=leg.quantity,
                    delta=Decimal(str(greeks["delta"])) if greeks.get("delta") else None,
                    gamma=Decimal(str(greeks["gamma"])) if greeks.get("gamma") else None,
                    theta=Decimal(str(greeks["theta"])) if greeks.get("theta") else None,
                    vega=Decimal(str(greeks["vega"])) if greeks.get("vega") else None,
                    iv=Decimal(str(greeks["iv"])) if greeks.get("iv") else None,
                    premium=leg.premium,
                )
                legs_with_greeks.append(leg_with_greeks)

            return ("IBKR", legs_with_greeks, underlying_price)

        except Exception as e:
            logger.error(f"Error fetching Greeks from IBKR: {e}")
            return ("IBKR", None, None)

    async def _fetch_greeks_polygon(
        self,
        trade,
        legs: list[LegData],
    ) -> tuple[str, list[LegData] | None, Decimal | None]:
        """Fetch Greeks from Polygon.

        Args:
            trade: Trade model
            legs: List of leg data

        Returns:
            Tuple of (source, legs_with_greeks, underlying_price)
        """
        try:
            from trading_journal.services.polygon_service import PolygonService

            async with PolygonService() as polygon:
                # Get underlying price
                underlying_price_data = await polygon.get_underlying_price(trade.underlying)
                if not underlying_price_data:
                    logger.debug(f"Could not get underlying price for {trade.underlying}")
                    return ("POLYGON", None, None)

                underlying_price = underlying_price_data

                # Fetch Greeks for each leg
                legs_with_greeks = []
                for leg in legs:
                    greeks_data = await polygon.get_option_greeks(
                        underlying=trade.underlying,
                        expiration=leg.expiration,
                        strike=leg.strike,
                        option_type=leg.option_type,
                    )

                    if not greeks_data:
                        logger.debug(f"Could not get Polygon Greeks for {trade.underlying} {leg.strike} {leg.option_type}")
                        return ("POLYGON", None, None)

                    leg_with_greeks = LegData(
                        option_type=leg.option_type,
                        strike=leg.strike,
                        expiration=leg.expiration,
                        quantity=leg.quantity,
                        delta=greeks_data.get("delta"),
                        gamma=greeks_data.get("gamma"),
                        theta=greeks_data.get("theta"),
                        vega=greeks_data.get("vega"),
                        iv=greeks_data.get("iv"),
                        premium=leg.premium,
                    )
                    legs_with_greeks.append(leg_with_greeks)

                return ("POLYGON", legs_with_greeks, underlying_price)

        except Exception as e:
            logger.error(f"Error fetching Greeks from Polygon: {e}")
            return ("POLYGON", None, None)

    def _build_legs_from_executions(self, executions: list) -> list[LegData]:
        """Build leg data from executions.

        For OPEN trades: uses net position from all executions
        For CLOSED trades: uses opening transactions only

        Args:
            executions: List of Execution models

        Returns:
            List of LegData objects
        """
        # Group by unique option contract
        contracts = {}

        for exec in executions:
            if exec.security_type != "OPT":
                continue

            # Create unique key for contract
            key = (
                exec.option_type,
                exec.strike,
                exec.expiration,
            )

            if key not in contracts:
                contracts[key] = {
                    "option_type": exec.option_type,
                    "strike": exec.strike,
                    "expiration": exec.expiration,
                    "quantity": 0,
                    "premium": Decimal("0"),
                }

            # Calculate signed quantity
            qty = exec.quantity
            if exec.side == "SLD":
                qty = -qty  # Short position

            # For opening transactions
            if exec.open_close_indicator == "O":
                contracts[key]["quantity"] += int(qty)
                contracts[key]["premium"] += exec.net_amount

        # Build LegData objects for non-zero positions
        legs = []
        for contract_data in contracts.values():
            if contract_data["quantity"] != 0:
                legs.append(LegData(
                    option_type=contract_data["option_type"],
                    strike=contract_data["strike"],
                    expiration=contract_data["expiration"],
                    quantity=contract_data["quantity"],
                    premium=contract_data["premium"],
                ))

        return legs

    def _calculate_net_premium(self, executions: list) -> Decimal:
        """Calculate net premium from executions.

        Positive = credit received
        Negative = debit paid

        Args:
            executions: List of Execution models

        Returns:
            Net premium per contract (weighted average across all contracts)
        """
        total_premium_value = Decimal("0")  # Total $ value of premium
        total_contracts = Decimal("0")  # Total number of contracts

        for exec in executions:
            if exec.security_type != "OPT":
                continue

            # Count opening transactions for premium
            # Include both "O" and None (infer as opening if not explicitly "C")
            is_opening = exec.open_close_indicator == "O" or (
                exec.open_close_indicator is None and exec.open_close_indicator != "C"
            )
            if is_opening:
                qty = abs(Decimal(str(exec.quantity)))
                premium_per_share = Decimal(str(exec.price))

                # Accumulate weighted premium (qty * price)
                if exec.side == "SLD":
                    total_premium_value += premium_per_share * qty
                else:
                    total_premium_value -= premium_per_share * qty

                total_contracts += qty

        # Return weighted average per contract
        # For a spread with equal quantities on each leg, this gives the net premium per spread
        if total_contracts > 0:
            # Divide by number of unique legs (spreads have 2 legs with equal qty)
            # Get unique strikes to determine number of legs
            unique_strikes = set()
            for exec in executions:
                if exec.security_type == "OPT" and exec.open_close_indicator == "O":
                    unique_strikes.add(exec.strike)
            num_legs = len(unique_strikes) if unique_strikes else 1

            # For a 2-leg spread with 75 contracts each side, total_contracts = 150
            # We want net premium per spread, so divide by (total_contracts / num_legs)
            contracts_per_leg = total_contracts / num_legs if num_legs > 0 else total_contracts
            return total_premium_value / contracts_per_leg if contracts_per_leg > 0 else total_premium_value

        return total_premium_value

    def _calculate_collateral(
        self,
        strategy_type: str,
        legs: list[LegData],
    ) -> Decimal | None:
        """Calculate collateral requirement for strategy.

        Args:
            strategy_type: Type of strategy
            legs: List of leg data

        Returns:
            Collateral requirement or None if undefined
        """
        if not legs:
            return None

        strikes = sorted({leg.strike for leg in legs})

        if "Vertical" in strategy_type or "Spread" in strategy_type:
            # Vertical spread: max risk = strike width
            if len(strikes) >= 2:
                width = strikes[-1] - strikes[0]
                return width * 100  # Per contract
            return None

        elif "Iron Condor" in strategy_type:
            # Iron Condor: wider of the two spreads
            call_legs = [leg for leg in legs if leg.option_type == "C"]
            put_legs = [leg for leg in legs if leg.option_type == "P"]

            call_strikes = sorted({leg.strike for leg in call_legs})
            put_strikes = sorted({leg.strike for leg in put_legs})

            call_width = call_strikes[-1] - call_strikes[0] if len(call_strikes) >= 2 else Decimal("0")
            put_width = put_strikes[-1] - put_strikes[0] if len(put_strikes) >= 2 else Decimal("0")

            return max(call_width, put_width) * 100

        elif "Short Put" in strategy_type or "Cash Secured Put" in strategy_type:
            # Cash-secured put: strike price
            put_legs = [leg for leg in legs if leg.option_type == "P" and leg.quantity < 0]
            if put_legs:
                return put_legs[0].strike * 100
            return None

        elif "Naked" in strategy_type or "Short Call" in strategy_type:
            # Undefined risk - broker determines margin
            return None

        return None
